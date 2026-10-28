const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const flow = JSON.parse(fs.readFileSync(path.join(__dirname,'../NodeRed/bender_strategy_master.json')));
const config = flow.find(n=>n.id==='bender_master_lb_rate_limit');
function fixture() {
  let now=10000, next=1;
  const timers=new Map(), sent=[], storage=new Map();
  const node={status(){},send(outputs){sent.push({at:now, outputs:structuredClone(outputs)});}};
  const sandbox={node,msg:null,context:{get:k=>storage.get(k),set:(k,v)=>storage.set(k,v)},Date:{now:()=>now},Number,String,Math,
    setTimeout(fn,ms){const id=next++;timers.set(id,{fn,at:now+ms});return id;},
    clearTimeout(id){timers.delete(id);}};
  const context=vm.createContext(sandbox);
  const script=new vm.Script('(function(){'+config.func+'})()');
  new vm.Script(config.initialize).runInContext(context);
  return {sent,timers,
    input(payload){sandbox.node={...node};sandbox.msg={_msgid:'test',payload};script.runInContext(context);},
    advance(ms){const end=now+ms;for(;;){const due=[...timers].filter(([,x])=>x.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}now=end;},
    close(){new vm.Script(config.finalize).runInContext(context);}
  };
}
test('HA event carries payload and the stop output directly reaches the stop script',()=>{
  const trigger=flow.find(n=>n.id==='bender_master_lb_sensor_trigger');
  assert.ok(trigger.outputProperties.some(p=>p.property==='payload'&&p.valueType==='entityState'));
  assert.deepEqual(config.wires,[['bender_master_fetch_strategy'],['bender_master_link_uit']]);
  assert.equal(flow.find(n=>n.id==='bender_master_link_uit').action,'script.bender_stop_charging');
});
test('1000 rising updates retain only the latest refresh, never a FIFO backlog',()=>{
  const f=fixture();f.input('6');
  for(let i=0;i<1000;i++)f.input(String(7+i/1000*9));
  assert.equal(f.sent.length,1);assert.equal(f.timers.size,1);
  f.advance(5000);assert.equal(f.sent.length,2);
  assert.equal(f.sent[1].outputs[0].payload,String(7+999/1000*9));
  f.advance(600000);assert.equal(f.sent.length,2);
});
test('a reduction bypasses the five-second throttle',()=>{
  const f=fixture();f.input('16');f.advance(10);f.input('10');
  assert.equal(f.sent.length,2);assert.equal(f.sent[1].at,10010);
});
test('stop cancels a pending raise and never allows it to reappear',()=>{
  const f=fixture();f.input('6');f.input('16');f.advance(20);f.input('0');
  assert.ok(f.sent.at(-1).outputs[1]);assert.equal(f.sent.at(-1).outputs[0],null);
  assert.equal(f.timers.size,0);f.advance(30000);assert.equal(f.sent.length,2);
});
test('all subminimum currents stop; repeated low values do not flood services',()=>{
  const f=fixture();f.input('16');f.input('5.9');f.input('3.5');f.input('0');
  assert.equal(f.sent.length,2);assert.ok(f.sent[1].outputs[1]);
});
test('missing, empty and nonfinite readings take the immediate stop path',()=>{
  for(const value of [undefined,null,'','unknown','unavailable','NaN','Infinity']) {
    const f=fixture();f.input('6');f.input('16');f.input(value);
    assert.ok(f.sent.at(-1).outputs[1]);assert.equal(f.timers.size,0);
  }
});
test('redeploy cancels pending work',()=>{
  const f=fixture();f.input('6');f.input('16');f.close();f.advance(10000);
  assert.equal(f.sent.length,1);
});
test('Direct has a periodic recheck that verifies the current strategy',()=>{
  const f=JSON.parse(fs.readFileSync(path.join(__dirname,'../NodeRed/bender_strategy_direct.json')));
  const inject=f.find(n=>n.id==='bender_direct_retry'),gate=f.find(n=>n.id==='bender_direct_is_active');
  assert.equal(inject.repeat,'5');assert.equal(gate.halt_if,'Direct');
  assert.deepEqual(gate.wires,[['bender_direct_start'],[]]);
});
