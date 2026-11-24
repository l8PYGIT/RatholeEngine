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
      if(url.endsWith('/overview'))return {status:200,j:ctx.OVS.node};
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
  for(const name of ['serviceRequest','serviceAction','findNodeServer','serverPublicIp','configureServiceCarrier']) {
    if(source.includes('function '+name+'(')) vm.runInContext(definition(name),ctx);
  }
  return ctx;
}
function action(c,name) { return c.calls.find(x=>x.action===name&&x.url.includes('/node/')) || c.calls.find(x=>x.action===name); }
for (const [carrier,nodeAction] of [['ws','plain_off'],['kcp','kcp_on'],['plain','plain_on'],['noise','noise_on']]) {
  test(carrier+' configures the node carrier',async()=>{
    const c=context(); await c.configureServiceCarrier('iran','node',carrier,8080,{});
    assert.ok(action(c,nodeAction),nodeAction+' was never sent');
  });
}
test('FRP uses its shared credential, actual listener and Iran backend port',async()=>{
  const c=context(); await c.configureServiceCarrier('iran','node','frp',8080,{});
  const frp=action(c,'frp_on');
  assert.equal(frp.args.token,'22222222222222222222222222222222');
  assert.equal(frp.args.remote,'192.0.2.1:7443');
  assert.equal(frp.args.remote_port,'21001');
  assert.equal(action(c,'add_svc').args.remote_port,'21001');
});
test('FRP+GRE configures both interfaces and dials FRP over GRE',async()=>{
  const c=context();await c.configureServiceCarrier('iran','node','frp_gre',8080,{});
  assert.equal(c.calls.filter(x=>x.action==='gre_on').length,2);
  assert.equal(action(c,'frp_on').args.remote,'10.10.10.1:7443');
});
test('GRE routes the Rathole control connection through its tunnel',async()=>{
  const c=context();await c.configureServiceCarrier('iran','node','gre',8080,{});
  assert.equal(c.calls.filter(x=>x.action==='gre_on').length,2);
  assert.ok(action(c,'plain_on'),'GRE must configure a control carrier');
  assert.equal(c.calls.find(x=>x.action==='plain_on'&&x.url.includes('/node/')).args.remote,'10.10.10.1:8880');
});
test('unreachable GRE peer leaves the working carrier selected',async()=>{
  const c=context({failAction:'gre_probe',oldLane:'backhaul'});
  assert.equal(await c.configureServiceCarrier('iran','node','gre',8080,{}),false);
  assert.equal(action(c,'plain_on'),undefined);
  assert.equal(action(c,'frp_node_on'),undefined);
  assert.equal(action(c,'backhaul_node_off'),undefined);
});
test('FRP releases the Iran backend only after preparing the node service',async()=>{
  const c=context();await c.configureServiceCarrier('iran','node','frp',8080,{});
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.indexOf('add_svc')<actions.indexOf('frp_node_on'));
});
test('unregistered FRP proxy reports failure and restores WebSocket',async()=>{
  const c=context({failAction:'frp_ready'});
  assert.equal(await c.configureServiceCarrier('iran','node','frp',8080,{}),false);
  assert.ok(action(c,'frp_off'));
  assert.ok(action(c,'frp_node_off'));
});
test('inactive FRP server is restarted before changing the node carrier',async()=>{
  const c=context({frpActive:false});
  await c.configureServiceCarrier('iran','node','frp',8080,{});
  const start=c.calls.find(x=>x.action==='frp_on'&&x.url.includes('/iran/'));
  assert.ok(start);
  assert.ok(c.calls.indexOf(start)<c.calls.findIndex(x=>x.action==='frp_node_on'));
});
test('Noise starts an inactive server and registers the service after node configuration',async()=>{
  const c=context({noiseConfigured:true,noiseActive:false});
  await c.configureServiceCarrier('iran','node','noise',8080,{});
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.includes('noise_on'));
  assert.ok(actions.lastIndexOf('noise_node_on') > actions.lastIndexOf('add_svc'));
  assert.ok(actions.lastIndexOf('noise_node_on') < actions.lastIndexOf('noise_on'));
});
test('failed Noise client restores the previous Iran route',async()=>{
  const c=context({failAction:'noise_on',noiseConfigured:true,noiseActive:true});
  assert.equal(await c.configureServiceCarrier('iran','node','noise',8080,{}),false);
  const actions=c.calls.map(x=>x.action);
  assert.ok(actions.includes('noise_node_on'));
  assert.ok(actions.lastIndexOf('noise_node_off') > actions.lastIndexOf('noise_on'));
  assert.ok(actions.lastIndexOf('noise_off') > actions.lastIndexOf('noise_on'));
});
test('inactive Noise daemon stops before switching the service',async()=>{
  const c=context({noiseConfigured:true,noiseActive:false,noiseStartFails:true});
  assert.equal(await c.configureServiceCarrier('iran','node','noise',8080,{}),false);
  assert.equal(action(c,'noise_node_on'),undefined);
  assert.equal(c.messages.some(x=>x.includes('rathole-noise')),true);
});
test('manual Iran IP is used for the Noise connection',async()=>{
  const c=context();
  await c.configureServiceCarrier('iran','node','noise',8080,{iran_ip:'203.0.113.9'});
  const nodeNoise=c.calls.find(x=>x.action==='noise_on'&&x.url.includes('/node/'));
  assert.equal(nodeNoise.args.remote,'203.0.113.9:2334');
});
test('manual Iran IP is used for FRP instead of the detected SSH address',async()=>{
  const c=context();
  await c.configureServiceCarrier('iran','node','frp',8080,{iran_ip:'203.0.113.9'});
  assert.equal(action(c,'frp_on').args.remote,'203.0.113.9:7443');
});
test('Backhaul records service in the independent mux lane',async()=>{
  const c=context();await c.configureServiceCarrier('iran','node','backhaul',8080,{});
  assert.ok(action(c,'add_bh_svc')); assert.equal(action(c,'add_svc'),undefined);
});
test('a failed command stops provisioning and cannot report success',async()=>{
  const c=context({failAction:'add_svc'});
  const result=await c.configureServiceCarrier('iran','node','frp',8080,{});
  assert.equal(result,false);assert.equal(action(c,'frp_on'),undefined);
  assert.equal(c.messages.some(x=>x.includes('با موفقیت')),false);
});
test('an unmatched service cannot silently select the first node',async()=>{
  const c=context();const result=await c.configureServiceCarrier('iran','unknown','ws',8080,{});
  assert.equal(result,false);assert.equal(c.calls.length,0);
});
test('quick carrier modal actually provisions the selected configuration',async()=>{
  const c=context();let callback,called=false;
  Object.assign(c,{buildWiringModel:()=>({circuits:[{iran:'iran',node:'node',backendPort:8080}]}),formModal:(title,fields,cb)=>{callback=cb;},closeModal:()=>{},showCircuitInspector:()=>{},drawPatchBoard:()=>{},highlightCircuit:()=>{},configureServiceCarrier:async()=>{called=true;return true;}});
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
test('UI prefers a public inventory address over a private detected address',()=>{
  const c=context();
  assert.equal(c.serverPublicIp(c.SERVERS[0],{status:{public_ip:'10.1.2.3'}}),'192.0.2.1');
  assert.equal(c.serverPublicIp({name:'iran',host:'10.1.2.3'},{status:{public_ip:'203.0.113.9'}}),'203.0.113.9');
});
test('GRE provisioning does not use a private auto-detected Iran address',async()=>{
  const c=context({detectedIranIp:'10.1.2.3'});
  await c.configureServiceCarrier('iran','node','gre',8080,{});
  const nodeGre=c.calls.find(x=>x.action==='gre_on'&&x.url.includes('/node/'));
  assert.equal(nodeGre.args.remote_ip,'192.0.2.1');
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
test('HTTP failures stop the sequence before any service is added',async()=>{
 const c=context();c.api=async()=>({status:400,j:{error:'invalid fields'}});
 assert.equal(await c.configureServiceCarrier('iran','node','ws',8080,{}),false);
 assert.equal(c.messages.some(x=>x.includes('✓')),false);
});
test('invalid GRE host addresses are rejected before mutating either server',async()=>{
 const c=context();assert.equal(await c.configureServiceCarrier('iran','node','gre',8080,{gre_ip:'10.10.10.0'}),false);
 assert.equal(c.calls.filter(x=>x.action && x.action!=='status').length,0);
});
test('GRE refuses a non-IPv4 public host before changing Iran state',async()=>{
 const c=context();
 assert.equal(await c.configureServiceCarrier('iran','node','gre',8080,{iran_ip:'panel.example'}),false);
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
 const result=await c.configureServiceCarrier('iran','node','frp',8080,{});
 assert.ok(result,'node provisioning stopped before initialization');
 assert.ok(c.calls.findIndex(x=>x.action==='set_main') < c.calls.findIndex(x=>x.action==='add_svc'));
});

test('configureServiceCarrier with null port resolves port from existing node', async () => {
  const c = context();
  const result = await c.configureServiceCarrier('iran', 'node', 'kcp', null, {});
  assert.ok(result, 'provisioning failed: ' + c.messages.join('; '));
  assert.equal(action(c, 'kcp_on').args.remote, '192.0.2.1:443');
});

test('GRE resolves node IP from api_url when host is absent', async () => {
  const c = context();
  c.SERVERS = [
    {name: 'iran', role: 'iran', host: '127.0.0.1'},
    {name: 'node', role: 'node', transport: 'api', api_url: 'http://78.135.77.57:8089'}
  ];
  const result = await c.configureServiceCarrier('iran', 'node', 'gre', 8080, {});
  assert.ok(result, 'provisioning failed: ' + c.messages.join('; '));
  const iranGre = c.calls.find(x => x.action === 'gre_on' && x.url.includes('/iran/'));
  const nodeGre = c.calls.find(x => x.action === 'gre_on' && x.url.includes('/node/'));
  assert.equal(iranGre.args.remote_ip, '78.135.77.57');
  assert.equal(nodeGre.args.remote_ip, '192.0.2.1');
});

test('silent option suppresses generic toast in configureServiceCarrier', async () => {
  const c = context();
  await c.configureServiceCarrier('iran', 'node', 'ws', 8080, { silent: true });
  assert.equal(c.messages.length, 0, 'silent configureServiceCarrier should not toast');
});

test('carrier change preserves authoritative inbound even when UI sends Iran backend port', async () => {
  const c=context({oldLane:'backhaul'});
  await c.configureServiceCarrier('iran','node','noise',21001,{});
  assert.equal(action(c,'edit_node'),undefined);
  assert.equal(String(action(c,'add_svc').args.inbound),'8080');
});

test('carrier label shows reported FRP protocol without inventing QUIC',()=>{
  const c=context();vm.runInContext(definition('carrierLabel'),c);
  assert.equal(c.carrierLabel('frp',{frp:{transport:'tcp'}}),'FRP / TCP');
  assert.equal(c.carrierLabel('frp',{frp:{transport:'quic'}}),'FRP / QUIC');
  assert.equal(c.carrierLabel('frp',{frp:{transport:'kcp'}}),'FRP / KCP');
  assert.equal(c.carrierLabel('backhaul',{backhaul:{transport:'wssmux'}}),'Backhaul / WSSMUX');
  assert.equal(c.carrierLabel('frp',{}),'FRP / ?');
});


test('removal deletes the Iran service and peer registry',async()=>{
 const c=context();c.OVS.node.services=[{name:'node'}];
 Object.assign(c,{confirm:()=>true,t:k=>k,outModal:()=>{}});
 vm.runInContext(definition('removeServicePair'),c);
 await c.removeServicePair('iran','node');
 assert.ok(action(c,'rm_node'));assert.ok(action(c,'rm_svc'));
});
test('node service settings retain the selected node server',()=>{
 const c=context();let selected;
 Object.assign(c,{serviceControl:(...args)=>{selected=args;}});
 vm.runInContext(definition('nodeServiceAction'),c);
 c.nodeServiceAction('node','node','configure','frp');
 assert.deepEqual(Array.from(selected),['iran','node','configure','frp','node']);
});
test('both service pages expose all migrated controls and no board route',()=>{
 const c=context();Object.assign(c,{h:String,t:k=>k});
 vm.runInContext(definition('serviceButtons'),c);
 for(const side of ['iran','node']){
  const html=c.serviceButtons(side,'server','svc');
  for(const action of ['configure','health','copy','manage','remove'])assert.ok(html.includes('data-action="'+action+'"'));
 }
 // radif-haye jadval compact shode-and: hamn 5 akshan az menu-ye '⋯' (serviceMenu) ersal mishavand
 vm.runInContext(definition('serviceMenu'),c);
 for(const side of ['iran','node']){
  const html=c.serviceMenu(side,'server','svc');
  for(const action of ['configure','health','copy','manage','remove'])assert.ok(html.includes('data-action="'+action+'"'));
  assert.ok(html.includes('details class="more"'));
 }
 assert.ok(definition('renderIran').includes("serviceMenu('iran'"));
 assert.ok(definition('renderNode').includes("serviceMenu('node'"));
 // selector-e hamel-e har nod bayad dar safhe-ye Iran baghi bemanad (yek-kliki, do-taraf)
 assert.ok(definition('renderIran').includes('iranNodeCarrierSel(n,ov,d.name)'));
 assert.doesNotMatch(source, /#\/wiring|drawPatchBoard|PATCH_CUSTOM_CIRCUITS|copyV2rayRecipe/);
});
test('copy config uses the supplied UUID and public address',async()=>{
 const c=context();let submit,fields,copied;
 Object.assign(c,{fnd:n=>c.SERVERS.find(s=>s.name===n),t:k=>k,URLSearchParams,
  formModal:(_title,f,cb)=>{fields=f;submit=cb;},closeModal:()=>{},outModal:()=>{},
  navigator:{clipboard:{writeText:async x=>{copied=x;}}}});
 vm.runInContext(definition('copyServiceConfig'),c);
 await c.copyServiceConfig('iran','node');
 const values={uuid:'12345678-1234-1234-1234-123456789abc',host:'panel.example',port:'443',sni:'panel.example',path:'/node'};
 await submit({...values,uuid:'invalid'});assert.equal(copied,undefined);
 await submit({...values,host:'127.0.0.1'});assert.equal(copied,undefined);
 await submit(values);
 assert.ok(copied.startsWith('vless://'+values.uuid+'@panel.example:443?'));
 assert.equal(new URL(copied).searchParams.get('path'),'/node');
 assert.equal(fields.find(x=>x.id==='host').val,'panel.example');
});
test('moving one Backhaul service keeps the other Backhaul services running',async()=>{
 const c=context({oldLane:'backhaul'});
 c.OVS.node.backhaul_services=[{name:'node',inbound:8080},{name:'other',inbound:8081}];
 await c.configureServiceCarrier('iran','node','noise',8080,{});
 assert.equal(action(c,'backhaul_off'),undefined);
 assert.equal(action(c,'rm_bh_svc').args.name,'node');
});

test('pair removal fetches fresh state and aborts on unavailable peer',async()=>{
 const c=context();Object.assign(c,{confirm:()=>true,t:k=>k,outModal:()=>{}});
 c.OVS.node={reachable:false};
 vm.runInContext(definition('removeServicePair'),c);
 await c.removeServicePair('iran','node');
 assert.equal(action(c,'rm_node'),undefined);
 assert.ok(c.calls.some(x=>x.url.endsWith('/overview')));
});
test('SNI services cannot accidentally open a default FRP carrier form',()=>{
 const c=context();c.formModal=()=>assert.fail('unsupported SNI modal opened');c.t=k=>k;
 vm.runInContext(definition('quickCarrierModal'),c);
 c.quickCarrierModal('iran','node','game');
 assert.equal(c.messages[0],'service_game_hint');
});
test('configureServiceCarrier emits a sticky syncing toast before finishing',async()=>{
 const toasts=[];
 const c=context();
 c.toast=(msg,ms)=>{c.messages.push(msg);toasts.push({msg,ms});};
 await c.configureServiceCarrier('iran','node','frp',8080,{});
 assert.ok(toasts.length>=2,'expected syncing toast + completion toast');
 assert.equal(toasts[0].ms,0,'syncing toast must be sticky (ms=0)');
 assert.match(toasts[0].msg,/همگام|sync/i);
});
test('Iran headBadges shows FRP carrier instead of ws/443 when nodes use FRP',()=>{
 const c=context();
 Object.assign(c,{
  fnd:n=>c.SERVERS.find(s=>s.name===n)||{},
  t:k=>k,
  h:s=>String(s==null?'':s),
  HUBST:{latest_version:'2.0.4'}
 });
 for(const fn of ['iranNodeMode','carrierLabel','latestVer','verBadge','headBadges']){
  vm.runInContext(definition(fn),c);
 }
 const ov={
  reachable:true,
  health:{ok:3,fail:0},
  nodes:[{name:'node',port:21001,inbound_port:8080,transport:'frp'}],
  kcp:{enabled:false},
  noise:{enabled:false},
  frp:{enabled:true,active:true,port:7000,transport:'quic'},
  status:{features:{frp:{configured:true,active:true,port:7000,transport:'quic'}}},
  version:{manager:'2.0.4'}
 };
 const html=c.headBadges('iran',ov);
 assert.ok(html.includes('FRP / QUIC'), 'expected FRP / QUIC badge, got: '+html);
 assert.ok(!html.includes('ws/443'), 'must not show ws/443 when only node is FRP, got: '+html);
});
test('Iran FRP carrier card shows UDP port for quic/kcp and live port',()=>{
 const renderIranSrc=definition('renderIran');
 assert.ok(!renderIranSrc.includes('<span>پورت: TCP :7000</span>'),'FRP card must not hardcode TCP :7000');
 assert.ok(renderIranSrc.includes("frpTr === 'quic' || frpTr === 'kcp'") || renderIranSrc.includes('UDP'),
  'FRP card must compute UDP vs TCP from live transport');
});
test('remote names with quotes cannot inject JS into serviceMenu or iranNodeCarrierSel',()=>{
 const c=context();
 const escHtml=s=>(''+(s==null?'':s)).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
 Object.assign(c,{
  h:escHtml,
  t:k=>k,
  IRAN_NODE_CARRIERS:['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre'],
  iranNodeMode:()=>'ws'
 });
 vm.runInContext('var IRAN_NODE_CARRIERS='+JSON.stringify(c.IRAN_NODE_CARRIERS)+';',c);
 vm.runInContext(definition('serviceButtons'),c);
 vm.runInContext(definition('serviceMenu'),c);
 vm.runInContext(definition('iranNodeCarrierSel'),c);
 const payload="n1');alert(1)//";
 for(const html of [
  c.serviceButtons('iran','srv',payload),
  c.serviceMenu('node','srv',payload),
  c.iranNodeCarrierSel('iran',{},payload)
 ]){
  assert.doesNotMatch(html, /\bon(click|change)=/i);
  assert.ok(html.includes('&#39;);alert(1)//'));
 }
});
test('Phase 3 UI fixes: no undefined CSS vars, frp_gre support, carrier rendering, error handling',()=>{
 assert.doesNotMatch(source, /var\(--(?:tx|ac|rd|gr|yl)\)/);
 assert.ok(!source.includes("'Finglish'"), 'language label should not say Finglish');
 const smSrc=definition('statusModal');
 assert.ok(!smSrc.includes("'+j.cmd+'\\\\n") && smSrc.includes("j.cmd+'\\n'"), 'statusModal must use real newline escape');

 const c=context();
 const carriersDecl=source.match(/const CARRIERS=\[[^\]]+\];/);
 assert.ok(carriersDecl,'CARRIERS declaration missing');
 vm.runInContext(carriersDecl[0].replace(/^const /,'var ')+'\n'+definition('nodeCarrier'),c);
 assert.equal(c.nodeCarrier({main_tunnel:'frp_gre'}),'frp_gre');

 const cfgSrc=definition('configureServiceCarrier');
 assert.ok(cfgSrc.includes("oldLane === 'frp_gre'") || cfgSrc.includes("oldIranLane"), 'configureServiceCarrier must map frp_gre to frp_node_off on Iran');

 const riSrc=definition('renderIran');
 for(const stale of ['<span>پورت: UDP :443</span>','<span>پروفایل: Balanced</span>','<span>پورت: TCP :2334</span>','<span>پورت: HTTP :8880</span>','<span>کارت شبکه: gre1</span>']){
  assert.ok(!riSrc.includes(stale), 'stale hardcoded card metadata remains: '+stale);
 }

 assert.match(definition('frpOnIran')+definition('quickCarrierModal'), /KCP.*QUIC|QUIC.*KCP/i);

 for(const fn of ['drawConsole','drawRouteTable','drawGraph']){
  const body=definition(fn);
  for(const car of ['backhaul','frp','gre','frp_gre']){
   assert.ok(body.includes(car), fn+' must handle '+car);
  }
 }

 assert.match(definition('api'), /try\s*\{[\s\S]*fetch[\s\S]*\}\s*catch/);
 assert.match(definition('bindGraphDrag'), /pointercancel/);
 const dtSrc=definition('dtLoadDomains');
 assert.doesNotMatch(dtSrc, /onclick="dt(MakePrimary|RmDomain)/);
});
test('Phase 3 & 4 assets cleanup: i18n duplicates/wb_*, app.css, index.html, dead UI functions',()=>{
 const i18nSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','i18n.js'),'utf8');
 for(const lang of ['fa','en']){
  const m=i18nSrc.match(new RegExp(lang+':\\s*\\{([\\s\\S]*?)\\n\\s*\\}'));
  assert.ok(m, 'missing lang block '+lang);
  const stripped=m[1].replace(/(["'])(?:\\.|(?!\1).)*\1/g,"''");
  const re=/(?:^|[,{\s])([A-Za-z0-9_]+)\s*:(?=\s*['"])/gm;
  const seen=new Set(), dups=[]; let x;
  while((x=re.exec(stripped))!==null){if(seen.has(x[1]))dups.push(x[1]); seen.add(x[1]);}
  assert.deepEqual(dups,[],'duplicate i18n keys in '+lang+': '+dups.join(','));
 }
 assert.doesNotMatch(i18nSrc, /\bwb_[a-z_]+\s*:/);

 const cssSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','app.css'),'utf8');
 assert.ok(!cssSrc.includes('repeat(5, 1fr)'), 'mobile nav should use 4 columns');
 assert.ok(cssSrc.includes('repeat(4, 1fr)'));
 assert.ok(!cssSrc.includes('.cable-flow'));
 assert.ok(cssSrc.includes('border-inline-start'));
 for(const cls of ['.e-backhaul','.e-frp','.e-gre','.e-frp_gre','.lw-backhaul','.lw-frp','.lw-gre','.lw-frp_gre']){
  assert.ok(cssSrc.includes(cls), 'missing css class '+cls);
 }

 const htmlSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','index.html'),'utf8');
 assert.ok(!htmlSrc.includes('id="i-cable"') && !htmlSrc.includes('id="i-plus"'));
 assert.ok(htmlSrc.includes('Content-Security-Policy'));

 for(const dead of ['addSvc','addBhSvc','plainOnNode','noiseOnNode','bhOnNode','bhAutofill','bhNodeFields','frpAutofill','greOnNode','kcpOnNode','carrierOffAction']){
  assert.doesNotMatch(source, new RegExp('\\bfunction\\s+'+dead+'\\b'));
 }
});
test('Apple/Raycast UI redesign: offline Vazirmatn font, native <dialog>, top-layer CSS, theme & filter logic',()=>{
 const fontPath=path.join(__dirname,'..','rathole-manager','ratholehub','ui','vazirmatn.woff2');
 const fontBuf=fs.readFileSync(fontPath);
 assert.ok(fontBuf.length>100000,'vazirmatn.woff2 too small');
 assert.equal(fontBuf.subarray(0,4).toString('ascii'),'wOF2');

 const hubPy=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','hub.py'),'utf8');
 assert.ok(hubPy.includes('"vazirmatn.woff2"'));
 const ihub=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','install-hub.sh'),'utf8');
 assert.ok(ihub.includes('vazirmatn.woff2'));
 const upd=fs.readFileSync(path.join(__dirname,'..','rathole-manager','update.sh'),'utf8');
 assert.ok(upd.includes('vazirmatn.woff2'));

 const htmlSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','index.html'),'utf8');
 assert.ok(htmlSrc.includes('<meta name="color-scheme" content="light dark">'));
 assert.ok(htmlSrc.includes("font-src 'self'"));
 assert.ok(htmlSrc.includes('href="ui/vazirmatn.woff2"'));

 const cssSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','app.css'),'utf8');
 assert.ok(cssSrc.includes('font-family: "Vazirmatn"'));
 assert.ok(cssSrc.includes('overscroll-behavior: contain'));
 assert.ok(cssSrc.includes('@starting-style'));
 assert.ok(cssSrc.includes('transition-behavior: allow-discrete'));
 assert.ok(cssSrc.includes('&:has(> head > meta[name="color-scheme"][content="dark"])'));
 assert.doesNotMatch(cssSrc,/^\s*\*\s*\{/m);

 const i18nSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','i18n.js'),'utf8');
 const extractKeys=lang=>{
  const m=i18nSrc.match(new RegExp(lang+':\\s*\\{([\\s\\S]*?)\\n\\s*\\}'));
  const stripped=m[1].replace(/(["'])(?:\\.|(?!\1).)*\1/g,"''");
  const re=/(?:^|[,{\s])([A-Za-z0-9_]+)\s*:(?=\s*['"])/gm;
  const s=new Set(); let x; while((x=re.exec(stripped))!==null)s.add(x[1]); return s;
 };
 const faKeys=extractKeys('fa'), enKeys=extractKeys('en');
 assert.deepEqual([...faKeys].filter(k=>!enKeys.has(k)),[],'missing en keys');
 assert.deepEqual([...enKeys].filter(k=>!faKeys.has(k)),[],'missing fa keys');

 // Exercise native <dialog>, Command Palette, filteredServers, toggleTheme, toggleSidebar
 assert.ok(source.includes("createElement('dialog')") && source.includes('showModal()'));
 assert.ok(!source.includes("setAttribute('inert'") && !source.includes('role="dialog"'));
 const store={};
 const metaEl={content:'light dark'};
 const clsSet=new Set();
 const docEl={dataset:{},lang:'',dir:'',classList:{toggle:(k,f)=>{if(f)clsSet.add(k);else clsSet.delete(k);}}};
 const c=context();
 Object.assign(c,{
  LANG:'fa', THEME_PREF:'', TOKEN:'tok', ROUTE:{page:'dashboard'},
  localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v);},removeItem:k=>{delete store[k];}},
  matchMedia:q=>({matches:q.includes('light')?false:true}),
  document:{documentElement:docEl,querySelector:sel=>sel.includes('color-scheme')?metaEl:null,querySelectorAll:()=>[]},
  $:()=>null, t:k=>k, applyStatic:()=>{}, renderSettingsPage:()=>{}, nav:()=>{}, editHubProxy:()=>{},
  updateAll:()=>{}, refreshPage:()=>{}, toggleLang:()=>{}, ovDotCls:()=>'d-ok',
 });
 vm.runInContext('var DASH_FILTER={q:"",role:"all",status:"all"};\nvar LANG="fa",THEME_PREF="",TOKEN="tok",ROUTE={page:"dashboard"};\n'+
  ['systemTheme','resolvedTheme','applyStatic','toggleTheme','setThemeMode','toggleSidebar','filteredServers','cmdkEntries'].map(fn=>definition(fn)).join('\n'),c);

 assert.equal(c.SERVERS.length,2);
 c.DASH_FILTER.role='iran';
 assert.deepEqual(Array.from(c.filteredServers(),s=>s.name),['iran']);
 c.DASH_FILTER.role='all'; c.DASH_FILTER.q='192.0.2.2';
 assert.deepEqual(Array.from(c.filteredServers(),s=>s.name),['node']);
 c.DASH_FILTER.q='';

 c.toggleTheme(); // dark OS -> toggle overrides to light
 assert.equal(store.rh_theme,'light');
 assert.equal(metaEl.content,'light');
 c.toggleTheme(); // toggles back to dark == OS -> clears override
 assert.equal(store.rh_theme,undefined);
 assert.equal(metaEl.content,'light dark');

 c.toggleSidebar();
 assert.equal(store.rh_sb_collapsed,'1');
 assert.equal(clsSet.has('sb-collapsed'),true);
 c.toggleSidebar();
 assert.equal(store.rh_sb_collapsed,undefined);
 assert.equal(clsSet.has('sb-collapsed'),false);

 const items=c.cmdkEntries('iran');
 assert.ok(items.some(it=>it.sec==='servers'&&it.label==='iran'));

 // Regression assertions for cascade order, empty HUBST KPI, menu offset, and t()
 assert.match(source, /function t\(k\)\{/);
 const baseLayerStart=cssSrc.indexOf('@layer base {');
 const layoutLayerStart=cssSrc.indexOf('@layer layout {');
 const btnBaseIdx=cssSrc.indexOf('  button {\n');
 assert.ok(baseLayerStart>=0&&layoutLayerStart>baseLayerStart&&btnBaseIdx>baseLayerStart&&btnBaseIdx<layoutLayerStart,
  'base button rule must live inside @layer base before @layer layout');
 const pmSrc=definition('positionMoreMenu');
 assert.ok(pmSrc.includes('origin.top')&&pmSrc.includes('origin.left'),
  'positionMoreMenu must compensate for backdrop-filter containing block offset');
 const kpiBox={innerHTML:''};
 const kc={
  $:id=>id==='kpi_grid'?kpiBox:null,
  SERVERS:[{name:'iran',role:'iran'}],
  OVS:{iran:{reachable:true,nodes:[{name:'n1'}]}},
  HUBST:{services:{},hub_uptime:75},
  t:k=>({st_ok:'OK_STATUS',loading:'LOADING_STATUS',kpi_servers:'S',kpi_online:'O',kpi_services:'V',kpi_hub:'H',flt_iran:'I',flt_node:'N',flt_online:'ON',flt_offline:'OFF',n_nodes:'NN',n_svcs:'NS',hs_up:'UP',hub_box:'HUB'}[k]||k),
  h:x=>String(x??''),
  icon:()=>'',
  fmtDur:s=>s+'s'
 };
 vm.createContext(kc);
 vm.runInContext(definition('updateDashboardKpis'),kc);
 kc.updateDashboardKpis();
 assert.ok(kpiBox.innerHTML.includes('OK_STATUS')&&!kpiBox.innerHTML.includes('LOADING_STATUS'),
  'empty HUBST.services must render healthy instead of loading');
 assert.ok(kpiBox.innerHTML.includes('75s'), 'expected hub_uptime fallback in KPI card');
});

test('More-menu body portaling, mobile sidebar stacking, dialog/diag animations & Emil motion rules',()=>{
 const cssSrc=fs.readFileSync(path.join(__dirname,'..','rathole-manager','ratholehub','ui','app.css'),'utf8');
 for(const tok of ['--ease-out','--ease-in-out','--ease-drawer']){
  assert.ok(cssSrc.includes(tok),'missing motion token '+tok);
 }
 assert.doesNotMatch(cssSrc,/transition\s*:\s*all\b/);
 assert.doesNotMatch(cssSrc,/scale\(\s*0\s*\)/);
 assert.ok(cssSrc.includes('\n  .more-menu {\n')||cssSrc.includes('.more-menu {\n'),'expected decoupled .more-menu rule');
 assert.ok(!cssSrc.includes('details.more .more-menu'),'portaled .more-menu must not require details.more ancestor');
 assert.ok(cssSrc.includes('.more-menu.more-menu-portal.is-open'));
 assert.ok(!cssSrc.includes('container-type: inline-size'),'.table-wrap must not trap fixed popovers');
 assert.ok(cssSrc.includes('dialog.cmdk-dialog')&&cssSrc.includes('transition-duration: 0ms !important'));
 assert.ok(cssSrc.includes('@media (hover: hover) and (pointer: fine)'));
 assert.ok(cssSrc.includes('#sb::before')&&cssSrc.includes('backdrop-filter: none;'));
 assert.ok(cssSrc.includes('@media (prefers-reduced-motion: reduce)'));

 const c=context();
 const bodyChildren=[];
 const doc={
  documentElement:{dir:'rtl'},
  body:{
   children:bodyChildren,
   appendChild(ch){
    if(ch.parentElement&&ch.parentElement!==doc.body&&Array.isArray(ch.parentElement.children)){
     const i=ch.parentElement.children.indexOf(ch);
     if(i>=0)ch.parentElement.children.splice(i,1);
    }
    ch.parentElement=doc.body;
    if(!bodyChildren.includes(ch))bodyChildren.push(ch);
    return ch;
   },
  },
  querySelectorAll(sel){
   if(sel==='details.more[open]')return details.open?[details]:[];
   if(sel==='body > .more-menu-portal')return bodyChildren.filter(x=>x._cl.has('more-menu-portal'));
   return [];
  },
 };
 const makeEl=(tag,cls='')=>{
  const el={
   tagName:tag.toUpperCase(),
   children:[],
   parentElement:null,
   isConnected:true,
   dataset:{},
   style:{},
   open:false,
   _cl:new Set(cls.split(/\s+/).filter(Boolean)),
   classList:{
    add:(...a)=>a.forEach(x=>el._cl.add(x)),
    remove:(...a)=>a.forEach(x=>el._cl.delete(x)),
    contains:x=>el._cl.has(x),
   },
   appendChild(ch){
    if(ch.parentElement&&ch.parentElement!==el){
     const i=ch.parentElement.children.indexOf(ch);
     if(i>=0)ch.parentElement.children.splice(i,1);
    }
    if(el===doc.body&&!bodyChildren.includes(ch))bodyChildren.push(ch);
    ch.parentElement=el;
    if(!el.children.includes(ch))el.children.push(ch);
    return ch;
   },
   remove(){
    const idx=bodyChildren.indexOf(el);
    if(idx>=0)bodyChildren.splice(idx,1);
    el.parentElement=null;
   },
   querySelector:()=>null,
   getBoundingClientRect:()=>({top:100,bottom:132,left:40,right:72,width:215,height:180}),
  };
  return el;
 };
 const details=makeEl('details');
 const summary=makeEl('summary');
 const menu=makeEl('div','more-menu');
 details.appendChild(summary);
 details.appendChild(menu);
 details.querySelector=sel=>sel==='summary'?summary:(sel==='.more-menu'?menu:null);
 Object.assign(c,{
  document:doc,
  window:{innerWidth:1280,innerHeight:900},
  requestAnimationFrame:fn=>fn(),
  clearTimeout:()=>{},
  setTimeout:()=>0,
  matchMedia:()=>({matches:false}),
  getComputedStyle:()=>({borderTopWidth:'1px',borderBottomWidth:'1px'}),
 });
 vm.runInContext(
  ['prefersReducedMotion','closeMoreMenu','closeAllMoreMenus','positionMoreMenu','toggleDiagDetails']
   .map(fn=>definition(fn)).join('\n'),
  c
 );

 details.open=true;
 c.positionMoreMenu(details);
 assert.equal(menu.parentElement,doc.body,'open .more-menu must portal directly to document.body');
 assert.ok(menu.classList.contains('fixed-menu')&&menu.classList.contains('more-menu-portal'));
 assert.ok(menu.classList.contains('is-open'));
 assert.ok(menu.style.transformOrigin==='top left');
 assert.equal(menu.dataset.side,'bottom');

 c.closeAllMoreMenus(null,true);
 assert.equal(details.open,false);
 assert.equal(menu.parentElement,details,'closed .more-menu must return inside details');
 assert.ok(!menu.classList.contains('more-menu-portal'));

 // Verify interruptible WAAPI toggleDiagDetails on details.diag-sec
 const diag=makeEl('details','diag-sec');
 const dSum=makeEl('summary');
 const dBody=makeEl('div','diag-content');
 diag.appendChild(dSum);
 diag.appendChild(dBody);
 diag.querySelector=sel=>sel===':scope > summary'?dSum:null;
 dSum.nextElementSibling=dBody;
 diag.offsetHeight=48;
 dSum.offsetHeight=44;
 let animCalls=0, canceled=0;
 const mkAnim=()=>{
  const a={onfinish:null,oncancel:null,cancel(){canceled++;}};
  animCalls++;
  return a;
 };
 diag.animate=mkAnim;
 dBody.animate=mkAnim;

 c.toggleDiagDetails(diag,true);
 assert.equal(diag.open,true);
 assert.equal(diag.dataset.opening,'1');
 assert.ok(animCalls>=2);

 // Interrupt mid-open with close
 c.toggleDiagDetails(diag,false);
 assert.ok(canceled>=2,'re-toggling mid-open must cancel prior animations cleanly');
 assert.equal(diag.dataset.closing,'1');
 diag._anim.onfinish();
 assert.equal(diag.open,false);
 assert.equal(diag.dataset.closing,undefined);
});

test('M2 UI: serviceHealth & nodeLinkTest use link-test with doctor fallback, and renderDriftPanel escapes HTML', async () => {
 const modCalls=[], toasts=[], domMap={driftpanel:{innerHTML:''}};
 const c={
  $:id=>domMap[id]||null,
  h:t=>String(t==null?'':t).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])),
  t:k=>k,
  toast:x=>toasts.push(x),
  modal:html=>modCalls.push(html),
  outModal:(title,txt)=>modCalls.push({out:true,title,txt}),
  closeModal:()=>{},
  loadOv:async()=>{},
  apiCalls:[],
  api:async(method,url,body)=>{
   c.apiCalls.push({method,url,body});
   if(url.endsWith('/link-test')&&c.nextLinkTest)return c.nextLinkTest(url,body);
   if(url.endsWith('/action')&&body&&body.action==='doctor')return {status:200,j:{rc:0,out:'DOCTOR OK',err:''}};
   return {status:200,j:{rc:0,out:''}};
  }
 };
 vm.createContext(c);
 vm.runInContext(
  'var _LT_CB={retest:null,doc:null};\n'+
  ['_ltVerdictBadge','_ltSideCard','renderLinkTestModal','runServerDoctor','serviceHealth','nodeLinkTest','renderDriftPanel']
   .map(fn=>definition(fn)).join('\n'),
  c
 );

 // 1. Bidirectional healthy link-test modal
 c.nextLinkTest=()=>({status:200,j:{
  ok:true, verdict:'healthy', diagnosis_code:'healthy', diagnosis:'Bidirectional link healthy',
  iran_to_node:{ok:true,verdict:'healthy',probe_mode:'http_ws',port:1005,loss_pct:0,jitter_ms:1.2,rtt_ms:{min:10,avg:14.5,max:20,p95:19},http_status:101},
  node_to_iran:{ok:true,verdict:'healthy',probe_mode:'ws_tls',endpoint:'rp01.example:443',loss_pct:0,jitter_ms:1.0,rtt_ms:{min:11,avg:13.0,max:16,p95:15},backends:[{name:'trk01',port:8444,up:true}]}
 }});
 await c.serviceHealth('iran1','trk01','node1');
 assert.equal(c.apiCalls[0].url,'api/servers/iran1/link-test');
 assert.equal(c.apiCalls[0].body.node,'trk01');
 assert.equal(c.apiCalls[0].body.peer,'node1');
 assert.ok(typeof modCalls.at(-1)==='string' && modCalls.at(-1).includes('14.5 ms'));

 c.apiCalls.length=0;
 await c.nodeLinkTest('de01');
 assert.equal(c.apiCalls[0].url,'api/servers/de01/link-test');
 assert.equal(c.apiCalls[0].body.count,5);

 // 2. Fallback to doctor when unsupported: true or 404
 c.apiCalls.length=0;
 c.nextLinkTest=()=>({status:200,j:{ok:false,unsupported:true}});
 await c.serviceHealth('iran1','trk01','node1');
 assert.ok(c.apiCalls.some(x=>x.url==='api/servers/iran1/action'&&x.body.action==='doctor'));
 assert.equal(modCalls.at(-1).out,true);
 assert.equal(modCalls.at(-1).txt,'DOCTOR OK');

 c.apiCalls.length=0;
 c.nextLinkTest=()=>({status:404,j:{error:'not found'}});
 await c.serviceHealth('iran1','trk01','node1');
 assert.ok(c.apiCalls.some(x=>x.url==='api/servers/iran1/action'&&x.body.action==='doctor'));

 // 3. renderDriftPanel XSS escaping and clean vs issue rendering
 const cleanHtml=c.renderDriftPanel({hub_version:'2.1.1',summary:{clean:true,total:0},items:[]});
 assert.ok(cleanHtml.includes('drift_clean'));
 assert.equal(domMap.driftpanel.innerHTML,cleanHtml);

 const evil='<script>alert(1)</script>"\'';
 const dirtyHtml=c.renderDriftPanel({
  hub_version:'2.1.1',
  summary:{clean:false,total:1},
  items:[{severity:'error',kind:'carrier_mismatch',server:evil,peer:'n1',service:'s<1>',expected:'ws',actual:'frp',message:'bad '+evil}]
 });
 assert.ok(!dirtyHtml.includes('<script>'));
 assert.ok(dirtyHtml.includes('&lt;script&gt;'));
 assert.ok(dirtyHtml.includes('drift-sev-error'));
});

test('doLogin prompts for TOTP when required and retries with 2FA code', async () => {
 const c = context();
 const mkEl = (val = '') => {
  const el = {
   value: val,
   style: { display: 'none' },
   hidden: true,
   textContent: '',
   focused: false,
   attrs: {},
   setAttribute(k, v) { this.attrs[k] = v; },
   focus() { this.focused = true; },
  };
  return el;
 };
 const els = { pw: mkEl('secret'), totp: mkEl(''), totp_wrap: mkEl(''), msg: mkEl('') };
 const stored = new Map();
 let shellCalled = 0;
 let apiCalls = 0;
 Object.assign(c, {
  $: id => els[id] || null,
  t: key => key,
  TOKEN: '',
  location: { hash: '' },
  localStorage: { setItem: (k, v) => stored.set(k, v) },
  shell: () => { shellCalled += 1; },
  api: async (method, url, body) => {
   apiCalls += 1;
   assert.equal(method, 'POST');
   assert.equal(url, 'api/login');
   const snap = JSON.parse(JSON.stringify(body));
   if (!snap.totp) {
    assert.deepEqual(snap, { password: 'secret' });
    return { status: 401, j: { error: 'totp_required', totp_required: true } };
   }
   assert.deepEqual(snap, { password: 'secret', totp: '123456' });
   return { status: 200, j: { ok: true, token: 'tok_2fa_ok' } };
  },
 });
 vm.runInContext(definition('doLogin'), c);

 await c.doLogin();
 assert.equal(apiCalls, 1);
 assert.equal(els.totp_wrap.style.display, '');
 assert.equal(els.totp_wrap.hidden, false);
 assert.equal(els.msg.textContent, 'totp_hint');
 assert.equal(els.totp.focused, true);
 assert.equal(shellCalled, 0);

 els.totp.value = '123456';
 await c.doLogin();
 assert.equal(apiCalls, 2);
 assert.equal(c.TOKEN, 'tok_2fa_ok');
 assert.equal(stored.get('rh_token'), 'tok_2fa_ok');
 assert.equal(shellCalled, 1);
});

test('saveMonitorConfig parses chat IDs and diagnoseMonitorRelay renders report', async () => {
 const c = context();
 const els = {
  mon_enabled: { checked: true },
  mon_chats: { value: '-100111, 222' },
  mon_relay: { value: 'ssh_auto' },
  mon_proxy: { value: '' },
  mon_poll: { value: '45' },
  mon_fail: { value: '3' },
  mon_rec: { value: '2' },
  mon_cool: { value: '300' },
  mon_actions: { checked: true },
  mon_token: { value: '' },
 };
 let modalOut = null;
 let reloaded = 0;
 Object.assign(c, {
  $: id => els[id] || null,
  t: key => key,
  toast: () => {},
  outModal: (title, text) => { modalOut = { title, text }; },
  loadMonitorSettings: () => { reloaded += 1; },
  api: async (method, url, body) => {
   if (url === 'api/monitor/config') {
    const snap = JSON.parse(JSON.stringify(body));
    assert.deepEqual(snap.allowed_chat_ids, [-100111, 222]);
    assert.equal(snap.relay_mode, 'ssh_auto');
    assert.equal('bot_token' in snap, false);
    return { status: 200, j: { ok: true } };
   }
   if (url === 'api/monitor/diagnose-relay') {
    return {
     status: 200,
     j: {
      recommended_mode: 'ssh_auto',
      best_ssh_node: 'trk01',
      summary: 'SSH node ok',
      direct: { ok: false, error: 'timeout' },
      proxy: { configured: false },
      ssh_nodes: [{ name: 'trk01', host: '198.51.100.10', ok: true, latency_ms: 142 }],
     },
    };
   }
   throw new Error('unexpected url: ' + url);
  },
 });
 vm.runInContext(definition('saveMonitorConfig'), c);
 vm.runInContext(definition('diagnoseMonitorRelay'), c);

 await c.saveMonitorConfig();
 assert.equal(reloaded, 1);

 await c.diagnoseMonitorRelay();
 assert.ok(modalOut);
 assert.ok(modalOut.text.includes('Recommended: ssh_auto (best node: trk01)'));
 assert.ok(modalOut.text.includes('trk01 (198.51.100.10): OK (142 ms)'));
});

test('adaptiveOnNode forwards chain and openEndpointsModal escapes endpoint HTML', async () => {
 const c = context();
 let modalArgs = null;
 let shownHtml = '';
 const ran = [];
 Object.assign(c, {
  $: () => null,
  t: key => key,
  toast: () => {},
  formModal: (title, fields, cb) => { modalArgs = { title, fields, cb }; },
  closeModal: () => {},
  run: (srv, act, args) => { ran.push({ srv, act, args }); },
  modal: html => { shownHtml = html; },
  api: async (method, url, body) => {
   assert.equal(method, 'POST');
   assert.equal(url, 'api/servers/trk01/action');
   assert.equal(body.action, 'endpoints_ls');
   return {
    status: 200,
    j: {
     rc: 0,
     out: JSON.stringify({
      primary: '5.202.4.40:443',
      active: '5.202.4.40:443',
      backups: ['<script>bad</script>:443'],
      scores: { '5.202.4.40:443': { score: 99, last_ok: true, last_ms: 14 } },
     }),
    },
   };
  },
 });
 vm.runInContext(definition('h'), c);
 vm.runInContext(definition('adaptiveOnNode'), c);
 vm.runInContext(definition('openEndpointsModal'), c);

 c.adaptiveOnNode('trk01');
 assert.ok(modalArgs.fields.some(f => f.id === 'chain'));
 assert.ok(modalArgs.fields.some(f => f.id === 'probe_candidates'));
 modalArgs.cb({ interval: '20', failures: '3', recoveries: '4', chain: 'ws,noise,frp', probe_candidates: '1' });
 assert.equal(ran.length, 1);
 assert.deepEqual(JSON.parse(JSON.stringify(ran[0].args)), {
  interval: '20', failures: '3', recoveries: '4', chain: 'ws,noise,frp', probe_candidates: '1',
 });

 await c.openEndpointsModal('trk01');
 assert.ok(!shownHtml.includes('<script>'));
 assert.ok(shownHtml.includes('&lt;script&gt;bad&lt;/script&gt;:443'));
 assert.ok(shownHtml.includes('ep_score'));
});

test('Backhaul direct_ip wssmux calls ip-tls/prepare and pins tls_ca + saveUpdateSettings saves config', async () => {
 const c = context();
 const prepCalls = [];
 let savedUpd = null;
 c.api = async (method, url, body) => {
  c.calls.push({ method, url, ...body });
  if (url === 'api/ip-tls/prepare') {
   prepCalls.push(JSON.parse(JSON.stringify(body)));
   return { status: 200, j: { ok: true, rc: 0, tls_trusted_root: '/etc/rathole/ip-root-ca.crt' } };
  }
  if (url === 'api/config') {
   savedUpd = JSON.parse(JSON.stringify(body));
   return { status: 200, j: { ok: true, changed: ['update_channel', 'update_relay_mode', 'update_require_sig'] } };
  }
  if (url.endsWith('/overview')) return { status: 200, j: c.OVS.node };
  if (url.includes('/nodeconnect/')) return { status: 200, j: { ok: true, name: 'node', token: '1'.repeat(32), inbound: '8080', remote_port: '21001', transport: 'ws' } };
  if (url.endsWith('/backhaulconnect')) return { status: 200, j: { ok: true, mode: 'direct_ip', remote_addr: '192.0.2.1:3080', transport: 'wssmux', profile: 'balanced', token: '4'.repeat(32) } };
  if (body && body.action === 'status') return { status: 200, j: { rc: 0, out: JSON.stringify({ public_ip: '192.0.2.1', ports: {}, features: { backhaul: { configured: true, active: true, port: 3080, transport: 'wssmux', profile: 'balanced' } }, nodes: [{ name: 'node', port: 21001, inbound_port: 8080, transport: 'ws' }] }) } };
  return { status: 200, j: { rc: 0, out: '' } };
 };
 await c.configureServiceCarrier('iran', 'node', 'backhaul', 8080, { bh_transport: 'wssmux' });
 assert.equal(prepCalls.length, 1);
 assert.deepEqual(prepCalls[0], { iran: 'iran', node: 'node' });
 const bhCall = action(c, 'backhaul_on');
 assert.equal(bhCall.args.tls_ca, '/etc/rathole/ip-root-ca.crt');

 const els = {
  upd_chan: { value: 'beta' },
  upd_relay: { value: 'relay' },
  upd_proxy: { value: 'socks5h://127.0.0.1:1080' },
  upd_req_sig: { checked: true },
 };
 c.$ = id => els[id] || null;
 c.t = key => key;
 vm.runInContext(definition('saveUpdateSettings'), c);
 await c.saveUpdateSettings();
 assert.deepEqual(savedUpd, {
  update_channel: 'beta',
  update_relay_mode: 'relay',
  update_proxy: 'socks5h://127.0.0.1:1080',
  update_require_sig: true,
 });
});

test('M7 paqet, Managed Xray & cover scanner UI helpers work cleanly', async () => {
 const c = context();
 c.OVS.rp01 = { nodes: [{ name: 'pq1', port: 1006, inbound_port: 8445, transport: 'paqet' }], features: {}, paqet: { enabled: true, mode: 'fast2' } };
 c.OVS.trk01 = { services: [{ name: 'pq1', inbound: 8445 }], paqet: { enabled: true, mode: 'fast', port: 9999 }, xray: { configured: true, active: true, mode: 'reality', port: 8443 } };
 const elements = {
  f_remote: { value: '' },
  f_key: { value: '' },
  f_mode: { value: 'fast' },
  f_block: { value: 'aes-128-gcm' },
  f_node_src: { value: 'trk01', onchange: null },
 };
 let modalTitle = '', modalSubmit = null, shownOut = '';
 c.$ = id => elements[id] || null;
 c.t = k => k;
 c.SERVERS = [{ name: 'rp01', role: 'iran', host: '5.202.4.40' }, { name: 'trk01', role: 'node', host: '198.51.100.5' }];
 c.formModal = (title, _fields, onSubmit) => { modalTitle = title; modalSubmit = onSubmit; };
 c.closeModal = () => {};
 c.outModal = (_t, txt) => { shownOut = txt; };
 c.run = (srv, action, args) => { c.calls.push({ url: 'api/servers/' + srv + '/action', srv, action, args }); };
 c.api = async (m, url, body) => {
  c.calls.push({ m, url, ...(body || {}) });
  if (url === 'api/servers/trk01/paqetconnect') {
   return { status: 200, j: { ok: true, remote: '198.51.100.5:9999', key: '0'.repeat(32), mode: 'fast3', block: 'salsa20' } };
  }
  if (body && body.action === 'xray_scan') {
   return { status: 200, j: { rc: 0, out: JSON.stringify({ ok: true, recommended: 'www.microsoft.com', results: [{ domain: 'www.microsoft.com', ok: true, tls_version: 'TLSv1.3', alpn: 'h2', rtt_ms: 15.2 }] }) } };
  }
  return { status: 200, j: { rc: 0, out: 'vless://ok' } };
 };
 vm.runInContext(
  definition('carrierLabel') + '\n' +
  definition('paqetAutofill') + '\n' +
  definition('paqetOnIran') + '\n' +
  definition('paqetNode') + '\n' +
  definition('paqetOnNode') + '\n' +
  definition('setupXrayNode') + '\n' +
  definition('scanXrayCover') + '\n' +
  definition('showXrayUri'),
  c
 );
 assert.equal(c.carrierLabel('paqet', c.OVS.rp01), 'Paqet / PCK · fast2');

 c.paqetOnIran('rp01');
 assert.ok(modalTitle);
 await new Promise(r => setTimeout(r, 10));
 assert.equal(elements.f_remote.value, '198.51.100.5:9999');
 assert.equal(elements.f_mode.value, 'fast3');
 modalSubmit({ remote: elements.f_remote.value, key: elements.f_key.value, mode: 'fast3', block: 'salsa20', conn: '2' });
 assert.equal(action(c, 'paqet_on').args.remote, '198.51.100.5:9999');

 c.paqetNode('rp01', 'pq1');
 modalSubmit({ name: 'pq1', act: 'on' });
 assert.equal(action(c, 'paqet_node_on').args.name, 'pq1');

 c.paqetOnNode('trk01');
 modalSubmit({ port: '9999', key: '', mode: 'fast', block: 'aes-128-gcm', conn: '1' });

 c.setupXrayNode('trk01');
 modalSubmit({ mode: 'reality', port: '8443', dest: 'www.microsoft.com:443', sni: 'www.microsoft.com', proxy_protocol: '1' });
 assert.equal(action(c, 'xray_setup').args.proxy_protocol, true);

 await c.scanXrayCover('rp01');
 await modalSubmit({ domains: 'www.microsoft.com', top: '3' });
 assert.ok(shownOut.includes('recommended: www.microsoft.com'));

 c.showXrayUri('trk01');
 assert.ok(c.calls.some(x => x.action === 'xray_uri'));
});

test('#/tuner route, i18n FA/EN keys, and tuner API UI helpers work cleanly', async () => {
 const i18nSrc = fs.readFileSync(path.join(__dirname, '../rathole-manager/ratholehub/ui/i18n.js'), 'utf8');
 const i18nCtx = {};
 vm.createContext(i18nCtx);
 vm.runInContext(i18nSrc + '\nthis.DICT = DICT;', i18nCtx);
 assert.ok(i18nCtx.DICT && i18nCtx.DICT.fa && i18nCtx.DICT.en);
  for (const k of [
   'nav_tuner', 'tuner_title', 'tuner_start', 'tuner_stop', 'tuner_copy_json',
   'tuner_copy_b64', 'tuner_apply_both', 'tuner_rollback_both', 'tuner_import_btn',
   'tuner_err_title', 'tuner_live_trials', 'tuner_ph_completed', 'tuner_ph_error',
   'tuner_st_0', 'tuner_st_5', 'tuner_live_status', 'tuner_st_applied',
   'tuner_st_default', 'tuner_winner_cfg', 'tuner_applied_msg', 'tuner_reconnect_hint',
  ]) {
   assert.ok(i18nCtx.DICT.fa[k], 'missing fa.' + k);
   assert.ok(i18nCtx.DICT.en[k], 'missing en.' + k);
  }

  assert.ok(source.includes('data-pg="tuner"'), 'sidebar missing tuner button');
  assert.ok(source.includes("ROUTE.page==='tuner'"), 'router missing tuner branch');

  const c = context();
  const els = {
   page: { innerHTML: '', classList: { remove() {}, add() {} }, offsetWidth: 1 },
   tn_iran: { value: 'iran' },
   tn_node: { value: 'node' },
   tn_mode: { value: 'brutal' },
   tn_goal: { value: 'low-latency' },
   tn_deep: { checked: true },
   tn_iran_dc: { value: 'arvan-thr' },
   tn_node_dc: { value: 'hetzner-fsn1' },
   tn_status_box: { innerHTML: '' },
  };
  let curHash = '#/tuner';
  c.location = { get hash() { return curHash; }, set hash(v) { curHash = v; } };
  c.$ = id => els[id] || null;
  c.t = k => k;
  c.h = x => ('' + (x == null ? '' : x)).replace(/[&<>'"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  c.SERVERS = [{ name: 'iran', role: 'iran', host: '5.202.4.40' }, { name: 'node', role: 'node', host: '198.51.100.5' }];
  c.ROUTE = { page: 'tuner', param: null };
  c.confirm = () => true;
  c.closeModal = () => {};
  let polledJobId = '';
  c.pollTunerJob = id => { polledJobId = id; };
  c.clearTunerPoll = () => { if (c.TUNER_STATE) c.TUNER_STATE.pollTimer = null; };
  c.loadTunerProfiles = async () => {};
  let jobsReply = [];
  c.TUNER_STATE = {
   activeJobId: null, job: null, lastReport: { profile_b64: 'rthprof1:abcdefghijklmnop' },
   profiles: [], jobs: [], jobsLoaded: false, liveStatus: null, liveStatusPair: '',
   liveStatusLoading: false, lastApplyNotice: '', pollTimer: null,
   iran: '', node: '', mode: 'brutal', goal: 'balanced', deep: false, iran_dc: '', node_dc: '',
  };
  c.api = async (method, url, body) => {
   c.calls.push({ method, url, body });
   if (url === 'api/tuner/start') return { status: 202, j: { ok: true, job_id: 'job_mock_1', job: { job_id: 'job_mock_1', iran: 'iran', node: 'node', mode: 'brutal', goal: 'low-latency', status: 'running', phase: 'starting_responder', live_trials: [] } } };
   if (url === 'api/tuner/jobs') return { status: 200, j: { jobs: jobsReply } };
   if (url.startsWith('api/tuner/status')) return { status: 200, j: { ok: true, iran: { ok: true, applied: true, profile_name: 'arvan-eu', current_mtu: 1460, current_qdisc_live: 'fq', current_route: { initcwnd: 20 }, current_sysctl: { cc: 'bbr', rmem_max: '16777216', notsent_lowat: '262144' }, applied_at: '2026-11-24T12:00:00Z' }, node: { ok: true, applied: false, current_mtu: 1500, current_qdisc_live: 'fq_codel', current_sysctl: { cc: 'cubic', rmem_max: '212992', notsent_lowat: '4294967295' } } } };
   if (url === 'api/tuner/apply') return { status: 200, j: { ok: true, iran_result: { ok: true, applied: ['mtu=1460', 'cc=bbr'], unsupported: [] }, node_result: { ok: true, applied: ['cc=bbr'], unsupported: [] } } };
   return { status: 200, j: { ok: true, profile: { id: 'prof_1' } } };
  };
  vm.runInContext(
   definition('parseHash') + '\n' +
   definition('iranServers') + '\n' +
   definition('_tunerPhaseLabel') + '\n' +
   definition('_fmtTunerBytes') + '\n' +
   definition('_renderTunerLiveStatusSide') + '\n' +
   definition('_renderTunerLiveStatusInner') + '\n' +
   definition('loadTunerLiveStatus') + '\n' +
   definition('onTunerPairChange') + '\n' +
   definition('_upsertTunerJob') + '\n' +
   definition('loadTunerJobs') + '\n' +
   definition('selectTunerJob') + '\n' +
   definition('dismissTunerJob') + '\n' +
   definition('startTunerJob') + '\n' +
   definition('importTunerProfile') + '\n' +
   definition('applyTunerProfileBoth') + '\n' +
   definition('rollbackTunerBoth') + '\n' +
   definition('_renderTunerProgressTop') + '\n' +
   definition('_renderTunerLiveRows') + '\n' +
   definition('_renderTunerProgressBody') + '\n' +
   definition('_patchTunerProgressBox') + '\n' +
   definition('_renderTunerConfigSummary') + '\n' +
   definition('_renderTunerResultsCard') + '\n' +
   definition('_renderTunerLibraryRows') + '\n' +
   definition('renderTunerPage'),
   c
  );

 assert.deepEqual(JSON.parse(JSON.stringify(c.parseHash())), { page: 'tuner', param: null });
 await c.startTunerJob();
 const stCall = c.calls.find(x => x.url === 'api/tuner/start');
 assert.ok(stCall);
 assert.equal(stCall.body.goal, 'low-latency');
 assert.equal(stCall.body.deep, true);
 assert.equal(stCall.body.tags.iran_dc, 'arvan-thr');
 assert.equal(polledJobId, 'job_mock_1');

 await c.importTunerProfile('custom-dc', 'rthprof1:abcdefghijklmnop');
 assert.ok(c.calls.some(x => x.url === 'api/tuner/profiles' && x.body.profile === 'rthprof1:abcdefghijklmnop'));

 await c.applyTunerProfileBoth('rthprof1:abcdefghijklmnop', '');
 assert.ok(c.calls.some(x => x.url === 'api/tuner/apply' && x.body.iran === 'iran' && x.body.node === 'node'));

 await c.rollbackTunerBoth();
 assert.ok(c.calls.some(x => x.url === 'api/tuner/rollback' && x.body.iran === 'iran' && x.body.node === 'node'));

 // Rehydration after page reload: running job with live_trials & PMTU resumes polling
 polledJobId = '';
 c.TUNER_STATE.job = null;
 c.TUNER_STATE.activeJobId = null;
 c.TUNER_STATE.jobsLoaded = false;
 jobsReply = [{
  job_id: 'job_live_77', iran: 'iran', node: 'node', mode: 'brutal', goal: 'balanced',
  status: 'running', phase: 'cc_qdisc_pacing', stage_index: 2, stage_total: 6,
  completed_trials: 4, estimated_trials: 14, best_so_far: 91.8, elapsed_s: 12.4,
  current_candidate: 'bbr_fq_lw32768',
  pmtu: { forward_bytes: 1420, reverse_bytes: 1420, blackhole_detected: false },
  live_trials: [{ id: 's2_0', name: 'bbr_fq_lw32768', stage: 2, throughput_mbps: 418.7, loaded_rtt_p95_ms: 46.2, jitter_ms: 2.9, retrans_pct: 0.15, score: 91.8, disqualified: false }],
 }];
 await c.loadTunerJobs(true);
 assert.equal(polledJobId, 'job_live_77');
 assert.ok(els.page.innerHTML.includes('PMTU 1420B'));
 assert.ok(els.page.innerHTML.includes('bbr_fq_lw32768'));
 assert.ok(els.page.innerHTML.includes('418.7'));
 assert.equal((els.page.innerHTML.match(/class="tuner-stage /g) || []).length, 6);

 // Rehydrated error job renders explicit diagnostic box with error text
 jobsReply = [{
  job_id: 'job_err_1', iran: 'iran', node: 'node', status: 'error', phase: 'error',
  stage_index: 0, stage_total: 6, elapsed_s: 15.1, error: '[iran bench] ConnectionError: port 29890 blocked',
 }];
 await c.loadTunerJobs(true);
 assert.ok(els.page.innerHTML.includes('tuner-err-detail'));
 assert.ok(els.page.innerHTML.includes('ConnectionError: port 29890 blocked'));

 // A/B test-profile result renders cleanly without profile_b64 copy/apply controls
 c.TUNER_STATE.lastReport = {
  ok: true, goal: 'balanced', profile_name: 'arvan-ab',
  baseline: { throughput_mbps: 150, loaded_rtt_p95_ms: 120, jitter_ms: 9, retrans_pct: 1.1, stability_cov: 0.1, scores: { balanced: 60 } },
  candidate: { throughput_mbps: 260, loaded_rtt_p95_ms: 55, jitter_ms: 3, retrans_pct: 0.2, stability_cov: 0.03, scores: { balanced: 90 } },
  delta: { throughput_pct: 73.3, loaded_rtt_p95_diff_ms: -65, goal_score_diff: 30 },
 };
 const abHtml = c._renderTunerResultsCard();
 assert.ok(abHtml.includes('arvan-ab') && abHtml.includes('tuner_ab_delta'));

 // Table alignment & incremental scroll-safe patching regression checks
 const cssSrc = fs.readFileSync(path.join(__dirname, '../rathole-manager/ratholehub/ui/app.css'), 'utf8');
 assert.ok(cssSrc.includes('.tuner-tbl th.num, .tuner-tbl td.num'), 'app.css missing .tuner-tbl numeric center alignment');
 assert.ok(cssSrc.includes('.tuner-res-tbl'), 'app.css missing .tuner-res-tbl');

 c.TUNER_STATE.job = {
  job_id: 'job_scroll_1', iran: 'iran', node: 'node', mode: 'brutal', goal: 'balanced',
  status: 'running', phase: 'cc_qdisc_pacing', stage_index: 2, stage_total: 6,
  completed_trials: 1, estimated_trials: 12, best_so_far: 85.0, elapsed_s: 5.0,
  live_trials: [{ id: 't1', name: 'mtu_1460', stage: 1, throughput_mbps: 310.5, loaded_rtt_p95_ms: 48.0, jitter_ms: 3.1, retrans_pct: 0.2, score: 85.0, disqualified: false }],
 };
 const liveBodyHtml = c._renderTunerProgressBody();
 assert.equal(/<td[^>]*\bdir="ltr"/.test(liveBodyHtml), false, 'live table <td> must not override dir="ltr"');
 assert.equal(/<td[^>]*\bdir="ltr"/.test(abHtml), false, 'results table <td> must not override dir="ltr"');
 assert.ok(liveBodyHtml.includes('class="tuner-tbl"') && liveBodyHtml.includes('<th class="num">Mbps</th>') && liveBodyHtml.includes('<td class="num mono"><bdi dir="ltr">310.5</bdi></td>'));
 assert.ok(abHtml.includes('class="tuner-tbl tuner-res-tbl"') && abHtml.includes('<th class="num">tuner_baseline</th>'));

 let pbWiped = 0;
 const topNode = { innerHTML: '', dataset: {} };
 const secNode = { hidden: false };
 const cntNode = { textContent: '1' };
 const wrapNode = { scrollTop: 180, scrollLeft: 24 };
 const tbodyNode = { innerHTML: '', dataset: {} };
 const pbNodes = {
  '#tn_prog_top': topNode,
  '#tn_live_sec': secNode,
  '#tn_live_cnt': cntNode,
  '#tn_live_wrap': wrapNode,
  '#tn_live_tbody': tbodyNode,
 };
 const pbMock = {
  set innerHTML(_v) { pbWiped += 1; },
  querySelector(sel) { return pbNodes[sel] || null; },
 };
 c._patchTunerProgressBox(pbMock);
 assert.equal(pbWiped, 0, '_patchTunerProgressBox must update children without wiping pb.innerHTML');
 assert.equal(wrapNode.scrollTop, 180);
 assert.equal(wrapNode.scrollLeft, 24);
 // Unchanged trials -> skips tbody rewrite; new trial -> updates tbody and preserves scroll
 const prevTbody = tbodyNode.innerHTML;
 c.TUNER_STATE.job.elapsed_s = 6.2;
 c._patchTunerProgressBox(pbMock);
 assert.equal(tbodyNode.innerHTML, prevTbody);
 c.TUNER_STATE.job.live_trials.push({ id: 't2', name: 'bbr_fq_lw32768', stage: 2, throughput_mbps: 420.0, loaded_rtt_p95_ms: 42.0, jitter_ms: 2.0, retrans_pct: 0.1, score: 92.4, disqualified: false });
 c._patchTunerProgressBox(pbMock);
 assert.equal(pbWiped, 0);
 assert.equal(cntNode.textContent, '2');
 assert.ok(tbodyNode.innerHTML.includes('bbr_fq_lw32768'));
 assert.equal(wrapNode.scrollTop, 180);
 assert.equal(wrapNode.scrollLeft, 24);

 // Live applied kernel status card & apply/config preview checks
 await c.loadTunerLiveStatus(true);
 assert.ok(els.tn_status_box.innerHTML.includes('arvan-eu'));
 assert.ok(els.tn_status_box.innerHTML.includes('CC=bbr'));
 assert.ok(els.tn_status_box.innerHTML.includes('MTU=1460'));
 assert.ok(els.tn_status_box.innerHTML.includes('rmem=16 MiB'));
 c.TUNER_STATE.lastReport = {
  ok: true, goal: 'balanced', profile_b64: 'rthprof1:abcdefghijklmnop',
  profile: { meta: { goal: 'balanced' }, iran_config: { mtu: 1460, qdisc: { kind: 'fq' }, route: { initcwnd: 20 }, sysctl: { 'net.ipv4.tcp_congestion_control': 'bbr', 'net.core.rmem_max': 16777216, 'net.ipv4.tcp_notsent_lowat': 262144 } }, node_config: { recommended_carrier: { lane: 'backhaul' } } },
  benchmarks: { baseline: { throughput_mbps: 100, scores: { balanced: 50 } }, winner: { throughput_mbps: 250, scores: { balanced: 90 } } },
 };
 const resWithCfg = c._renderTunerResultsCard();
 assert.ok(resWithCfg.includes('tuner_winner_cfg') && resWithCfg.includes('CC=bbr') && resWithCfg.includes('carrier=backhaul'));
 await c.applyTunerProfileBoth('rthprof1:abcdefghijklmnop', '');
 assert.ok(c.TUNER_STATE.lastApplyNotice.includes('Iran:2, Node:1'));
 assert.ok(c.TUNER_STATE.lastApplyNotice.includes('tuner_reconnect_hint'));
});
