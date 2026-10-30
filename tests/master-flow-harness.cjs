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
// Follow the actual automatic-stop wire into the exported HA action node.
// This adapter covers static service configuration, not the HA websocket node runtime.
function automaticStopActions(payloads) {
  const f=fixture();
  for (const value of payloads) f.input(value);
  return f.sent.filter(e=>e.outputs[1]).flatMap(e=>config.wires[1].map(id=>{
    const n=flow.find(n=>n.id===id);
    if (n.type!=='api-call-service'||n.dataType!=='json') throw Error('Unsupported stop route');
    const action={service:n.action,data:JSON.parse(n.data||'{}')};
    if(n.entityId.length) {
      if(n.entityId.length!==1)throw Error('Expected one target');
      action.target={entity_id:n.entityId[0]};
    }
    return action;
  }));
}
module.exports={fixture,flow,config,automaticStopActions};
if(require.main===module)process.stdout.write(JSON.stringify(automaticStopActions(JSON.parse(process.argv[2]))));
