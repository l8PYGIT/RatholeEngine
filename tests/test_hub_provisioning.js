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
  let noiseActive=options.noiseActive!==false;
  const ctx={calls,messages, SERVERS:[{name:'iran',role:'iran',host:'192.0.2.1'},
    {name:'node',role:'node',host:'192.0.2.2'}],
    OVS:{iran:{nodes:[{name:'node',port:21001,inbound_port:8080}]},node:{services:[],backhaul_services:[],main_tunnel:'ws'}},
    toast:x=>messages.push(x),loadOv:()=>{},console,URL:globalThis.URL,
    api:async(method,url,body)=>{
      calls.push({method,url,...body});
      if(body && body.action===options.failAction) return {status:200,j:{rc:1,err:'failed action'}};
      if(body && body.action==='noise_on' && url.includes('/iran/') && !options.noiseStartFails) noiseActive=true;
      if(body && body.action==='status')return {status:200,j:{rc:0,out:JSON.stringify({public_ip:options.detectedIranIp||'192.0.2.1',ports:{},features:{frp:{configured:true,active:options.frpActive!==false,port:7443,transport:'quic'},noise:{configured:!!options.noiseConfigured,active:noiseActive,port:2334}},nodes:[{name:'node',port:21001,inbound_port:8080,transport:options.oldLane||'ws'}]})}};
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
  for(const name of ['patchRequest','patchAction','patchNodeServer','serverPublicIp','provisionPatchCircuit']) {
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
test('unreachable GRE peer leaves the working carrier selected',async()=>{
  const c=context({failAction:'gre_probe',oldLane:'backhaul'});
  assert.equal(await c.provisionPatchCircuit('iran','node','gre',8080,{}),false);
  assert.equal(action(c,'plain_on'),undefined);
  assert.equal(action(c,'frp_node_on'),undefined);
  assert.equal(action(c,'backhaul_node_off'),undefined);
});
test('FRP releases the Iran backend only after preparing the node service',async()=>{
  const c=context();await c.provisionPatchCircuit('iran','node','frp',8080,{});
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.indexOf('add_svc')<actions.indexOf('frp_node_on'));
});
test('unregistered FRP proxy reports failure and restores WebSocket',async()=>{
  const c=context({failAction:'frp_ready'});
  assert.equal(await c.provisionPatchCircuit('iran','node','frp',8080,{}),false);
  assert.ok(action(c,'frp_off'));
  assert.ok(action(c,'frp_node_off'));
});
test('inactive FRP server is restarted before changing the node carrier',async()=>{
  const c=context({frpActive:false});
  await c.provisionPatchCircuit('iran','node','frp',8080,{});
  const start=c.calls.find(x=>x.action==='frp_on'&&x.url.includes('/iran/'));
  assert.ok(start);
  assert.ok(c.calls.indexOf(start)<c.calls.findIndex(x=>x.action==='frp_node_on'));
});
test('Noise starts an inactive server and registers the service after node configuration',async()=>{
  const c=context({noiseConfigured:true,noiseActive:false});
  await c.provisionPatchCircuit('iran','node','noise',8080,{});
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.includes('noise_on'));
  assert.ok(actions.lastIndexOf('noise_node_on') > actions.lastIndexOf('add_svc'));
  assert.ok(actions.lastIndexOf('noise_node_on') < actions.lastIndexOf('noise_on'));
});
test('failed Noise client restores the previous Iran route',async()=>{
  const c=context({failAction:'noise_on',noiseConfigured:true,noiseActive:true});
  assert.equal(await c.provisionPatchCircuit('iran','node','noise',8080,{}),false);
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.includes('noise_node_on'));
  assert.ok(actions.lastIndexOf('noise_node_off') > actions.lastIndexOf('noise_on'));
  assert.ok(actions.lastIndexOf('noise_off') > actions.lastIndexOf('noise_on'));
});
test('inactive Noise daemon stops before switching the service',async()=>{
  const c=context({noiseConfigured:true,noiseActive:false,noiseStartFails:true});
  assert.equal(await c.provisionPatchCircuit('iran','node','noise',8080,{}),false);
  assert.equal(action(c,'noise_node_on'),undefined);
  assert.equal(c.messages.some(x=>x.includes('rathole-noise')),true);
});
test('manual Iran IP is used for the Noise connection',async()=>{
  const c=context();
  await c.provisionPatchCircuit('iran','node','noise',8080,{iran_ip:'203.0.113.9'});
  const nodeNoise=c.calls.find(x=>x.action==='noise_on'&&x.url.includes('/node/'));
  assert.equal(nodeNoise.args.remote,'203.0.113.9:2334');
});
test('manual Iran IP is used for FRP instead of the detected SSH address',async()=>{
  const c=context();
  await c.provisionPatchCircuit('iran','node','frp',8080,{iran_ip:'203.0.113.9'});
  assert.equal(action(c,'frp_on').args.remote,'203.0.113.9:7443');
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
test('FRP selection opens transport settings before changing the node',async()=>{
  const c=context();
  const selector={value:'frp'};
  let opened=null;
  Object.assign(c,{$:()=>selector,t:key=>key,quickCarrierModal:(...args)=>{opened=args;},
    confirm:()=>{throw new Error('FRP must open settings before confirmation');}});
  vm.runInContext(definition('setIranNodeCarrier'),c);
  await c.setIranNodeCarrier('iran','node','frp','ws');
  assert.deepEqual(Array.from(opened),['iran','node','frp']);
  assert.equal(selector.value,'ws');
  assert.equal(c.calls.length,0);
});
test('unknown peer cannot change the Iran carrier alone',async()=>{
  const c=context(); c.SERVERS=[c.SERVERS[0],{name:'node-a',role:'node',host:'192.0.2.2'},{name:'node-b',role:'node',host:'192.0.2.3'}];
  let opened=null;
  Object.assign(c,{$:()=>({value:'noise'}),t:key=>key,confirm:()=>true,
    quickCarrierModal:(...args)=>{opened=args;}});
  vm.runInContext(definition('setIranNodeCarrier'),c);
  await c.setIranNodeCarrier('iran','node','noise','ws');
  assert.deepEqual(Array.from(opened),['iran','node','noise']);
  assert.equal(c.calls.length,0);
});
test('Iran Noise and Backhaul node buttons open synchronized carrier setup',()=>{
  const c=context();let submit,opened=[];
  Object.assign(c,{t:key=>key,formModal:(_title,_fields,cb)=>{submit=cb;},closeModal:()=>{},
    quickCarrierModal:(...args)=>opened.push(args)});
  vm.runInContext(definition('noiseNode'),c);
  vm.runInContext(definition('bhNode'),c);
  c.noiseNode('iran','on');submit({name:'node'});
  c.bhNode('iran','on');submit({name:'node'});
  assert.deepEqual(opened.map(x=>x[2]),['noise','backhaul']);
  assert.equal(c.calls.length,0);
});
test('foreign-node FRP button uses the synchronized circuit setup',()=>{
  const c=context();let fields,submit,opened;
  Object.assign(c,{t:key=>key,iranServers:()=>[c.SERVERS[0]],formModal:(_title,f,cb)=>{fields=f;submit=cb;},
    closeModal:()=>{},quickCarrierModal:(...args)=>{opened=args;},$:()=>null});
  vm.runInContext(definition('frpOnNode'),c);
  c.frpOnNode('node');
  assert.ok(fields.some(f=>f.id==='service'));
  submit({iran:'iran',service:'node'});
  assert.deepEqual(Array.from(opened),['iran','node','frp']);
  assert.equal(c.calls.length,0);
});
test('new wiring form forwards manual public IPs',async()=>{
  const c=context(); let fields,submit,extra;
  Object.assign(c,{formModal:(_title,f,cb)=>{fields=f;submit=cb;},closeModal:()=>{},
    patchNodeServer:()=>({name:'node'}),applyPatchConnection:async(_ir,_node,_carrier,_port,_p1,_p2,e)=>{extra=e;}});
  vm.runInContext(definition('promptPatchProtocol'),c);
  c.promptPatchProtocol('iran','node',8080,null,null);
  assert.ok(fields.some(f=>f.id==='iran_ip'));
  assert.ok(fields.some(f=>f.id==='node_ip'));
  await submit({carrier:'noise',port:'8080',iran_ip:'203.0.113.9',node_ip:'203.0.113.10'});
  assert.equal(extra.iran_ip,'203.0.113.9');
  assert.equal(extra.node_ip,'203.0.113.10');
});
test('UI prefers a public inventory address over a private detected address',()=>{
  const c=context();
  assert.equal(c.serverPublicIp(c.SERVERS[0],{status:{public_ip:'10.1.2.3'}}),'192.0.2.1');
  assert.equal(c.serverPublicIp({name:'iran',host:'10.1.2.3'},{status:{public_ip:'203.0.113.9'}}),'203.0.113.9');
});
test('GRE provisioning does not use a private auto-detected Iran address',async()=>{
  const c=context({detectedIranIp:'10.1.2.3'});
  await c.provisionPatchCircuit('iran','node','gre',8080,{});
  const nodeGre=c.calls.find(x=>x.action==='gre_on'&&x.url.includes('/node/'));
  assert.equal(nodeGre.args.remote_ip,'192.0.2.1');
});
test('wiring model flags mismatched carriers and ignores stale optimistic status',()=>{
  const c=context();
  c.OVS.iran.nodes[0].transport='noise';
  c.OVS.node.main_tunnel='ws';
  c.OVS.node.services=[{name:'node',inbound:8080}];
  c.PATCH_CUSTOM_CIRCUITS=[{id:'c_iran_node',iran:'iran',node:'node',carrier:'noise',status:'ok'}];
  vm.runInContext(definition('buildWiringModel'),c);
  const circuit=c.buildWiringModel().circuits[0];
  assert.equal(circuit.status,'warn');
  assert.equal(circuit.carrier,'noise');
  assert.equal(circuit.nodeCarrier,'ws');
});
test('wiring model does not claim a live circuit without a successful health probe',()=>{
  const c=context(); c.PATCH_CUSTOM_CIRCUITS=[];
  vm.runInContext(definition('buildWiringModel'),c);
  assert.equal(c.buildWiringModel().circuits[0].status,'warn');
  c.OVS.iran.health={nodes:{node:'ok'}};
  assert.equal(c.buildWiringModel().circuits[0].status,'ok');
  c.OVS.node.reachable=false;
  assert.equal(c.buildWiringModel().circuits[0].status,'warn');
});
test('an Iran carrier cannot be disabled while a node still uses it',async()=>{
  const c=context();c.OVS.iran.nodes[0].transport='noise';
  let disabled=0;
  Object.assign(c,{run:async()=>{disabled++;}});
  vm.runInContext(definition('disableIranCarrier'),c);
  await c.disableIranCarrier('iran','noise');
  assert.equal(disabled,0);
  assert.equal(c.messages.some(x=>x.includes('node')),true);
  c.OVS.iran.nodes[0].transport='ws';
  await c.disableIranCarrier('iran','noise');
  assert.equal(disabled,1);
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
  assert.deepEqual(Array.from(fields,f=>f.id),['api_url','public_ip','api_token']);
  await save({api_url:'http://192.0.2.5:8089',api_token:''});
  assert.deepEqual(JSON.parse(JSON.stringify(c.calls[0])),{method:'PUT',url:'api/servers/hub',body:{api_url:'http://192.0.2.5:8089',public_ip:''}});
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
test('GRE refuses a non-IPv4 public host before changing Iran state',async()=>{
 const c=context();
 assert.equal(await c.provisionPatchCircuit('iran','node','gre',8080,{iran_ip:'panel.example'}),false);
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

test('provisionPatchCircuit with null port resolves port from existing node', async () => {
  const c = context();
  const result = await c.provisionPatchCircuit('iran', 'node', 'kcp', null, {});
  assert.ok(result, 'provisioning failed: ' + c.messages.join('; '));
  assert.equal(action(c, 'kcp_on').args.remote, '192.0.2.1:443');
});

test('GRE resolves node IP from api_url when host is absent', async () => {
  const c = context();
  c.SERVERS = [
    {name: 'iran', role: 'iran', host: '127.0.0.1'},
    {name: 'node', role: 'node', transport: 'api', api_url: 'http://78.135.77.57:8089'}
  ];
  const result = await c.provisionPatchCircuit('iran', 'node', 'gre', 8080, {});
  assert.ok(result, 'provisioning failed: ' + c.messages.join('; '));
  const iranGre = c.calls.find(x => x.action === 'gre_on' && x.url.includes('/iran/'));
  const nodeGre = c.calls.find(x => x.action === 'gre_on' && x.url.includes('/node/'));
  assert.equal(iranGre.args.remote_ip, '78.135.77.57');
  assert.equal(nodeGre.args.remote_ip, '192.0.2.1');
});

test('silent option suppresses generic toast in provisionPatchCircuit', async () => {
  const c = context();
  await c.provisionPatchCircuit('iran', 'node', 'ws', 8080, { silent: true });
  assert.equal(c.messages.length, 0, 'silent provisionPatchCircuit should not toast');
});
