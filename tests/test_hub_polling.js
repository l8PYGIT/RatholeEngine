const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync(require('node:path').join(__dirname,'../rathole-manager/ratholehub/ui/app.js'),'utf8');
// Extract only the polling function to avoid DOM or application startup.
const fn=src.match(/const OV_PENDING=new Set\(\);\nasync function loadOv\(n\)\{.*\}\n/)[0];
test('overlapping overview requests coalesce and retry after error',async()=>{
 let resolve,calls=0;
 const context={Set,OVS:{},onOv(){},api(){calls++;return new Promise(r=>resolve=r)}};
 vm.createContext(context);vm.runInContext(fn,context);
 const first=context.loadOv('node');await context.loadOv('node');assert.equal(calls,1);
 resolve({j:{reachable:true}});await first;assert.equal(context.OVS.node.reachable,true);
 context.api=async()=>{throw new Error('offline')};await assert.rejects(context.loadOv('node'));
 context.api=async()=>({j:{reachable:true}});await context.loadOv('node');
 assert.equal(context.OVS.node.reachable,true);
});
