/** Owner-only local IPC host for notebook_pi_responder; opt-in, no autostart.
 * Authentication is the OS user/private directory, NOT a claim about which
 * same-user process connects. No network listener, new credential or replay DB.
 */
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import {NotebookModelError} from './notebook_pi_responder.mjs';

export const MAX_WIRE=4_100_000;
function privateParent(socketPath){
  if(typeof socketPath!=='string' || !path.isAbsolute(socketPath) || path.normalize(socketPath)!==socketPath ||
    Buffer.byteLength(socketPath)>100) throw Error('Notebook socket path is invalid');
  const parent=path.dirname(socketPath),info=fs.lstatSync(parent);
  if(!info.isDirectory() || info.isSymbolicLink() || info.uid!==process.getuid() || (info.mode&0o077)) throw Error('Notebook socket parent must be owner-only');
  let current=parent;
  while(current!==path.dirname(current)) {
    if(fs.lstatSync(current).isSymbolicLink())throw Error('Notebook socket ancestors must not be symlinks');
    current=path.dirname(current);
  }
  // Never remove an existing socket/file: its process may still own it.
  try {fs.lstatSync(socketPath);} catch(e) {if(e.code==='ENOENT')return;throw e;}
  throw Error('Notebook socket already exists');
}

export async function serveNotebookSocket({socketPath,responder}){
  privateParent(socketPath);
  if(typeof responder?.respond!=='function' || typeof responder?.close!=='function')throw Error('Notebook responder is unavailable');
  const connections=new Set();
  const server=net.createServer(socket=>{
    connections.add(socket);
    let chunks=[],size=0,started=false,done=false,requestId=null;
    const controller=new AbortController();
    const send=value=>{if(done)return;done=true;socket.end(JSON.stringify(value)+'\n');};
    const failure=code=>send({request_id:requestId,error:code});
    socket.setTimeout(5000);
    socket.on('error',()=>controller.abort());
    socket.on('close',()=>{connections.delete(socket);controller.abort();});
    socket.on('timeout',()=>{controller.abort();failure('deadline');});
    socket.on('data',chunk=>{
      if(done)return;
      if(started){controller.abort();failure('invalid_request');return;}
      size+=chunk.length;
      if(size>MAX_WIRE){failure('request_too_large');return;}
      chunks.push(chunk);
      if(!chunk.includes(10))return;
      const raw=Buffer.concat(chunks);chunks=[];
      if(raw.indexOf(10)!==raw.length-1){failure('invalid_request');return;}
      let request;
      try {request=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}
      catch {failure('invalid_request');return;}
      if(typeof request?.request_id==='string' && /^notebook-[0-9a-f]{32}$/.test(request.request_id))requestId=request.request_id;
      started=true;
      // The core validates this deadline; socket gets a small reply-flush margin.
      socket.setTimeout(Number.isInteger(request?.deadline_ms) && request.deadline_ms>0 && request.deadline_ms<=90000 ? request.deadline_ms+2000 : 2000);
      const onRecord=value=>new Promise((resolve,reject)=>{
        if(done || socket.destroyed || controller.signal.aborted) {
          reject(new NotebookModelError('cancelled'));return;
        }
        socket.write(JSON.stringify(value)+'\n',error=>error?reject(error):resolve());
      });
      Promise.resolve().then(()=>responder.respond(request,{signal:controller.signal,onRecord}))
        .then(send,error=>failure(error instanceof NotebookModelError ? error.code : 'provider_error'));
    });
  });
  await new Promise((resolve,reject)=>{
    server.once('error',reject);
    server.listen(socketPath,()=>{server.removeListener('error',reject);resolve();});
  });
  const identity=fs.lstatSync(socketPath);
  fs.chmodSync(socketPath,0o600);
  server.on('error',()=>{responder.close();for(const socket of connections)socket.destroy();});
  let closing;
  return {
    close(){
      if(closing)return closing;
      const drained=Promise.resolve(responder.close());
      for(const socket of connections)socket.destroy();
      const listenerClosed=new Promise((resolve,reject)=>server.close(error=>{
        try {
          // Node normally removes its socket on close. Only remove a leftover
          // with our exact identity, never a replacement file or another owner.
          let info;try{info=fs.lstatSync(socketPath);}catch(e){if(e.code!=='ENOENT')throw e;}
          if(info && info.isSocket() && info.ino===identity.ino && info.dev===identity.dev && info.uid===process.getuid())fs.unlinkSync(socketPath);
          if(error)reject(error);else resolve();
        }catch(e){reject(e);}
      }));
      // A session/model replacement must not start another paid call while an
      // abort-ignoring provider from this listener is still alive.
      closing=Promise.all([listenerClosed,drained]).then(()=>{});
      return closing;
    },
  };
}
