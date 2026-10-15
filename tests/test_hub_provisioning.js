// Regression: exercise the shipped provisioning function with only HTTP/UI boundaries stubbed.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../rathole-manager/ratholehub/ui/app.js'), 'utf8');
function definition(name) {
  const match = new RegExp('(?:async )?function '+name+'\\(').exec(source);
  assert.ok(match, 'missing '+name);
  const end = source.indexOf('\n}', match.index);
  return source.slice(match.index, end+2);
}
function context(options={}) {
  const calls=[], messages=[];
  const ctx={calls,messages, SERVERS:[{name:'iran',role:'iran',host:'192.0.2.1'},
    {name:'node',role:'node',host:'192.0.2.2'}],
    OVS:{iran:{nodes:[{name:'node',port:21001,inbound_port:8080}]},node:{services:[],backhaul_services:[],main_tunnel:'ws'}},
    toast:x=>messages.push(x),loadOv:()=>{},console,
    api:async(method,url,body)=>{
      calls.push({method,url,...body});
      if(body && body.action===options.failAction) return {status:200,j:{rc:1,err:'failed action'}};
      if(body && body.action==='status')return {status:200,j:{rc:0,out:JSON.stringify({public_ip:'192.0.2.1',ports:{},features:{frp:{configured:true,port:7443,transport:'quic'}},nodes:[{name:'node',port:21001,inbound_port:8080}]})}};
      let j={rc:0,out:''};
      if(url.includes('/nodeconnect/'))j={ok:true,name:'node',token:'11111111111111111111111111111111',inbound:'8080',remote_port:'21001',transport:'ws'};
      if(url.endsWith('/mainconnect'))j={ok:true,server:'panel.example:443',tls_hostname:'panel.example',control_path:'/'};
      if(url.endsWith('/frpconnect'))j={ok:true,host:'192.0.2.1',remote:'192.0.2.1:7443',port:7443,token:'22222222222222222222222222222222',transport:'quic'};
      if(url.endsWith('/kcpconnect'))j={ok:true,remote:'192.0.2.1:443',key:'33333333333333333333333333333333',profile:'balanced'};
      if(url.endsWith('/noiseconnect'))j={ok:true,remote:'192.0.2.1:2334',pubkey:'A'.repeat(43)+'=',pattern:'Noise_NK_25519_ChaChaPoly_BLAKE2s'};
      if(url.endsWith('/backhaulconnect'))j={ok:true,mode:'nginx_tls',remote_addr:'panel.example:443',transport:'wssmux',profile:'balanced',token:'44444444444444444444444444444444'};
      return {status:200,j};
    }};
  vm.createContext(ctx);
  for(const name of ['patchRequest','patchAction','patchNodeServer','provisionPatchCircuit']) {
    if(source.includes('function '+name+'(')) vm.runInContext(definition(name),ctx);
  }
  return ctx;
}
function action(c,name) { return c.calls.find(x=>x.action===name&&x.url.includes('/node/')) || c.calls.find(x=>x.action===name); }
for (const [carrier,nodeAction] of [['ws','plain_off'],['kcp','kcp_on'],['plain','plain_on'],['noise','noise_on']]) {
  test(carrier+' configures the node carrier',async()=>{
    const c=context(); await c.provisionPatchCircuit('iran','node',carrier,8080,{});
    assert.ok(action(c,nodeAction),nodeAction+' was never sent');
  });
}
test('FRP uses its shared credential, actual listener and Iran backend port',async()=>{
  const c=context(); await c.provisionPatchCircuit('iran','node','frp',8080,{});
  const frp=action(c,'frp_on');
  assert.equal(frp.args.token,'22222222222222222222222222222222');
  assert.equal(frp.args.remote,'192.0.2.1:7443');
  assert.equal(frp.args.remote_port,'21001');
  assert.equal(action(c,'add_svc').args.remote_port,'21001');
});
test('FRP+GRE configures both interfaces and dials FRP over GRE',async()=>{
  const c=context();await c.provisionPatchCircuit('iran','node','frp_gre',8080,{});
  assert.equal(c.calls.filter(x=>x.action==='gre_on').length,2);
  assert.equal(action(c,'frp_on').args.remote,'10.10.10.1:7443');
});
test('GRE routes the Rathole control connection through its tunnel',async()=>{
  const c=context();await c.provisionPatchCircuit('iran','node','gre',8080,{});
  assert.equal(c.calls.filter(x=>x.action==='gre_on').length,2);
  assert.ok(action(c,'plain_on'),'GRE must configure a control carrier');
  assert.equal(c.calls.find(x=>x.action==='plain_on'&&x.url.includes('/node/')).args.remote,'10.10.10.1:8880');
});
test('Backhaul records service in the independent mux lane',async()=>{
  const c=context();await c.provisionPatchCircuit('iran','node','backhaul',8080,{});
  assert.ok(action(c,'add_bh_svc')); assert.equal(action(c,'add_svc'),undefined);
});
test('a failed command stops provisioning and cannot report success',async()=>{
  const c=context({failAction:'add_svc'});
  const result=await c.provisionPatchCircuit('iran','node','frp',8080,{});
  assert.equal(result,false);assert.equal(action(c,'frp_on'),undefined);
  assert.equal(c.messages.some(x=>x.includes('با موفقیت')),false);
});
test('an unmatched service cannot silently select the first node',async()=>{
  const c=context();const result=await c.provisionPatchCircuit('iran','unknown','ws',8080,{});
  assert.equal(result,false);assert.equal(c.calls.length,0);
});
test('quick carrier modal actually provisions the selected configuration',async()=>{
  const c=context();let callback,called=false;
  Object.assign(c,{buildWiringModel:()=>({circuits:[{iran:'iran',node:'node',backendPort:8080}]}),formModal:(title,fields,cb)=>{callback=cb;},closeModal:()=>{},showCircuitInspector:()=>{},drawPatchBoard:()=>{},highlightCircuit:()=>{},applyPatchConnection:async()=>{called=true;return true;}});
  vm.runInContext(definition('quickCarrierModal'),c);
  c.quickCarrierModal('iran','node','ws');await callback({carrier:'kcp',profile:'balanced'});
  assert.equal(called,true);
});
const uiContext=()=>{
 const c=context();
 Object.assign(c,{PATCH_CUSTOM_CIRCUITS:[],drawPatchBoard:()=>{},highlightCircuit:()=>{},resetCircuit:()=>{},$:()=>null,document:{querySelector:()=>null},setTimeout:()=>{},buildWiringModel:()=>({circuits:[{id:'c_iran_node',iran:'iran',node:'node',nodeServer:'node'}]})});
 return c;
};
test('REST API outage is labeled as Agent connectivity, not SSH',()=>{
  const c=context();
  const page={innerHTML:''}, strip={innerHTML:''};
  c.SERVERS=[{name:'hub',role:'iran',transport:'api',api_url:'http://127.0.0.1:8089'}];
  c.OVS={hub:{reachable:false,error:'Agent connection error: Connection refused'}};
  Object.assign(c,{
    t:key=>key, h:x=>String(x??''), icon:()=>'', ovDotCls:()=>'',
    $:id=>id==='page'?page:(id==='hubstrip'?strip:null),
    fnd:name=>c.SERVERS.find(s=>s.name===name)||{},
    nodeTunnelStatus:()=>null, latestVer:()=>'',
    HUBST:{services:{},uptime:1}, fmtDur:()=>'', fmtGB:()=>'',
  });
  vm.runInContext(definition('headBadges'),c);
  assert.match(c.headBadges('hub',c.OVS.hub),/no_agent/);
  assert.doesNotMatch(c.headBadges('hub',c.OVS.hub),/no_ssh/);
  vm.runInContext(definition('renderServerPage'),c);
  c.renderServerPage('hub');
  assert.match(page.innerHTML,/agent_help/);
  assert.doesNotMatch(page.innerHTML,/ssh-copy-id|ssh_help/);
  vm.runInContext(definition('updateHubStrip'),c);
  c.updateHubStrip();
  assert.doesNotMatch(strip.innerHTML,/SSH/);
});
test('API server can edit its URL without SSH fields',async()=>{
  const c=context(); let fields,save;
  c.SERVERS=[{name:'hub',role:'iran',transport:'api',api_url:'http://127.0.0.1:8089'}];
  Object.assign(c,{fnd:name=>c.SERVERS.find(s=>s.name===name),formModal:(title,f,cb)=>{fields=f;save=cb;},t:key=>key,api:async(method,url,body)=>{c.calls.push({method,url,body});return {status:200,j:{ok:true}};},closeModal:()=>{},loadAll:()=>{}});
  const start=source.indexOf('function editServer('), end=source.indexOf('\nasync function savePw(',start);
  vm.runInContext(source.slice(start,end),c);
  c.editServer('hub');
  assert.deepEqual(Array.from(fields,f=>f.id),['api_url','api_token']);
  await save({api_url:'http://192.0.2.5:8089',api_token:''});
  assert.deepEqual(JSON.parse(JSON.stringify(c.calls[0])),{method:'PUT',url:'api/servers/hub',body:{api_url:'http://192.0.2.5:8089'}});
});
test('failed provisioning cannot optimistically change the wiring model',async()=>{
 const c=uiContext();c.provisionPatchCircuit=async()=>false;
 vm.runInContext(definition('applyPatchConnection'),c);
 assert.equal(await c.applyPatchConnection('iran','node','frp',8080,null,null,{}),false);
 assert.equal(c.OVS.iran.nodes[0].transport,undefined);
 assert.equal(c.PATCH_CUSTOM_CIRCUITS.length,0);
});
test('disconnect actually removes the Iran service and the peer service',async()=>{
 const c=uiContext();vm.runInContext(definition('disconnectCircuit'),c);
 await c.disconnectCircuit('c_iran_node');
 assert.ok(action(c,'rm_node'));assert.ok(action(c,'rm_svc'));
});
test('HTTP failures stop the sequence before any service is added',async()=>{
 const c=context();c.api=async()=>({status:400,j:{error:'invalid fields'}});
 assert.equal(await c.provisionPatchCircuit('iran','node','ws',8080,{}),false);
 assert.equal(c.messages.some(x=>x.includes('✓')),false);
});
test('invalid GRE host addresses are rejected before mutating either server',async()=>{
 const c=context();assert.equal(await c.provisionPatchCircuit('iran','node','gre',8080,{gre_ip:'10.10.10.0'}),false);
 assert.equal(c.calls.filter(x=>x.action && x.action!=='status').length,0);
});
test('fresh node state is initialized before applying its first service',async()=>{
 const c=context();let initialized=false;
 const boundary=c.api;
 c.api=async(m,p,b)=>{
   if(b && b.action==='set_main')initialized=true;
   if(b && b.action==='add_svc'&&!initialized)return {status:200,j:{rc:1,err:'node.env peyda nashod'}};
   return boundary(m,p,b);
 };
 const result=await c.provisionPatchCircuit('iran','node','frp',8080,{});
 assert.ok(result,'node provisioning stopped before initialization');
 assert.ok(c.calls.findIndex(x=>x.action==='set_main') < c.calls.findIndex(x=>x.action==='add_svc'));
});
