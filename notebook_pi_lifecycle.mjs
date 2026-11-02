/** Register notebook resources on the EXISTING Pi extension's lifecycle.
 * Importing does nothing. The owner supplies a fixed prompt/private socket.
 * No configuration reads, login handling, new process, tools or Nvoy consumer.
 */
import {createNotebookResponder,evaluationSettings,productionSettings} from './notebook_pi_responder.mjs';
import {serveNotebookSocket} from './notebook_pi_socket.mjs';
import {basename} from 'node:path';

export function registerNotebookResponder(pi,{socketPath,systemPrompt,onStatus=()=>{},fixedModel,responseFormat='semantic-v1',evaluation,production},
  {createResponder=createNotebookResponder,listen=serveNotebookSocket}={}) {
  if(typeof pi?.on!=='function' || typeof onStatus!=='function')throw Error('Notebook lifecycle unavailable');
  if(!['semantic-v1','story-panel-v1','story-stream-v1','role-eval-v1','role-production-v1'].includes(responseFormat))throw Error('Invalid notebook response format');
  const candidate=evaluationSettings(responseFormat,evaluation);
  const deployed=productionSettings(responseFormat,production);
  if(candidate && (typeof socketPath!=='string' || basename(socketPath)!=='notebook-eval.sock' || fixedModel===undefined)) {
    throw Error('Role evaluation requires a fixed model and evaluation-only socket');
  }
  if(deployed && (typeof socketPath!=='string' || basename(socketPath)!==`notebook-${deployed.role}.sock` || fixedModel===undefined)) {
    throw Error('Production role requires a fixed model and role-specific socket');
  }
  // Optional owner configuration, never a notebook request parameter. Resolve
  // only through the existing trusted registry; no new auth/provider or fallback.
  if(fixedModel!==undefined && (!fixedModel || typeof fixedModel!=='object' || Array.isArray(fixedModel) ||
    Object.keys(fixedModel).sort().join(',')!=='id,provider' || fixedModel.provider!=='openai-codex' ||
    typeof fixedModel.id!=='string' || !/^[\w.\-/\[\]]{1,128}$/.test(fixedModel.id))) {
    throw Error('Invalid fixed notebook model');
  }
  const selection=fixedModel===undefined?null:Object.freeze({...fixedModel});
  let generation=0,current=null,chain=Promise.resolve(),session=false,disposed=false;
  const report=state=>{try{onStatus(state);}catch{/* status is not control authority */}};
  function replace(snapshot){
    const ticket=++generation;
    // Cancel immediately, even if the previous bind/close is still pending.
    if(current)current.responder.close();
    chain=chain.then(async()=>{
      if(current){
        const previous=current;
        await previous.host.close(); // includes draining the old provider
        if(current===previous)current=null;
      }
      if(ticket!==generation || !snapshot){
        if(ticket===generation)report('stopped');
        return;
      }
      const entry={responder:null,host:null};
      try{
        const model=selection?snapshot.modelRegistry?.find?.(selection.provider,selection.id):snapshot.model;
        if(selection && (model?.provider!==selection.provider || model?.id!==selection.id)) {
          throw Error('Fixed notebook model unavailable');
        }
        entry.responder=createResponder({modelRegistry:snapshot.modelRegistry,model,systemPrompt,responseFormat,
          ...(candidate?{evaluation:candidate}:{}),...(deployed?{production:deployed}:{})});
        current=entry;
        entry.host=await listen({socketPath,responder:entry.responder});
        if(ticket!==generation || disposed){
          await entry.host.close();
          if(current===entry)current=null;
          return;
        }
        report('ready');
      }catch{
        if(entry.host)await entry.host.close();
        else if(entry.responder)await entry.responder.close();
        if(current===entry)current=null;
        report('unavailable');
      }
    }).catch(()=>{report('unavailable');});
    return chain;
  }
  // Registry/model only: never capture session messages, channel tools or ctx.
  const snapshot=(ctx,model=ctx?.model)=>({modelRegistry:ctx?.modelRegistry,model});
  const detach=[
    pi.on('session_start',(_event,ctx)=>{
      if(disposed)return;
      session=true;void replace(snapshot(ctx));
    }),
    pi.on('model_select',(event,ctx)=>{
      if(disposed || !session)return;
      void replace(snapshot(ctx,event.model));
    }),
    pi.on('session_shutdown',()=>{
      if(disposed)return;
      session=false;void replace(null);
    }),
  ];
  return {
    // Optional observation for tests/deployment readiness. Pi's own event
    // hooks never await a hanging notebook provider and block the chat UI.
    settled(){return chain;},
    close(){
      if(disposed)return chain;
      disposed=true;session=false;
      for(const remove of detach)if(typeof remove==='function')remove();
      return replace(null);
    },
  };
}
