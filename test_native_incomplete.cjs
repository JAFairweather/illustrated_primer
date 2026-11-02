const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'xochitl/herdRespond.qmd'),'utf8');
function definition(name){
 const start=source.indexOf(`function ${name}(`);
 const tokens=['\n\t\t\t\tfunction ','\n\t\t\t\tText {'];
 return source.slice(start,Math.min(...tokens.map(t=>source.indexOf(t,start+1)).filter(i=>i>=0)));
}
function reopened(){
 const c=vm.createContext({herdMine:false,herdPage:'p',herdIncompletePage:'',herdIncompleteRequest:'',herdIncompleteDismissed:'',
   navigator:{herdJob:null,herdState:'',herdNote:'',herdUuid:x=>x},root:{inSuspend:false},sceneView:{document:{id:'d'},isLoading:false}});
 vm.runInContext(['herdStatusLabel','herdObserveIncomplete','herdDismissIncomplete','herdNewQuestionRequest'].map(definition).join('\n'),c);return c;
}
const hint={accepted:true,incomplete_reply:{request:'notebook-'+'a'.repeat(32)}};
const c=reopened();c.herdObserveIncomplete(hint,'p','d');
assert.equal(c.herdStatusLabel(),'Reply may be incomplete — tap to dismiss');assert.equal(c.navigator.herdJob,null);
assert(c.herdDismissIncomplete());assert.equal(c.herdStatusLabel(),'New question — keep previous reply');
assert.equal(c.herdNewQuestionRequest(),hint.incomplete_reply.request);
c.herdObserveIncomplete(hint,'p','d');assert.equal(c.herdStatusLabel(),'New question — keep previous reply','dismiss once in current view');
c.herdPage='another';assert.equal(c.herdNewQuestionRequest(),'','dismissal cannot transfer to another page');
c.herdObserveIncomplete(hint,'another','d');assert.equal(c.herdIncompleteDismissed,'');
const next=reopened();next.herdObserveIncomplete(hint,'p','d');
assert.match(next.herdStatusLabel(),/incomplete/,'fresh view restores warning from existing attempt');
next.herdObserveIncomplete({accepted:true,incomplete_reply:null},'p','d');assert.equal(next.herdStatusLabel(),'RESPOND');
for(const change of ['page','doc','active-job','suspend','loading','malformed','unaccepted']){
 const s=reopened();let h=structuredClone(hint);
 if(change==='page')s.herdPage='other';
 if(change==='doc')s.sceneView.document.id='other';
 if(change==='active-job')s.navigator.herdJob={};
 if(change==='suspend')s.root.inSuspend=true;
 if(change==='loading')s.sceneView.isLoading=true;
 if(change==='malformed')h.incomplete_reply.request='raw arbitrary prose';
 if(change==='unaccepted')h.accepted=false;
 s.herdObserveIncomplete(h,'p','d');assert.equal(s.herdIncompleteRequest,'',change);
}
console.log('Incomplete reply: read-only warning restored on fresh view; no resume, edits, stale-page hint or repeated dismissal.');
