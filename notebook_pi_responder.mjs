/** Isolated notebook model call, hosted INSIDE the existing Pi process.
 * No listener, credentials, session access, tools, transcript injection or writes.
 * The host owns IPC authorization/lifecycle; herd-board owns full lesson validation
 * and the existing pending job. This module alone enables no production route.
 */
import {Buffer} from 'node:buffer';
import {performance} from 'node:perf_hooks';
import {createHash} from 'node:crypto';

export const LIMITS=Object.freeze({imageBytes:3_000_000,imagePixels:4_000_000,
  contextBytes:12_000,promptBytes:64_000,replyBytes:24_000,deadlineMs:90_000,outputTokens:8192});
export class NotebookModelError extends Error {
  constructor(code){super(`Notebook responder: ${code}`);this.name='NotebookModelError';this.code=code;}
}
const fail=code=>{throw new NotebookModelError(code);};
export function evaluationSettings(responseFormat,evaluation) {
  if(responseFormat!=='role-eval-v1') {
    if(evaluation!==undefined) fail('invalid_prompt');
    return null;
  }
  if(!evaluation || typeof evaluation!=='object' || Array.isArray(evaluation) ||
    Object.keys(evaluation).sort().join(',')!=='outputTokens,reasoning,role' ||
    !['planner','drawer','critic'].includes(evaluation.role) ||
    !['minimal','low','medium','high','xhigh'].includes(evaluation.reasoning) ||
    !Number.isInteger(evaluation.outputTokens) || evaluation.outputTokens<1 || evaluation.outputTokens>8192) fail('invalid_prompt');
  return Object.freeze({...evaluation});
}
export function productionSettings(responseFormat,production) {
  if(responseFormat!=='role-production-v1') {
    if(production!==undefined) fail('invalid_prompt');
    return null;
  }
  const settings=evaluationSettings('role-eval-v1',production);
  if(!['planner','drawer'].includes(settings.role)) fail('invalid_prompt');
  return settings;
}
function productionTask(context,role) {
  let packet;
  try {packet=JSON.parse(context);} catch {fail('invalid_request');}
  fields(packet,['task','context']);
  if(packet.task!==(role==='planner'?'story':'panel') || !packet.context ||
    typeof packet.context!=='object' || Array.isArray(packet.context)) fail('invalid_request');
}
function fields(value,keys){
  if(!value || typeof value!=='object' || Array.isArray(value) ||
    Object.keys(value).length!==keys.length || keys.some(k=>!Object.hasOwn(value,k))) fail('invalid_request');
}
function input(request){
  fields(request,['request_id','image','context','deadline_ms']);
  if(typeof request.request_id!=='string' || !/^notebook-[0-9a-f]{32}$/.test(request.request_id) ||
    typeof request.context!=='string' || Buffer.byteLength(request.context)>LIMITS.contextBytes ||
    !Number.isInteger(request.deadline_ms) || request.deadline_ms<1 || request.deadline_ms>LIMITS.deadlineMs) fail('invalid_request');
  fields(request.image,['mime_type','data']);
  const image=request.image;
  if(image.mime_type!=='image/png' || typeof image.data!=='string' ||
    image.data.length>4*Math.ceil(LIMITS.imageBytes/3) || !/^[A-Za-z0-9+/]*={0,2}$/.test(image.data)) fail('invalid_image');
  const bytes=Buffer.from(image.data,'base64');
  if(bytes.length<33 || bytes.length>LIMITS.imageBytes || bytes.toString('base64')!==image.data ||
    !bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])) ||
    bytes.readUInt32BE(8)!==13 || bytes.toString('ascii',12,16)!=='IHDR') fail('invalid_image');
  const width=bytes.readUInt32BE(16),height=bytes.readUInt32BE(20);
  if(!width || !height || width>4096 || height>4096 || width*height>LIMITS.imagePixels) fail('invalid_image');
  // Header/transport bounds only; herd-board must fully decode its captured PNG
  // before dispatch. No attacker-specified local path is ever opened here.
  return {id:request.request_id,image:image.data,context:request.context,deadline:request.deadline_ms};
}
function completed(message,model){
  if(message?.role!=='assistant' || message.stopReason!=='stop') fail('incomplete_response');
  if(message.provider!==model.provider || message.model!==model.id) fail('model_mismatch');
  if(!Array.isArray(message.content) || message.content.some(p=>!p || !['text','thinking'].includes(p.type))) fail('tools_forbidden');
  const texts=message.content.filter(p=>p.type==='text');
  if(texts.length!==1 || typeof texts[0].text!=='string' || Buffer.byteLength(texts[0].text)>LIMITS.replyBytes) fail('invalid_response');
  const text=texts[0].text;
  // Transport the bounded assistant text unchanged, including malformed JSON.
  // Python is the sole authoritative syntax/schema/geometry gate before any
  // publication. Its offline observer can retain rejected output for diagnosis.
  // Do not strip fences, repair JSON, retry, or include reasoning/provider data.
  const usage={};
  for(const name of ['input','output','cacheRead','cacheWrite']) {
    const n=message.usage?.[name];if(Number.isInteger(n) && n>=0 && n<=1_000_000_000) usage[name]=n;
  }
  return {text,usage}; // Never return reasoning, raw provider errors or auth data.
}

export function createNotebookResponder({modelRegistry,model,systemPrompt,responseFormat='semantic-v1',evaluation,production}) {
  // Fixed host configuration only; never selectable by a notebook request.
  if(!['semantic-v1','story-panel-v1','story-stream-v1','role-eval-v1','role-production-v1'].includes(responseFormat)) fail('invalid_prompt');
  const evaluated=evaluationSettings(responseFormat,evaluation);
  const deployed=productionSettings(responseFormat,production);
  const candidate=evaluated || deployed;
  if(!model || model.provider!=='openai-codex' || typeof model.id!=='string' ||
    !/^[\w.\-/\[\]]{1,128}$/.test(model.id) || !model.input?.includes('image') ||
    typeof modelRegistry?.streamSimple!=='function' || modelRegistry.isUsingOAuth?.(model)!==true) fail('runtime_unavailable');
  if(typeof systemPrompt!=='string' || !systemPrompt.trim() || Buffer.byteLength(systemPrompt)>LIMITS.promptBytes) fail('invalid_prompt');
  // Snapshot the trusted configured model, not a value selected by the caller.
  const selected={...model};
  // Production lessons reason out their explainer; reasoning tokens share the output budget.
  const reasoning=candidate?.reasoning ?? 'medium';
  const outputTokens=candidate?.outputTokens ?? LIMITS.outputTokens;
  const evaluationIdentity=candidate ? Object.freeze({role:candidate.role,harness:'pi',
    prompt_sha256:createHash('sha256').update(systemPrompt,'utf8').digest('hex')}) : null;
  let active=null,closed=false;
  // One JSON object per reply: ask the provider for JSON mode, so a lesson cannot arrive as broken JSON
  // ("points":[1,2],[3,4] or "radius": thirty, 819a27b3). If the provider refuses it before any text, that one
  // request goes again without it, and JSON mode stays off for this process.
  let jsonMode=responseFormat==='semantic-v1';
  const jsonPayload=body=>({...body,text:{...(body.text||{}),format:{type:'json_object'}}});
  return {
    async respond(request,{signal,onRecord}={}) {
      if(closed) fail('closed');
      if(active) fail('busy');
      const q=input(request);
      if(deployed) productionTask(q.context,deployed.role);
      const streaming=responseFormat==='story-stream-v1';
      if(streaming && typeof onRecord!=='function') fail('invalid_request');
      if(signal?.aborted) fail('cancelled');
      const controller=new AbortController(),started=performance.now();
      const run={controller};active=run;
      let timer,abortHandler,firstText=null,streamedBytes=0;
      let streamedText='',pendingRecord='',sequence=0;
      const emitRecord=async text=>{
        if(controller.signal.aborted) fail('cancelled');
        if(++sequence>8) {controller.abort();fail('reply_too_large');}
        // This is bounded assistant output, NOT validated answer prose. The
        // Python record consumer owns parsing and must not display raw text.
        try {
          await onRecord({request_id:q.id,response_format:responseFormat,
            sequence:sequence-1,record:text});
        } catch {controller.abort();fail('cancelled');}
        if(controller.signal.aborted) fail('cancelled');
      };
      let rejectStop;
      const stopped=new Promise((_,reject)=>{rejectStop=reject;});
      const stop=code=>{rejectStop(new NotebookModelError(code));controller.abort();};
      run.stop=stop;
      timer=setTimeout(()=>stop('deadline'),q.deadline);
      abortHandler=()=>stop('cancelled');signal?.addEventListener('abort',abortHandler,{once:true});
      // A fresh context every time. The parent session, channel tools and files
      // are not even constructor inputs; no sessionId or shared prompt cache key.
      const context={systemPrompt,messages:[{role:'user',timestamp:Date.now(),content:[
        {type:'text',text:'Current notebook context (question data):\n'+q.context},
        {type:'image',mimeType:'image/png',data:q.image}]}],tools:[]};
      const work=(async()=>{
        const json=jsonMode && !streaming;
        let stream=modelRegistry.streamSimple(selected,context,{
          toolChoice:'none',reasoning,maxTokens:outputTokens,
          cacheRetention:'none',transport:'sse',maxRetries:0,timeoutMs:q.deadline,signal:controller.signal,
          ...(json?{onPayload:jsonPayload}:{})});
        let result=await consume(stream).catch(error=>{
          if(!json || firstText!==null || controller.signal.aborted ||
            (error instanceof NotebookModelError && error.code!=='incomplete_response')) throw error;
          jsonMode=false;
          stream=modelRegistry.streamSimple(selected,context,{
            toolChoice:'none',reasoning,maxTokens:outputTokens,
            cacheRetention:'none',transport:'sse',maxRetries:0,timeoutMs:q.deadline,signal:controller.signal});
          return consume(stream);
        });
        if(streaming) {
          // Never silently replace text which was already delivered early.
          if(result.text!==streamedText) fail('invalid_response');
          if(pendingRecord) await emitRecord(pendingRecord);
        }
        return {request_id:q.id,response_format:responseFormat,text:result.text,
          ...(evaluationIdentity?{[deployed?'production':'evaluation']:{...evaluationIdentity}}:{}),
          metrics:{elapsed_ms:Math.round(performance.now()-started),first_text_ms:firstText===null?null:Math.round(firstText),
            provider:selected.provider,model:selected.id,reasoning_requested:reasoning,
            requested_output_tokens:outputTokens,usage:result.usage}};
      })();
      async function consume(stream) {
        for await(const event of stream) {
          if(controller.signal.aborted) fail('cancelled');
          if(event.type==='toolcall_start' || event.type==='toolcall_delta' || event.type==='toolcall_end') {
            controller.abort();fail('tools_forbidden');
          }
          if(event.type==='text_delta') {
            if(typeof event.delta!=='string') fail('invalid_response');
            if(firstText===null) firstText=performance.now()-started;
            streamedBytes+=Buffer.byteLength(event.delta);
            if(streamedBytes>LIMITS.replyBytes) {controller.abort();fail('reply_too_large');}
            if(streaming) {
              streamedText+=event.delta;pendingRecord+=event.delta;
              while(pendingRecord.includes('\n')) {
                const at=pendingRecord.indexOf('\n')+1;
                const record=pendingRecord.slice(0,at);pendingRecord=pendingRecord.slice(at);
                await emitRecord(record);
              }
            }
          }
        }
        return completed(await stream.result(),selected);
      }
      // If a provider ignores cancellation, retain busy until it actually ends.
      // A caller timeout must not launch another paid request behind the first.
      run.finished=work.then(()=>{},()=>{}).finally(()=>{if(active===run) active=null;});
      try {return await Promise.race([work,stopped]);}
      catch(error) {if(error instanceof NotebookModelError) throw error;fail('provider_error');}
      finally {clearTimeout(timer);signal?.removeEventListener('abort',abortHandler);}
    },
    close(){closed=true;active?.stop('closed');return active?.finished ?? Promise.resolve();},
  };
}
