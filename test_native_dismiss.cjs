// Execute the real failure branch with QString-like strict assignment.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname+'/xochitl/herdRespond.qmd','utf8');
const branch = source.match(/if \(herdButton\.herdMine && navigator\.herdState === "failed"\) \{([\s\S]*?)\n\s*\}/)[1];
for (const job of [null, {}, {doc:'d',page:'p',path:'',live:true}, {request:'notebook-123'}]) {
  let dismissed=0,value='';
  const button={set herdIncompleteDismissed(v){assert.equal(typeof v,'string');value=v;}};
  vm.runInNewContext('(function(){'+branch+'})()', {
    herdButton:button,navigator:{herdJob:job,herdDismissFailure(){dismissed++;}}
  });
  assert.equal(dismissed,1);
  assert.equal(value,job?.request||'');
}
console.log('Dismiss failed sends with or without a request ID; no resend.');
