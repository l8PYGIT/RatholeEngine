const $=id=>document.getElementById(id);
let TOKEN=localStorage.getItem('rh_token')||'';
let SERVERS=[];
let LANG=localStorage.getItem('rh_lang')||'fa';
let THEME_PREF=(()=>{const s=localStorage.getItem('rh_theme');return (s==='light'||s==='dark')?s:'';})();

function t(k){return (DICT[LANG]&&DICT[LANG][k])||DICT.fa[k]||k;}

function systemTheme(){
 return (typeof matchMedia==='function'&&matchMedia('(prefers-color-scheme:light)').matches)?'light':'dark';
}
function resolvedTheme(){
 return THEME_PREF||systemTheme();
}
function applyStatic(){
 document.documentElement.lang=LANG;
 document.documentElement.dir=(LANG==='fa'?'rtl':'ltr');
 const m=document.querySelector('meta[name="color-scheme"]');
 if(m)m.content=THEME_PREF||'light dark';
 document.documentElement.dataset.theme=resolvedTheme();
 document.documentElement.classList.toggle('sb-collapsed',localStorage.getItem('rh_sb_collapsed')==='1');
}
function toggleLang(){
 LANG=(LANG==='fa'?'en':'fa');
 localStorage.setItem('rh_lang',LANG);
 applyStatic();
 shell();
}
function toggleTheme(){
 const target=resolvedTheme()==='dark'?'light':'dark';
 if(target===systemTheme()){
  THEME_PREF='';
  localStorage.removeItem('rh_theme');
 }else{
  THEME_PREF=target;
  localStorage.setItem('rh_theme',target);
 }
 applyStatic();
 if(ROUTE.page==='settings')renderSettingsPage();
}
function setThemeMode(mode){
 if(mode==='light'||mode==='dark'){
  THEME_PREF=mode;
  localStorage.setItem('rh_theme',mode);
 }else{
  THEME_PREF='';
  localStorage.removeItem('rh_theme');
 }
 applyStatic();
 document.querySelectorAll('[data-theme-opt]').forEach(b=>b.classList.toggle('on',b.dataset.themeOpt===(THEME_PREF||'system')));
}
function toggleSidebar(){
 const next=localStorage.getItem('rh_sb_collapsed')==='1'?'0':'1';
 if(next==='1')localStorage.setItem('rh_sb_collapsed','1');
 else localStorage.removeItem('rh_sb_collapsed');
 document.documentElement.classList.toggle('sb-collapsed',next==='1');
 const b=$('sb_toggle');
 if(b){const txt=t(next==='1'?'sb_expand':'sb_collapse');b.title=txt;b.setAttribute('aria-label',txt);}
}
function togglePwVis(){
 const pw=$('pw'),btn=$('pw_eye');
 if(!pw||!btn)return;
 const show=pw.type==='password';
 pw.type=show?'text':'password';
 btn.setAttribute('aria-label',t(show?'pw_hide':'pw_show'));
 btn.title=t(show?'pw_hide':'pw_show');
 const useEl=btn.querySelector('use');
 if(useEl)useEl.setAttribute('href',show?'#i-eye-off':'#i-eye');
}
function confirmT(k,extra){return confirm(t(k)+(extra?(' '+extra):'')+' ?');}

function h(t){return (''+(t==null?'':t)).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function icon(name){return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;}
function toast(t,ms=5000){
 const e=$('toast');if(!e)return;
 e.textContent=t;
 const s=String(t||'');
 e.classList.remove('toast-ok','toast-err','toast-sync');
 if(ms===0||s.includes('⏳'))e.classList.add('toast-sync');
 else if(s.startsWith('✓')||s.includes('✓'))e.classList.add('toast-ok');
 else if(s.startsWith('✗')||s.startsWith('⚠️')||/^error:/i.test(s))e.classList.add('toast-err');
 e.classList.add('show');
 clearTimeout(e._t);
 if(ms>0)e._t=setTimeout(()=>e.classList.remove('show'),ms);
}
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
 if(TOKEN)o.headers['Authorization']='Bearer '+TOKEN; if(b)o.body=JSON.stringify(b);
 try{
  const r=await fetch(p,o); let j={};try{j=await r.json()}catch(e){}
  if(r.status===401){TOKEN='';localStorage.removeItem('rh_token');shell();} return {status:r.status,j};
 }catch(e){return {status:0,j:{error:'network error: '+(e&&e.message||e)}};}}
function logout(){TOKEN='';localStorage.removeItem('rh_token');shell();}

let supportsDisplayTransition;
function canTransitionDisplay(){
 if(supportsDisplayTransition!==undefined)return supportsDisplayTransition;
 if(!window.CSS?.supports?.('transition-behavior','allow-discrete')||!document.body)return false;
 const probe=document.createElement('div');
 probe.style.cssText='transition: display 1s allow-discrete !important; display: block;';
 document.body.appendChild(probe);
 getComputedStyle(probe).display;
 probe.style.display='none';
 supportsDisplayTransition=getComputedStyle(probe).display==='block';
 probe.remove();
 return supportsDisplayTransition;
}
function supportsTopLayerExit(){
 return Boolean(window.CSS?.supports?.('overlay','auto')&&canTransitionDisplay());
}
function bindDialogLightDismiss(dlg){
 if('closedBy' in HTMLDialogElement.prototype||dlg._rthLightBound)return;
 dlg._rthLightBound=true;
 const outside=(e)=>{
  const r=dlg.getBoundingClientRect();
  return e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom;
 };
 let pressedOutside=false;
 dlg.addEventListener('pointerdown',e=>{pressedOutside=outside(e);});
 dlg.addEventListener('pointerup',e=>{if(pressedOutside&&outside(e))closeTopLayer(dlg);});
}
async function closeTopLayer(dlg){
 if(!dlg||!dlg.open)return;
 const token=(dlg._closingToken=(dlg._closingToken||0)+1);
 if(!supportsTopLayerExit()){
  dlg.setAttribute('data-closing','');
  const anims=dlg.getAnimations?dlg.getAnimations({subtree:true}):[];
  if(anims.length>0){
   await Promise.race([Promise.allSettled(anims.map(a=>a.finished)),new Promise(r=>setTimeout(r,450))]);
  }
  if(token!==dlg._closingToken||!dlg.hasAttribute('data-closing'))return;
  dlg.removeAttribute('data-closing');
 }
 if(dlg.open)dlg.close();
}
function modal(html){
 let dlg=$('modal');
 if(!dlg){
  dlg=document.createElement('dialog');
  dlg.id='modal';
  dlg.className='modal-dialog';
  dlg.setAttribute('closedby','any');
  dlg.addEventListener('cancel',e=>{e.preventDefault();closeTopLayer(dlg);});
  dlg.addEventListener('close',()=>{dlg.returnValue='';dlg.removeAttribute('data-closing');dlg.innerHTML='';});
  bindDialogLightDismiss(dlg);
  document.body.appendChild(dlg);
 }
 dlg._closingToken=(dlg._closingToken||0)+1;
 dlg.removeAttribute('data-closing');
 dlg.innerHTML=`<div class="mbox"><button class="modal-close" type="button" onclick="closeModal()" aria-label="${h(t('close'))}">${icon('close')}</button><div class="modal-content">${html}</div></div>`;
 const box=dlg.querySelector('.mbox'),title=box.querySelector('h1,h2,h3');
 if(title){title.id='modal_title';dlg.setAttribute('aria-labelledby','modal_title');dlg.removeAttribute('aria-label');}
 else{dlg.removeAttribute('aria-labelledby');dlg.setAttribute('aria-label',t('settings'));}
 box.querySelectorAll('label:not([for])').forEach((label,i)=>{const control=label.parentElement&&label.parentElement.querySelector('input,select,textarea');if(control){if(!control.id)control.id='modal_field_'+i;label.htmlFor=control.id;}});
 if(!dlg.open)dlg.showModal();
 requestAnimationFrame(()=>{
  const first=box.querySelector('[autofocus],input:not([disabled]),select:not([disabled]),button:not(.modal-close):not([disabled])')||box.querySelector('.modal-close');
  if(first)first.focus();
 });
}
function closeModal(){const dlg=$('modal');if(dlg)closeTopLayer(dlg);}

// ---------- form modal (jaigozin prompt zanjire-i) ----------
// fields: [{id,label,type,val,ph,opts:[{v,t}],req}]  onOk(values)
function formModal(title,fields,onOk){
 const rows=fields.map(f=>{
  let inp;
  const req=f.req?' required aria-required="true"':'';
  if(f.type==='select'){inp=`<select id="f_${f.id}" name="${h(f.id)}"${req}>`+f.opts.map(o=>`<option value="${h(o.v)}"${o.v==(f.val||'')?' selected':''}>${h(o.t)}</option>`).join('')+`</select>`;}
  else{inp=`<input id="f_${f.id}" name="${h(f.id)}" type="${f.type||'text'}" value="${h(f.val==null?'':f.val)}" placeholder="${h(f.ph||'')}"${req}>`;}
  return `<div class="row"><label for="f_${f.id}">${h(f.label)}${f.req?' *':''}</label>${inp}</div>`;
 }).join('');
 modal(`<h3>${h(title)}</h3><div class="form-error" id="f_error" role="alert"></div>${rows}<div class="modal-actions">
  <button class="gh" type="button" onclick="closeModal()">${t('cancel')}</button>
  <button class="g" type="button" id="f_ok">${t('save')}</button></div>`);
 $('f_ok').onclick=()=>{
  const v={};let firstBad=null;
  fields.forEach(f=>{const el=$('f_'+f.id);v[f.id]=(el.value||'').trim();const bad=f.req&&!v[f.id];el.setAttribute('aria-invalid',bad?'true':'false');if(bad&&!firstBad)firstBad=el;});
  if(firstBad){const err=$('f_error');err.textContent=t('fill');err.classList.add('show');firstBad.focus();return;}
  onOk(v);
 };
}
const PROF=[{v:'balanced',t:'balanced'},{v:'lossy',t:'lossy'},{v:'aggressive',t:'aggressive'}];

setInterval(()=>{const c=$('clock');if(c)c.textContent=new Date().toLocaleTimeString(LANG==='fa'?'fa-IR':'en-US');},1000);

// ---------- router (hash-based ta posht-e /hub/ ham kar konad) ----------
let OVS={};                                            // cache: name -> akharin overview
let VIEW=localStorage.getItem('rh_view')||'grid';      // chinesh dashboard: grid|list
let ROUTE={page:'dashboard',param:null};
let _navAnimate=false, _tabAnimate=false;
function parseHash(){const hh=location.hash||'#/dashboard';
 let m=hh.match(/^#\/server\/([A-Za-z0-9_-]+)$/); if(m)return{page:'server',param:m[1]};
 m=hh.match(/^#\/(dashboard|routing|tuner|audit|settings)$/); return m?{page:m[1],param:null}:{page:'dashboard',param:null};
}
function nav(hh){if(location.hash===hh){router();}else{location.hash=hh;}}
window.addEventListener('hashchange',()=>{if(TOKEN)router();});
function markNav(){document.querySelectorAll('.sitem').forEach(e=>{
 const active=e.dataset.pg===ROUTE.page;e.classList.toggle('active',active);e.setAttribute('aria-current',active?'page':'false');});}
async function router(){
 if(!TOKEN)return; if(typeof closeAllMoreMenus==='function')closeAllMoreMenus(null,true); ROUTE=parseHash(); markNav();
 if(ROUTE.page!=='tuner'&&typeof clearTunerPoll==='function')clearTunerPoll();
 await ensureServers();
 _navAnimate=true;
 try{
  const pg=$('page');
  if(ROUTE.page==='server')renderServerPage(ROUTE.param);
  else if(ROUTE.page==='routing')renderRouting();
  else if(ROUTE.page==='tuner')renderTunerPage();
  else if(ROUTE.page==='audit')renderAuditPage();
  else if(ROUTE.page==='settings')renderSettingsPage();
  else renderDashboard();
  if(pg){pg.classList.remove('view-enter');void pg.offsetWidth;pg.classList.add('view-enter');}
 }finally{_navAnimate=false;}
}
async function ensureServers(){if(SERVERS.length)return;const {j}=await api('GET','api/servers');SERVERS=j||[];}
// sazegari ba code-haye ghadimi: refresh-e inventory + safhe-ye faal
async function loadAll(){SERVERS=[];await ensureServers();router();}
// vaghti overview miresad, faghat safhe-ye faal ra be-rooz kon
function onOv(n){
 if(ROUTE.page==='dashboard'){updateCard(n);
  // doctor-e iran vaziat-e tunnel-e node-ha ra moshakhas mikonad → kart-e node-ha ham berooz shavand
  if(fnd(n).role==='iran')SERVERS.filter(s=>s.role==='node').forEach(s=>updateCard(s.name));
  updateHubStrip();updateDashboardKpis();}
 else if(ROUTE.page==='server'&&ROUTE.param===n)renderServerPage(n);
 else if(ROUTE.page==='server'&&fnd(n).role==='iran'&&fnd(ROUTE.param).role==='node')renderServerPage(ROUTE.param);
 else if(ROUTE.page==='routing')scheduleGraph();
}
const _ovInFlight={};
async function loadOv(n){
 if(_ovInFlight[n])return _ovInFlight[n];
 _ovInFlight[n]=(async()=>{
  try{const {j}=await api('GET','api/servers/'+n+'/overview');OVS[n]=j||{};onOv(n);}
  finally{delete _ovInFlight[n];}
 })();
 return _ovInFlight[n];
}

// ---------- Raycast Command Palette (Ctrl+K / Cmd+K) ----------
let CMDK_IDX=0, CMDK_ITEMS=[];
function cmdkEntries(query){
 const q=String(query||'').trim().toLowerCase();
 const out=[];
 SERVERS.forEach(s=>{
  const host=s.transport==='api'?(s.api_url||''):(s.host||'');
  const txt=(s.name+' '+s.role+' '+host).toLowerCase();
  if(!q||txt.includes(q)){
   const ov=OVS[s.name];
   const dot=ovDotCls(s.name,ov);
   out.push({sec:'servers',icon:'server',dot,label:s.name,meta:s.role.toUpperCase()+' · '+host,run:()=>nav('#/server/'+s.name)});
  }
 });
 [
  {id:'dashboard',icon:'dashboard',label:t('nav_dash'),meta:'#/dashboard',run:()=>nav('#/dashboard')},
  {id:'routing',icon:'route',label:t('nav_routing'),meta:'#/routing',run:()=>nav('#/routing')},
  {id:'tuner',icon:'gauge',label:t('nav_tuner'),meta:'#/tuner',run:()=>nav('#/tuner')},
  {id:'audit',icon:'history',label:t('audit'),meta:'#/audit',run:()=>nav('#/audit')},
  {id:'settings',icon:'settings',label:t('settings'),meta:'#/settings',run:()=>nav('#/settings')}
 ].forEach(pg=>{
  if(!q||(pg.label+' '+pg.id).toLowerCase().includes(q))out.push({sec:'pages',...pg});
 });
 [
  {icon:'server',label:t('cmdk_add_srv'),meta:'+',run:()=>{nav('#/dashboard');requestAnimationFrame(()=>{const d=$('add_srv_details');if(d){toggleDiagDetails(d,true);const inp=$('n');if(inp)inp.focus();}});}},
  {icon:'shield',label:t('hub_proxy_btn'),meta:'Proxy',run:()=>editHubProxy()},
  {icon:'download',label:t('upd_all'),meta:'Deploy',run:()=>{nav('#/dashboard');updateAll();}},
  {icon:'refresh',label:t('refresh'),meta:'Sync',run:()=>refreshPage()},
  {icon:'sidebar',label:t('cmdk_toggle_sb'),meta:'Sidebar',run:()=>toggleSidebar()},
  {icon:'theme',label:t('cmdk_toggle_theme'),meta:'Theme',run:()=>toggleTheme()},
  {icon:'language',label:t('cmdk_toggle_lang'),meta:LANG==='fa'?'EN':'FA',run:()=>toggleLang()}
 ].forEach(act=>{
  if(!q||(act.label+' '+act.meta).toLowerCase().includes(q))out.push({sec:'actions',...act});
 });
 return out;
}
function renderCmdkList(){
 const list=$('cmdk_list'), inp=$('cmdk_in');
 if(!list)return;
 CMDK_ITEMS=cmdkEntries(inp?inp.value:'');
 if(!CMDK_ITEMS.length){list.innerHTML=`<div class="empty" style="padding:18px;text-align:center">${h(t('cmdk_empty'))}</div>`;return;}
 if(CMDK_IDX>=CMDK_ITEMS.length)CMDK_IDX=0;
 if(CMDK_IDX<0)CMDK_IDX=CMDK_ITEMS.length-1;
 const secTitle={servers:t('cmdk_sec_servers'),pages:t('cmdk_sec_pages'),actions:t('cmdk_sec_actions')};
 let curSec='', html='';
 CMDK_ITEMS.forEach((it,i)=>{
  if(it.sec!==curSec){curSec=it.sec;html+=`<div class="cmdk-sec">${h(secTitle[curSec]||curSec)}</div>`;}
  const lead=it.dot?`<span class="dot ${it.dot}"></span>`:icon(it.icon||'search');
  html+=`<button type="button" class="cmdk-item${i===CMDK_IDX?' sel':''}" data-cmdk-idx="${i}">${lead}<span>${h(it.label)}</span><span class="cmdk-meta">${h(it.meta||'')}</span></button>`;
 });
 list.innerHTML=html;
 const active=list.querySelector('.cmdk-item.sel');
 if(active&&active.scrollIntoView)active.scrollIntoView({block:'nearest'});
}
function execCmdkIdx(i){
 const it=CMDK_ITEMS[i];
 if(!it)return;
 closeCmdPalette();
 it.run();
}
function closeCmdPalette(){const d=$('cmdk');if(d)closeTopLayer(d);}
function openCmdPalette(preset=''){
 if(!TOKEN)return;
 let dlg=$('cmdk');
 if(!dlg){
  dlg=document.createElement('dialog');
  dlg.id='cmdk';
  dlg.className='cmdk-dialog';
  dlg.setAttribute('closedby','any');
  dlg.setAttribute('aria-label',t('cmdk_btn'));
  dlg.addEventListener('cancel',e=>{e.preventDefault();closeTopLayer(dlg);});
  dlg.addEventListener('close',()=>{dlg.returnValue='';dlg.removeAttribute('data-closing');dlg.innerHTML='';});
  bindDialogLightDismiss(dlg);
  document.body.appendChild(dlg);
 }
 dlg._closingToken=(dlg._closingToken||0)+1;
 dlg.removeAttribute('data-closing');
 dlg.innerHTML=`<div class="cmdk-box">
  <div class="cmdk-head">${icon('search')}<input id="cmdk_in" class="cmdk-input" type="search" value="${h(preset)}" placeholder="${h(t('cmdk_ph'))}" autocomplete="off"><span class="kbd">ESC</span></div>
  <div class="cmdk-list" id="cmdk_list"></div>
  <div class="cmdk-foot"><span>${h(t('cmdk_hint_nav'))}</span><span class="kbd">⌘K / Ctrl+K</span></div>
 </div>`;
 CMDK_IDX=0;
 renderCmdkList();
 const inp=$('cmdk_in'), list=$('cmdk_list');
 if(inp){
  inp.addEventListener('input',()=>{CMDK_IDX=0;renderCmdkList();});
  inp.addEventListener('keydown',e=>{
   if(e.key==='ArrowDown'){e.preventDefault();if(CMDK_ITEMS.length){CMDK_IDX=(CMDK_IDX+1)%CMDK_ITEMS.length;renderCmdkList();}}
   else if(e.key==='ArrowUp'){e.preventDefault();if(CMDK_ITEMS.length){CMDK_IDX=(CMDK_IDX-1+CMDK_ITEMS.length)%CMDK_ITEMS.length;renderCmdkList();}}
   else if(e.key==='Enter'){e.preventDefault();execCmdkIdx(CMDK_IDX);}
  });
 }
 if(list){
  list.addEventListener('click',e=>{const b=e.target.closest('[data-cmdk-idx]');if(b)execCmdkIdx(+b.dataset.cmdkIdx);});
 }
 if(!dlg.open)dlg.showModal();
 requestAnimationFrame(()=>{if(inp)inp.focus();});
}

function shell(){
 if(typeof closeAllMoreMenus==='function')closeAllMoreMenus(null,true);
 applyStatic();
 if(!TOKEN){document.body.classList.add('login');
  $('app').innerHTML=`<main id="page"><section class="login-panel" aria-labelledby="login_title">
   <div class="login-brand"><span class="brand-mark">${icon('brand')}</span><div><div class="brand-name">rathole<span>hub</span></div></div></div>
   <div class="login-body"><h1 id="login_title">${t('login_title')}</h1><p class="login-sub">${h(t('login_sub'))}</p>
    <div class="field"><label for="pw">${t('pw_ph')}</label><div class="login-actions"><div class="pw-wrap"><input id="pw" type="password" autocomplete="current-password" aria-describedby="msg"><button id="pw_eye" class="pw-eye" type="button" onclick="togglePwVis()" title="${h(t('pw_show'))}" aria-label="${h(t('pw_show'))}">${icon('eye')}</button></div><button class="g" type="button" onclick="doLogin()">${t('login_btn')}</button></div></div>
    <div id="totp_wrap" class="field" style="display:none"><label for="totp">${t('sec_2fa_code')}</label><input id="totp" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="${h(t('totp_ph'))}" aria-describedby="msg"></div>
    <div id="msg" class="form-message" role="alert"></div>
   </div></section></main>`;
  const p=$('pw'); if(p)p.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
  const tp=$('totp'); if(tp)tp.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
  return;}
 document.body.classList.remove('login');
 const sbCollapsed=localStorage.getItem('rh_sb_collapsed')==='1';
 const sbTxt=t(sbCollapsed?'sb_expand':'sb_collapse');
 $('app').innerHTML=`<aside id="sb">
   <div class="sb-top">
    <div class="brand"><span class="brand-mark">${icon('brand')}</span><div class="brand-name">rathole<span>hub</span></div></div>
    <button id="sb_toggle" class="gh sb-toggle" type="button" onclick="toggleSidebar()" title="${h(sbTxt)}" aria-label="${h(sbTxt)}">${icon('sidebar')}</button>
   </div>
   <button class="cmdk-trigger" type="button" onclick="openCmdPalette()" title="${h(t('cmdk_btn'))}"><span class="cmdk-trig-l">${icon('search')}<span class="cmdk-trig-txt">${h(t('cmdk_btn'))}</span></span><span class="kbd">⌘K</span></button>
   <nav class="nav-list" aria-label="${h(t('nav_label'))}">
    <button class="sitem" type="button" data-pg="dashboard" onclick="nav('#/dashboard')" title="${h(t('nav_dash'))}">${icon('dashboard')}<span>${t('nav_dash')}</span></button>
    <button class="sitem" type="button" data-pg="routing" onclick="nav('#/routing')" title="${h(t('nav_routing'))}">${icon('route')}<span>${t('nav_routing')}</span></button>
    <button class="sitem" type="button" data-pg="tuner" onclick="nav('#/tuner')" title="${h(t('nav_tuner'))}">${icon('gauge')}<span>${t('nav_tuner')}</span></button>
    <button class="sitem" type="button" data-pg="audit" onclick="nav('#/audit')" title="${h(t('audit'))}">${icon('history')}<span>${t('audit')}</span></button>
    <button class="sitem" type="button" data-pg="settings" onclick="nav('#/settings')" title="${h(t('settings'))}">${icon('settings')}<span>${t('settings')}</span></button>
   </nav>
   <div class="sfoot">
    <div class="sidebar-meta"><span class="clock" id="clock"></span><label class="sw"><input type="checkbox" id="auto" checked><span>${t('auto')}</span></label></div>
    <div class="utility-actions">
     <button class="gh icon-btn" type="button" onclick="toggleLang()" title="${LANG==='fa'?'English':'فارسی'}" aria-label="${LANG==='fa'?'English':'فارسی'}">${icon('language')}</button>
     <button class="gh icon-btn" type="button" onclick="toggleTheme()" title="${t('theme')}" aria-label="${t('theme')}">${icon('theme')}</button>
     <button class="gh icon-btn" type="button" onclick="refreshPage()" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button>
     <button class="s icon-btn" type="button" onclick="logout()" title="${t('logout')}" aria-label="${t('logout')}">${icon('logout')}</button>
    </div>
   </div></aside><main id="page" tabindex="-1"></main>`;
 router();
}
function refreshPage(){SERVERS=[];if(ROUTE.page==='tuner'){TUNER_STATE.jobsLoaded=false;TUNER_STATE.profiles=null;}ensureServers().then(()=>{router();pollByPage();});}
// polling-e hoshmand: faghat overview-haye lazem baraye safhe-ye faal
function pollByPage(){
 if(!TOKEN)return;
 if(ROUTE.page==='server'&&ROUTE.param){loadOv(ROUTE.param);
  // vaziat-e tunnel-e node az doctor-e Iran miayad → overview-e Iran-ha ham lazem ast
  if(fnd(ROUTE.param).role==='node')SERVERS.filter(s=>s.role==='iran').forEach(s=>loadOv(s.name));}
 else if(ROUTE.page==='dashboard'||ROUTE.page==='routing'){SERVERS.forEach(s=>loadOv(s.name));}
 if(ROUTE.page==='dashboard')loadHubStatus();
}
async function doLogin(){
 const totpEl=$('totp'), tw=$('totp_wrap');
 const body={password:$('pw').value};
 const totpVal=totpEl?(totpEl.value||'').trim():'';
 if(totpVal)body.totp=totpVal;
 const {status,j}=await api('POST','api/login',body);
 if(status===200){
  $('pw').setAttribute('aria-invalid','false');
  if(totpEl)totpEl.setAttribute('aria-invalid','false');
  TOKEN=j.token;localStorage.setItem('rh_token',TOKEN);
  if(!location.hash)location.hash='#/dashboard';
  shell();
 }else if(status===401&&j&&j.totp_required){
  if(tw){tw.style.display='';if('hidden' in tw)tw.hidden=false;}
  if(totpEl){totpEl.setAttribute('aria-invalid',j.error==='bad totp'?'true':'false');totpEl.focus();}
  $('msg').textContent=(j.error==='bad totp')?t('totp_wrong'):t('totp_hint');
 }else{
  $('pw').setAttribute('aria-invalid','true');
  $('msg').textContent=t('pw_wrong');
  $('pw').focus();
 }
}
function fnd(n){return SERVERS.find(s=>s.name===n)||{};}
function setDot(n,cls){const d=$('dot_'+n); if(d)d.className='dot '+cls;}

// ---------- vaziat-e vasl boodan-e tunnel-e node (az doctor-e serverhaye Iran) ----------
// doctor rooye Iran har node ra ok/warn mikonad; inja natije baraye yek server-e node
// jam mishavad: 'ok' (hameye service-ha vasl), 'warn' (hadaghal yeki ghat), ya null (namalum).
function nodeTunnelStatus(n){
 const ov=OVS[n]; if(!ov||ov.reachable===false)return null;
 const keys=[n].concat([...(ov.services||[]),...(ov.backhaul_services||[])].map(x=>x.name));
 (ov.upstreams||[]).forEach(u=>(u.services||[]).forEach(x=>keys.push(x.name)));
 let seen=false,bad=false;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  keys.forEach(k=>{if(k in hn){seen=true;if(hn[k]==='warn')bad=true;}});
 });
 return seen?(bad?'warn':'ok'):null;
}
// ---------- badge-haye khoolase (moshtarak beyne kart va safhe-ye server) ----------
function headBadges(n,ov){
 const role=fnd(n).role;
 if(!ov||ov.reachable===false)return `<span class="badge b-bad">${t(fnd(n).transport==='api'?'no_agent':'no_ssh')}</span>`;
 let hb='';
 if(role==='iran'){
  const hObj=ov.health||{};
  const hTot=(hObj.ok||0)+(hObj.fail||0);
  const ok=(hObj.fail||0)===0;
  hb=hTot>0
   ? `<span class="badge ${ok?'b-ok':'b-bad'}">✓ ${hObj.ok||0}/${hTot}</span>`
   : `<span class="badge b-ok">online</span>`;
  const nodes=ov.nodes||[];
  const modes=[];
  nodes.forEach(d=>{const m=iranNodeMode(ov,d.name);if(modes.indexOf(m)<0)modes.push(m);});
  const k=ov.kcp||{};
  if(nodes.length){
   modes.forEach(m=>{
    const cls=['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre','paqet','game'].includes(m)?m:'ws';
    hb+=` <span class="badge b-${cls}" dir="ltr">${h(carrierLabel(m,ov))}</span>`;
   });
   if(k.enabled&&modes.indexOf('kcp')<0)hb+=` <span class="badge b-kcp" dir="ltr">kcp ${h(k.profile||'')}${k.port?(' :'+h(k.port)):''}${k.stealth?' · QUIC':''}</span>`;
  }else{
   let shown=false;
   const feats=(ov.status||{}).features||{};
   if((ov.frp||{}).enabled||(feats.frp||{}).configured){hb+=` <span class="badge b-frp" dir="ltr">${h(carrierLabel('frp',ov))}</span>`;shown=true;}
   if((ov.backhaul||{}).enabled||(feats.backhaul||{}).configured){hb+=` <span class="badge b-backhaul" dir="ltr">${h(carrierLabel('backhaul',ov))}</span>`;shown=true;}
   if((ov.paqet||{}).enabled||(feats.paqet||{}).configured){hb+=` <span class="badge b-paqet" dir="ltr">${h(carrierLabel('paqet',ov))}</span>`;shown=true;}
   if(k.enabled){hb+=` <span class="badge b-kcp" dir="ltr">kcp ${h(k.profile||'')}${k.port?(' :'+h(k.port)):''}${k.stealth?' · QUIC':''}</span>`;shown=true;}
   const nz=ov.noise||{}; if(nz.enabled){hb+=` <span class="badge b-noise" dir="ltr">noise${nz.port?(' :'+h(nz.port)):''}</span>`;shown=true;}
   if((ov.gre||{}).enabled||(feats.gre||{}).configured){hb+=` <span class="badge b-gre" dir="ltr">GRE</span>`;shown=true;}
   if((ov.plain||{}).enabled||(feats.plain||{}).configured){hb+=` <span class="badge b-plain" dir="ltr">Plain</span>`;shown=true;}
   if(!shown)hb+=' <span class="badge b-ws" dir="ltr">ws/443</span>';
  }
 }else{
  let m = (ov.status && ov.status.main && ov.status.main.transport) || ov.main_tunnel || (ov.kcp||{}).mode || 'ws';
  const cClass=['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre','paqet'].includes(m)?m:'ws';
  const cTitle=h(carrierLabel(m,ov));
  hb=`<span class="badge b-${cClass}" dir="ltr">${cTitle}</span>`;
  if((ov.paqet||{}).enabled&&m!=='paqet')hb+=` <span class="badge b-paqet" dir="ltr">Paqet</span>`;
  if((ov.backhaul_services||[]).length&&m!=='backhaul')hb+=` <span class="badge b-backhaul" dir="ltr">${h(carrierLabel('backhaul',ov))}</span>`;
  const ts=nodeTunnelStatus(n);
  if(ts)hb+=` <span class="badge ${ts==='ok'?'b-ok':'b-bad'}">${ts==='ok'?t('tun_up'):t('tun_down')}</span>`;
 }
 hb+=verBadge(ov);
 return hb;
}
// badge-e noskhe: sabz=hamsan ba akharin (latest_version-e hub), zard=ghadimi-tar (niaz be apdit).
function latestVer(){return (HUBST&&HUBST.latest_version)||'';}
function verBadge(ov){
 const mv=((ov||{}).version||{}).manager||''; if(!mv)return '';
 const lv=latestVer(); const old=lv&&mv!==lv;
 return ` <span class="badge ${old?'b-bad':'b-ok'}" dir="ltr" title="${old?t('ver_old'):t('ver_ok')}">v${h(mv)}${old?' → v'+h(lv):''}</span>`;
}
function ovDotCls(n,ov){
 if(!ov)return 'd-un';
 if(ov.reachable===false)return 'd-bad';
 if(fnd(n).role==='iran')return ((ov.health||{}).fail===0)?'d-ok':'d-bad';
 const ts=nodeTunnelStatus(n);
 return ts==='warn'?'d-bad':'d-ok';
}

// ---------- vaziat-e khod-e server-e hub (strip-e bala-ye dashboard) ----------
let HUBST=null;
function fmtDur(s){if(s==null)return '?';const d=Math.floor(s/86400),hh=Math.floor(s%86400/3600),mm=Math.floor(s%3600/60);
 return (d?d+'d ':'')+(hh?hh+'h ':'')+mm+'m';}
function fmtGB(b){return (b/1073741824).toFixed(1)+'G';}
async function loadHubStatus(){const {j}=await api('GET','api/hubstatus');HUBST=j||null;updateHubStrip();updateDashboardKpis();}
function updateHubStrip(){
 const box=$('hubstrip'); if(!box)return;
 const st=HUBST;
 if(!st){box.innerHTML=`<span class="sub">${t('loading')}</span>`;return;}
 let x=`<span class="badge b-role">${t('hub_box')}</span>`;
 const sv=st.services||{};
 Object.keys(sv).forEach(u=>{const ok=sv[u]==='active';
  x+=`<span class="badge ${ok?'b-ok':'b-bad'}" dir="ltr">${h(u)} ${ok?'✓':'✗'}</span>`;});
 if(st.uptime!=null)x+=`<span class="hub-metric"><span>${h(t('hs_up'))}:</span><b class="mono">${fmtDur(st.uptime)}</b></span>`;
 else if(st.hub_uptime!=null)x+=`<span class="hub-metric"><span>${h(t('hs_up'))} (hub):</span><b class="mono">${fmtDur(st.hub_uptime)}</b></span>`;
 if(st.load)x+=`<span class="hub-metric"><span>${h(t('hs_load'))}:</span><b class="mono">${st.load.join(' ')}</b></span>`;
 if(st.mem_total_kb){const used=st.mem_total_kb-(st.mem_avail_kb||0);
  x+=`<span class="hub-metric"><span>${h(t('hs_mem'))}:</span><b class="mono">${(used/1048576).toFixed(1)}/${(st.mem_total_kb/1048576).toFixed(1)}G</b></span>`;}
 if(st.disk_total)x+=`<span class="hub-metric"><span>${h(t('hs_disk'))}:</span><b class="mono">${fmtGB(st.disk_free)}/${fmtGB(st.disk_total)}</b></span>`;
 // khoolase-ye inventory: chand server up/down (az overview-haye cache-shode)
 let up=0,down=0,unk=0;
 SERVERS.forEach(s=>{const ov=OVS[s.name];
  if(!ov)unk++;else if(ov.reachable===false)down++;else up++;});
 x+=`<span class="badge ${down?'b-bad':'b-ok'}">${up}/${SERVERS.length} ${t('hs_connected')}</span>`;
 const px = st.proxy || '';
 if(px){
  x+=`<button class="badge b-plain" type="button" onclick="editHubProxy()" title="${t('hub_proxy_lbl')} ${h(px)}">🛡️ ${t('badge_proxied')}: <span class="mono">${h(px)}</span></button>`;
 } else {
  x+=`<button class="badge b-ws" type="button" onclick="editHubProxy()" title="${t('hub_proxy_btn')}">+ ${t('badge_proxied')}</button>`;
 }
 box.innerHTML=x;
}
async function editHubProxy(){
 const {j}=await api('GET','api/config');
 const cur=(j&&j.proxy)||'';
 formModal(t('hub_proxy_modal'),[
  {id:'proxy',label:t('hub_proxy_lbl'),val:cur,ph:t('hub_proxy_hint')}
 ], async v=>{
  closeModal();
  const {status,j:res}=await api('POST','api/config',{proxy:v.proxy});
  if(status===200){
   toast(t('saved'));
   loadHubStatus();
  } else {
   toast('error: '+(res.error||status));
  }
 });
}
function toggleConnType(){
 const isApi = $('conn_tr')?.value === 'api';
 document.querySelectorAll('.f-ssh').forEach(el=>el.style.display = isApi ? 'none' : '');
 document.querySelectorAll('.f-api').forEach(el=>el.style.display = isApi ? '' : 'none');
}

// ---------- safhe: dashboard (KPI + filters + grid/list kart-haye khoolase) ----------
let DASH_FILTER={q:'',role:'all',status:'all'};
function filteredServers(){
 const q=DASH_FILTER.q.trim().toLowerCase();
 return SERVERS.filter(s=>{
  if(DASH_FILTER.role!=='all'&&s.role!==DASH_FILTER.role)return false;
  const ov=OVS[s.name];
  const isOnline=Boolean(ov&&ov.reachable!==false);
  const isOffline=Boolean(ov&&ov.reachable===false);
  if(DASH_FILTER.status==='online'&&!isOnline)return false;
  if(DASH_FILTER.status==='offline'&&!isOffline)return false;
  if(q){
   const hay=(s.name+' '+s.role+' '+(s.host||'')+' '+(s.api_url||'')+' '+((ov&&ov.domain)||'')).toLowerCase();
   if(!hay.includes(q))return false;
  }
  return true;
 });
}
function setDashFilter(patch){
 Object.assign(DASH_FILTER,patch);
 document.querySelectorAll('[data-flt-role]').forEach(b=>b.classList.toggle('on',b.dataset.fltRole===DASH_FILTER.role));
 document.querySelectorAll('[data-flt-st]').forEach(b=>b.classList.toggle('on',b.dataset.fltSt===DASH_FILTER.status));
 const clr=$('flt_clr');
 if(clr)clr.style.display=(DASH_FILTER.q||DASH_FILTER.role!=='all'||DASH_FILTER.status!=='all')?'':'none';
 drawCards();
 const c=$('servers');if(c)c.classList.remove('stagger-in');
 SERVERS.forEach(s=>{if(OVS[s.name])updateCard(s.name);});
}
function resetDashFilter(){
 DASH_FILTER={q:'',role:'all',status:'all'};
 const inp=$('srv_q');if(inp)inp.value='';
 setDashFilter({});
}
function updateDashboardKpis(){
 const box=$('kpi_grid'); if(!box)return;
 const irans=SERVERS.filter(s=>s.role==='iran').length;
 const nodes=SERVERS.filter(s=>s.role==='node').length;
 let up=0,down=0,svcs=0;
 SERVERS.forEach(s=>{
  const ov=OVS[s.name];
  if(ov){
   if(ov.reachable===false)down++;
   else{
    up++;
    if(s.role==='iran')svcs+=(ov.nodes||[]).length;
    else svcs+=(ov.services||[]).length+(ov.backhaul_services||[]).length;
   }
  }
 });
 const svs=(HUBST&&HUBST.services)||{};
 const svcKeys=Object.keys(svs);
 const hubOk=!HUBST?null:(svcKeys.length?svcKeys.every(k=>svs[k]==='active'):true);
 const hubLabel=hubOk===null?t('loading'):(hubOk?t('st_ok'):t('st_bad'));
 const hubUp=HUBST?(HUBST.uptime!=null?HUBST.uptime:HUBST.hub_uptime):null;
 box.innerHTML=`
  <div class="kpi-card">
   <div class="kpi-head"><span>${h(t('kpi_servers'))}</span>${icon('server')}</div>
   <div class="kpi-num">${SERVERS.length}</div>
   <div class="kpi-sub">${irans} ${h(t('flt_iran'))} · ${nodes} ${h(t('flt_node'))}</div>
  </div>
  <div class="kpi-card">
   <div class="kpi-head"><span>${h(t('kpi_online'))}</span>${icon('zap')}</div>
   <div class="kpi-num"><span class="dot ${down?'d-bad':'d-ok'}"></span>${up}/${SERVERS.length}</div>
   <div class="kpi-sub">${up} ${h(t('flt_online'))} · ${down} ${h(t('flt_offline'))}</div>
  </div>
  <div class="kpi-card">
   <div class="kpi-head"><span>${h(t('kpi_services'))}</span>${icon('route')}</div>
   <div class="kpi-num">${svcs}</div>
   <div class="kpi-sub">${h(t('n_nodes'))} / ${h(t('n_svcs'))}</div>
  </div>
  <div class="kpi-card">
   <div class="kpi-head"><span>${h(t('kpi_hub'))}</span>${icon('shield')}</div>
   <div class="kpi-num" style="font-size:17px"><span class="dot ${hubOk===null?'d-un':(hubOk?'d-ok':'d-bad')}"></span>${h(hubLabel)}</div>
   <div class="kpi-sub">${hubUp!=null?`${h(t('hs_up'))}: <span class="mono">${h(fmtDur(hubUp))}</span>`:h(t('hub_box'))}</div>
  </div>`;
}
function renderDashboard(){
 const pg=$('page'); if(!pg)return;
 const dirty=Boolean(DASH_FILTER.q||DASH_FILTER.role!=='all'||DASH_FILTER.status!=='all');
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_dash')}</h2><span class="page-count">${SERVERS.length}</span><span class="ptitle-spacer"></span>
   <div class="page-actions"><button class="gh" id="driftbtn" type="button" onclick="checkFleetDrift()">${icon('shield')}${t('drift_check')}</button><button class="g" id="updall" type="button" onclick="updateAll()">${icon('download')}${t('upd_all')}</button>
   <div class="vswitch" role="group" aria-label="${h(t('view'))}"><button id="vg" type="button" class="${VIEW==='grid'?'on':''}" aria-pressed="${VIEW==='grid'}" onclick="setView('grid')">${icon('grid')}${t('view_grid')}</button>
   <button id="vl" type="button" class="${VIEW==='list'?'on':''}" aria-pressed="${VIEW==='list'}" onclick="setView('list')">${icon('list')}${t('view_list')}</button></div></div></div>
  <div id="updpanel"></div>
  <div id="driftpanel"></div>
  <div class="kpi-grid" id="kpi_grid"></div>
  <section class="status-strip" id="hubstrip" aria-label="${h(t('hub_box'))}"></section>
  <details class="diag-sec server-panel" id="add_srv_details">
   <summary>
    <span class="brand-mark" style="width:28px;height:28px;border-radius:8px;display:inline-grid;place-items:center;">${icon('server')}</span>
    <span style="font-size:13.5px;font-weight:700;">${t('add_server')}</span>
    <span class="badge b-role">${t('add_btn')}</span>
   </summary>
   <div class="cbody" style="padding:14px 18px 18px;">
    <div class="server-form">
     <div class="field"><label for="conn_tr">${t('conn_type')}</label><select id="conn_tr" onchange="toggleConnType()"><option value="ssh">${t('conn_ssh')}</option><option value="api">${t('conn_api')}</option></select></div>
     <div class="field"><label for="n">${t('f_name')}</label><input id="n" autocomplete="off"></div>
     <div class="field"><label for="rl">${t('role')}</label><select id="rl"><option value="iran">iran</option><option value="node">node</option></select></div>
     <div class="field host f-ssh"><label for="hh">${t('f_host')}</label><input id="hh" inputmode="url" autocomplete="off"></div>
     <div class="field f-ssh"><label for="uu">${t('f_user')}</label><input id="uu" value="root" autocomplete="username"></div>
     <div class="field f-ssh"><label for="pp">${t('f_port')}</label><input id="pp" value="22" inputmode="numeric"></div>
     <div class="field password f-ssh"><label for="sw">${t('prov_pw')}</label><input id="sw" type="password" autocomplete="new-password"></div>
     <div class="field host f-api" style="display:none;"><label for="api_u">${t('f_api_url')}</label><input id="api_u" placeholder="http://1.2.3.4:8089" autocomplete="off"></div>
     <div class="field password f-api" style="display:none;"><label for="api_tok">${t('f_api_token')}</label><input id="api_tok" type="password" autocomplete="new-password"></div>
     <div class="field"><label for="srv_px">${t('f_proxy_opt')}</label><input id="srv_px" placeholder="socks5://127.0.0.1:10808"></div>
     <div class="field"><label for="isv">${t('l_iran_srv')}</label><select id="isv"><option value="">${t('l_iran_srv')}?</option>${iranSrvOptions()}</select></div>
     <div class="server-form-actions">
      <button class="gh" type="button" onclick="addSrv()">${t('add_btn')}</button>
      <button class="g f-ssh" type="button" onclick="provSrv()">${t('prov_btn')}</button>
     </div>
    </div>
   </div>
  </details>
  <div class="filter-bar">
   <div class="search-box">${icon('search')}<input id="srv_q" type="search" value="${h(DASH_FILTER.q)}" placeholder="${h(t('flt_search_srv'))}" aria-label="${h(t('flt_search_srv'))}"></div>
   <div class="seg-group" role="group" aria-label="${h(t('role'))}">
    <button type="button" class="seg-btn${DASH_FILTER.role==='all'?' on':''}" data-flt-role="all">${h(t('flt_all'))}</button>
    <button type="button" class="seg-btn${DASH_FILTER.role==='iran'?' on':''}" data-flt-role="iran">${h(t('flt_iran'))}</button>
    <button type="button" class="seg-btn${DASH_FILTER.role==='node'?' on':''}" data-flt-role="node">${h(t('flt_node'))}</button>
   </div>
   <div class="seg-group" role="group" aria-label="${h(t('c_status'))}">
    <button type="button" class="seg-btn${DASH_FILTER.status==='all'?' on':''}" data-flt-st="all">${h(t('flt_all'))}</button>
    <button type="button" class="seg-btn${DASH_FILTER.status==='online'?' on':''}" data-flt-st="online">${h(t('flt_online'))}</button>
    <button type="button" class="seg-btn${DASH_FILTER.status==='offline'?' on':''}" data-flt-st="offline">${h(t('flt_offline'))}</button>
   </div>
   <button id="flt_clr" type="button" class="gh" style="${dirty?'':'display:none'}" onclick="resetDashFilter()">${h(t('flt_clear'))}</button>
  </div>
  <div id="servers" class="grid ${VIEW==='list'?'list':''}"></div>`;
 const qEl=$('srv_q');
 if(qEl)qEl.addEventListener('input',()=>setDashFilter({q:qEl.value}));
 updateDashboardKpis();
 drawCards();
 const srvGrid=$('servers');
 if(srvGrid&&typeof _navAnimate!=='undefined'&&_navAnimate)srvGrid.classList.add('stagger-in');
 updateHubStrip(); loadHubStatus();
 SERVERS.forEach(s=>{if(OVS[s.name])updateCard(s.name);loadOv(s.name);});
}
function setView(v){VIEW=v;localStorage.setItem('rh_view',v);
 const c=$('servers');if(c)c.classList.toggle('list',v==='list');
 const vg=$('vg'),vl=$('vl');if(vg){vg.classList.toggle('on',v==='grid');vg.setAttribute('aria-pressed',String(v==='grid'));}if(vl){vl.classList.toggle('on',v==='list');vl.setAttribute('aria-pressed',String(v==='list'));}}
function drawCards(){
 const c=$('servers'); if(!c)return;
 if(!SERVERS.length){c.innerHTML=`<div class="card" style="margin:0"><div class="cbody empty">${t('no_servers')}</div></div>`;return;}
 const list=filteredServers();
 if(!list.length){c.innerHTML=`<div class="card" style="margin:0"><div class="cbody empty">${h(t('flt_no_match'))} <button class="gh" type="button" onclick="resetDashFilter()" style="margin-inline-start:8px">${h(t('flt_clear'))}</button></div></div>`;return;}
 c.innerHTML=list.map(s=>{
  const isIran=s.role==='iran';
  const roleBadge=isIran?`<span class="badge b-ok" style="gap:4px">🇮🇷 Iran</span>`:`<span class="badge b-info" style="gap:4px">🌐 Node</span>`;
  const trBadge=s.transport==='api'?`<span class="badge b-noise" style="gap:4px;font-size:10.5px">⚡ ${t('badge_agent')}</span>`:`<span class="badge b-ws" style="gap:4px;font-size:10.5px">🔑 ${t('badge_ssh')}</span>`;
  const pxBadge=s.proxy?`<span class="badge b-plain" style="gap:4px;font-size:10.5px">${t('badge_proxied')}</span>`:'';
  const hostLine=s.transport==='api'?h(s.api_url||''):`${h(s.host||'')}:${s.ssh_port||22}`;
  return `<article class="scard" id="srv_${h(s.name)}">
   <div class="top"><span class="dot d-un" id="dot_${h(s.name)}" aria-hidden="true"></span>
    <button class="server-link" type="button" onclick="nav('#/server/${h(s.name)}')">${h(s.name)}</button>${roleBadge}${trBadge}${pxBadge}</div>
   <div class="host mono">${hostLine}</div>
   <div class="bstrip" id="hd_${h(s.name)}"><span class="sub">${t('loading')}</span></div>
   <div class="meta" id="mt_${h(s.name)}"><div class="meta-info"></div><span class="qr"><button class="gh icon-btn" type="button" onclick="loadOv('${h(s.name)}')" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button></span></div>
  </article>`;
 }).join('');
}
function updateCard(n){
 const ov=OVS[n]; if(!ov)return;
 if(typeof updateDashboardKpis==='function')updateDashboardKpis();
 if(DASH_FILTER.status!=='all'&&!$('srv_'+n)){drawCards();const c=$('servers');if(c)c.classList.remove('stagger-in');SERVERS.forEach(s=>{if(OVS[s.name]&&s.name!==n)updateCard(s.name);});return;}
 setDot(n,ovDotCls(n,ov));
 const hd=$('hd_'+n); if(hd)hd.innerHTML=headBadges(n,ov);
 const mt=$('mt_'+n); if(!mt)return;
 let meta='';
 const srv=fnd(n);
 if(ov.reachable===false){
  meta=`<span class="badge b-bad">${h((ov.error||'').split(String.fromCharCode(10))[0].slice(0,50))}</span>`;
 } else if(srv.role==='iran'){
  meta=`<span class="badge b-ok">${(ov.nodes||[]).length} ${t('n_nodes')}</span>`;
  if((ov.game||[]).length)meta+=` <span class="badge b-info">${ov.game.length} ${t('n_game')}</span>`;
  if(ov.domain)meta+=` <span class="mono" style="font-size:11.5px;color:var(--text-muted);">${h(ov.domain)}</span>`;
 } else {
  const svcCount = (ov.services||[]).length + (ov.backhaul_services||[]).length;
  meta=`<span class="badge b-ok">${svcCount} ${t('n_svcs')}</span>`;
  if((ov.upstreams||[]).length)meta+=` <span class="badge b-info">${ov.upstreams.length} ${t('n_ups')}</span>`;
  if(ov.main_server)meta+=` <span class="mono" style="font-size:11.5px;color:var(--text-muted);">→ ${h(ov.main_server)}</span>`;
 }
 if(srv.proxy)meta+=` <span class="badge b-plain">${t('badge_proxied')}</span>`;
 mt.innerHTML=`<div class="meta-info">${meta}</div><span class="qr"><button class="gh icon-btn" type="button" onclick="loadOv('${h(n)}')" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button></span>`;
}

// ---------- safhe: server (hameye amaliat-e ghadimi inja) ----------
function renderServerPage(n){
 if(typeof closeAllMoreMenus==='function')closeAllMoreMenus(null,true);
 const pg=$('page'); if(!pg)return; const s=fnd(n);
 if(!s.name){pg.innerHTML=`<div class="ptitle"><button class="back" type="button" onclick="nav('#/dashboard')">${icon('arrow')}${t('back')}</button><h2>${t('srv_notfound')}</h2></div>`;return;}
 const ov=OVS[n];
 const roleBadge=s.role==='iran'?'<span class="badge b-ok" style="gap:4px">🇮🇷 Iran</span>':'<span class="badge b-info" style="gap:4px">🌐 Node</span>';
 const trBadge=s.transport==='api'?'<span class="badge b-noise" style="gap:4px">⚡ REST API</span>':'<span class="badge b-ws" style="gap:4px">🔑 SSH</span>';
 const pxBadge=s.proxy?`<span class="badge b-plain" style="gap:4px">${t('badge_proxied')}</span>`:'';
 const hostLine=s.transport==='api'?h(s.api_url||''):`${h(s.host||'')}:${s.ssh_port||22}`;
 let head=`<div class="spage-head"><button class="back" type="button" onclick="nav('#/dashboard')">${icon('arrow')}${t('back')}</button>
   <span class="dot ${ovDotCls(n,ov)}" id="dot_${h(n)}"></span>
   <span class="name" style="font-size:18px">${h(n)}</span>${roleBadge}${trBadge}${pxBadge}
   <span class="sub mono">${hostLine}</span><span id="hd_${h(n)}">${ov?headBadges(n,ov):''}</span>
   <div class="btns">
     <button class="gh icon-btn" type="button" onclick="loadOv('${h(n)}')" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button>
     <button class="gh" onclick="showDetails('${h(n)}')">${t('details')}</button>
     <button class="s" onclick="doDeploy('${h(n)}')">${t('update')}</button>
     <button class="gh" onclick="editServer('${h(n)}')">${t('edit_server')}</button>
     <button class="r" onclick="delSrvPage('${h(n)}')">${t('del_server')}</button>
   </div></div>`;
 let body;
 if(!ov){body=`<div class="empty">${t('loading')}</div>`;loadOv(n);}
 else if(ov.reachable===false){body=s.transport==='api'
  ?`<div class="sec"><div class="empty">${t('agent_help')}<br><br>${h(ov.error||'')}</div></div>`
  :`<div class="sec"><div class="empty">${t('ssh_help')}<br><code>ssh-copy-id -i /root/.ssh/id_ed25519.pub root@${h(s.host)}</code><br><br>${h(ov.error||'')}</div></div>`;}
 else{body=(s.role==='iran'?renderIran(n,ov):renderNode(n,ov));}
 // baraye node: dot-haye vaziat az doctor-e Iran miayand — agar overview-e Iran-i nadarim, biar
 if(s.role==='node')SERVERS.filter(x=>x.role==='iran'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
 pg.innerHTML=`<div class="spage">${head}<div id="body_${h(n)}">${body}</div></div>`;
}
async function delSrvPage(n){if(!confirm(t('cf_delsrv')+' ('+n+')'))return;await api('DELETE','api/servers/'+n);SERVERS=[];delete OVS[n];nav('#/dashboard');}
function tbl(cols){return '<table><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr>';}
function esc(s){return h(s);}

function featureOn(ov,key){
 const f=((ov||{}).status||{}).features||{};
 if(f[key]&&typeof f[key].active==='boolean')return f[key].active;
 if(key==='frp') return !!(((ov||{}).status||{}).ports||{}).frp;
 if(key==='gre') return !!(((ov||{}).status||{}).gre||{}).name;
 return !!(((ov||{})[key]||{}).enabled);
}
function toggleAction(on,onHtml,offHtml){return on?offHtml:onHtml;}
function connSummary(ov,role){
 const st=(ov||{}).status||{},m=role==='node'?(st.main||{}):{};
 if(role==='node'&&!m.transport)return '';
 if(role==='node')return `<div class="sub" style="margin-top:7px">${h(t('conn_transport'))}: <b>${h(m.transport)}</b> · ${h(t('conn_dial'))}: <span class="mono">${h(m.dial_endpoint||'?')}</span> · ${h(t('conn_sni'))}: <span class="mono">${h(m.tls_hostname||'-')}</span> · ${h(t('conn_crypto'))}: ${m.encrypted?t('yes'):t('no')} · ${h(t('conn_live'))}: ${h(m.live||'unknown')}</div>`;
 const bh=(((st||{}).features)||{}).backhaul||{};
 return bh.configured?`<div class="sub" style="margin-top:7px">${h(t('conn_transport'))}: Backhaul/${h(bh.mode||'nginx_tls')} · ${h(t('conn_crypto'))}: ${bh.encrypted?t('yes'):t('no')} · ${h(t('conn_live'))}: ${h(bh.active?'active':'inactive')}</div>`:'';
}
let IRAN_TAB = localStorage.getItem('rh_iran_tab') || 'nodes';
function setIranTab(n, tab){
  if(typeof closeAllMoreMenus==='function')closeAllMoreMenus(null,true);
  IRAN_TAB = tab;
  localStorage.setItem('rh_iran_tab', tab);
  const el = $('body_' + n);
  if(el && OVS[n]){
    _tabAnimate = true;
    try { el.innerHTML = renderIran(n, OVS[n]); }
    finally { _tabAnimate = false; }
  }
}

function renderIran(n,ov){
  SERVERS.filter(x=>x.role==='node'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
  let s='<div id="det_'+n+'"></div>';

  const st = ov.status || {};
  const dom = st.domain || ov.domain || '-';
  const hasCert = ((st.cert || {}).exists === 'yes');
  const certTag = hasCert ? `<span class="badge b-ok">🔒 ${t('ssl_valid')}</span>` : `<span class="badge b-bad">${t('ssl_missing')}</span>`;
  const nodeCount = (ov.nodes || []).length;
  const gameCount = (ov.game || []).length;
  const nodesVal = `${nodeCount} ${t('c_name')}` + (gameCount ? ` (+${gameCount} SNI)` : '');

  const activeCarriers = [];
  if(featureOn(ov, 'backhaul')) activeCarriers.push('Backhaul');
  if(featureOn(ov, 'kcp')) activeCarriers.push('KCP');
  if(featureOn(ov, 'noise')) activeCarriers.push('Noise');
  if(featureOn(ov, 'plain')) activeCarriers.push('Plain');
  if(featureOn(ov, 'frp')) activeCarriers.push('FRP');
  if(featureOn(ov, 'gre')) activeCarriers.push('GRE');
  if(featureOn(ov, 'paqet')) activeCarriers.push('Paqet');
  if(!activeCarriers.length) activeCarriers.push('WS/443');

  s+=`<div class="hero-stats">
    <div class="stat-card">
      <div class="stat-lbl">🌐 ${t('stat_domain')}</div>
      <div class="stat-val"><span class="mono">${esc(dom)}</span> ${certTag}</div>
    </div>
    <div class="stat-card">
      <div class="stat-lbl">👥 ${t('stat_nodes')}</div>
      <div class="stat-val"><span class="dot d-ok"></span> ${esc(nodesVal)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-lbl">⚡ ${t('stat_carriers')}</div>
      <div class="stat-val">${activeCarriers.map(c=>`<span class="badge b-ok">${c}</span>`).join(' ')}</div>
    </div>
  </div>`;

  const tabs = [
    { id: 'nodes', label: t('tab_nodes'), count: nodeCount + gameCount },
    { id: 'carriers', label: t('tab_carriers'), count: activeCarriers.length },
    { id: 'network', label: t('tab_network') },
    { id: 'maint', label: t('tab_maint') }
  ];
  s+=`<div class="tab-bar">` + tabs.map(tab => {
    const act = (IRAN_TAB === tab.id) ? 'active' : '';
    const cnt = tab.count != null ? ` <span class="badge b-ws" style="margin-inline-start:4px">${tab.count}</span>` : '';
    return `<button type="button" class="tab-btn ${act}" onclick="setIranTab('${n}','${tab.id}')">${tab.label}${cnt}</button>`;
  }).join('') + `</div>`;

  const tabAnim=typeof _tabAnimate!=='undefined'&&_tabAnimate;
  const navAnim=typeof _navAnimate!=='undefined'&&_navAnimate;
  s+=`<div class="tab-panel${tabAnim?' view-enter':''}">`;
  if(IRAN_TAB === 'nodes'){
    s+=`<div class="sec"><div class="sec-head-row"><h4>${t('nodes_svcs')} <button class="g" onclick="addNode('${n}')">${t('add_node')}</button></h4>
      ${(ov.nodes||[]).length?`<div class="search-box inline-search">${icon('search')}<input type="search" data-tbl-filter="iran_nodes_tbl" placeholder="${h(t('flt_search_svc'))}" aria-label="${h(t('flt_search_svc'))}"></div>`:''}</div>`;
    const nodes=ov.nodes||[];
    if(!nodes.length)s+=`<div class="empty">${t('no_nodes')}</div>`;
    else{ s+=`<div class="table-wrap" tabindex="0" role="region" aria-label="${h(t('nodes_svcs'))}" id="iran_nodes_tbl">`+tbl([t('c_name'),t('c_dport'),t('c_inbound'),t('c_api'),t('c_ops')]);
     const nnodes=(ov.noise||{}).nodes||[]; const hn=(ov.health||{}).nodes||{};
     nodes.forEach(d=>{ const isN=nnodes.indexOf(d.name)>=0;
      const st=hn[d.name]; const hdot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
      const nbadge=` <span class="badge">${h(carrierLabel(iranNodeMode(ov,d.name),ov))}</span>`;
      const csel=iranNodeCarrierSel(n,ov,d.name);
      s+=`<tr><td>${hdot}${esc(d.name)}${nbadge}</td><td class="mono">${esc(d.port)}</td><td class="mono">${esc(d.inbound)}</td><td class="mono">${esc(d.api)}</td>
      <td class="btns nowrap"><button class="gh" type="button" data-act="show_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('show_token')}</button>
      <button class="g" type="button" data-act="wire_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('wire_to_node')}</button>
      <button class="gh" type="button" data-act="edit_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('edit')}</button>
      <button class="gh" type="button" data-act="rename_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('rename')}</button>
      <button class="gh" type="button" data-act="rotate_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('rotate')}</button>
      ${csel}
      ${serviceMenu('iran',n,d.name)}
      <button class="r" type="button" data-act="rm_node" data-srv="${h(n)}" data-name="${h(d.name)}">${t('remove')}</button></td></tr>`;});
     s+='</table></div>';}
    s+='</div>';

    s+=`<div class="sec"><h4>${t('game_svcs')} <button class="g" onclick="gameAdd('${n}')">${t('add_game')}</button> <button class="gh" onclick="gameCert('${n}')">${t('get_cert')}</button></h4>`;
    const g=ov.game||[];
    if(!g.length)s+=`<div class="empty">${t('no_game')}</div>`;
    else{ s+=`<div class="table-wrap" tabindex="0" role="region" aria-label="${h(t('game_svcs'))}">`+tbl([t('c_name'),'SNI',t('c_data'),t('c_node_inb'),t('c_ops')]);
     g.forEach(d=>{s+=`<tr><td>${esc(d.name)}</td><td>${esc(d.sni)}</td><td>${esc(d.data)}</td><td>${esc(d.inbound)}</td>
      <td class="btns"><button class="r" type="button" data-act="game_rm" data-srv="${h(n)}" data-name="${h(d.name)}">${t('remove')}</button></td></tr>`;});
     s+='</table></div>';}
    s+='</div>';
  } else if(IRAN_TAB === 'carriers'){
    const isBh = featureOn(ov, 'backhaul');
    const isKcp = featureOn(ov, 'kcp');
    const isNoise = featureOn(ov, 'noise');
    const isPlain = featureOn(ov, 'plain');
    const isFrp = featureOn(ov, 'frp');
    const isGre = featureOn(ov, 'gre');

    s+=`<div class="sec"><h4>⚡ ${t('carriers_avail')}</h4>
      <div class="sub" style="margin-bottom:8px">${h(t('carriers_avail_hint'))}</div>
      <div class="carrier-grid${(tabAnim||navAnim)?' stagger-in':''}">
        <div class="carrier-card ${isBh?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🚀 Backhaul (SMUX Core)</b>
                <span class="carrier-desc">مالتی‌پلکسر پرسرعت ترافیک با یک استریم TCP روی پورت ۴۴۳</span>
              </div>
              ${isBh ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const bf=((ov.status||{}).features||{}).backhaul||{};const bo=ov.backhaul||{};const bp=bf.port||bo.port||((ov.status||{}).ports||{}).backhaul||3080;const btr=bf.transport||bo.transport||'wsmux';const bm=bf.mode||bo.mode||'nginx_tls';const bind=bm==='direct_ip'?'0.0.0.0':'127.0.0.1';return `<span>پورت: ${bind}:${h(bp)}</span><span>حالت: ${h(btr)} (${h(bm)})</span>`;})()}
              ${bhUsageLine(ov)}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isBh, `<button class="g" onclick="bhOnIran('${n}')">${t('bh_on')}</button>`, `<button class="r" onclick="disableIranCarrier('${n}','backhaul')">${t('bh_off')}</button>`)}
            <button class="gh" onclick="run('${n}','backhaul_show')">${t('show_key')}</button>
            <button class="gh" onclick="run('${n}','backhaul_status')">${t('status')}</button>
            <button class="gh" onclick="run('${n}','backhaul_logs')">${t('logs')}</button>
            <button class="s" onclick="bhNode('${n}','on')">${t('bh_node_on')}</button>
          </div>
        </div>

        <div class="carrier-card ${isKcp?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🛡️ KCP Tunnel (UDP + FEC)</b>
                <span class="carrier-desc">پروتکل ضد اختلال بر پایه UDP همراه با تصحیح خطای بسته‌ها</span>
              </div>
              ${isKcp ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const ko=ov.kcp||{};const kp=ko.port||((ov.status||{}).ports||{}).kcp||443;const kpr=ko.profile||'balanced';return `<span>پورت: UDP :${h(kp)}</span><span>پروفایل: ${h(kpr)}</span>`;})()}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isKcp, `<button class="g" onclick="kcpOnIran('${n}')">${t('kcp_on')}</button>`, `<button class="r" onclick="run('${n}','kcp_off')">${t('kcp_off')}</button>`)}
            <button class="gh" onclick="run('${n}','kcp_show')">${t('show_key')}</button>
          </div>
        </div>

        <div class="carrier-card ${isNoise?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🔒 Noise Protocol</b>
                <span class="carrier-desc">رمزنگاری امن سرتاسر ChaChaPoly بدون نیاز به گواهی دامنه‌ای</span>
              </div>
              ${isNoise ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const nf=((ov.status||{}).features||{}).noise||{};const no=ov.noise||{};const np=nf.port||no.port||((ov.status||{}).ports||{}).noise||2334;const pat=no.pattern||'Noise_NK';return `<span>پورت: TCP :${h(np)}</span><span>الگو: ${h(pat)}</span>`;})()}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isNoise, `<button class="g" onclick="noiseOnIran('${n}')">${t('noise_on')}</button>`, `<button class="r" onclick="disableIranCarrier('${n}','noise')">${t('noise_off')}</button>`)}
            <button class="gh" onclick="run('${n}','noise_show')">${t('show_key')}</button>
            <button class="s" onclick="noiseNode('${n}','on')">${t('noise_node_on')}</button>
          </div>
        </div>

        <div class="carrier-card ${isPlain?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🌐 Plain (بدون TLS)</b>
                <span class="carrier-desc">وب‌سوکت سبک روی پورت مجزا برای تست و سرورهای بدون دامنه</span>
              </div>
              ${isPlain ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const pf=((ov.status||{}).features||{}).plain||{};const po=ov.plain||{};const pp=pf.port||po.port||((ov.status||{}).ports||{}).plain||8880;return `<span>پورت: HTTP :${h(pp)}</span>`;})()}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isPlain, `<button class="g" onclick="plainOnIran('${n}')">${t('plain_on')}</button>`, `<button class="r" onclick="run('${n}','plain_off')">${t('plain_off')}</button>`)}
            <button class="gh" onclick="run('${n}','plain_show')">${t('show_key')}</button>
          </div>
        </div>

        <div class="carrier-card ${isFrp?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🚀 FRP Core (fatedier)</b>
                <span class="carrier-desc">تونل معکوس پایدار چندپروتکله TCP/KCP/QUIC با mux داخلی</span>
              </div>
              ${isFrp ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const ff=((ov.status||{}).features||{}).frp||{};const fp=ff.port||(ov.frp||{}).port||7000;const frpTr=(ff.transport||(ov.frp||{}).transport||'tcp').toLowerCase();const proto=(frpTr === 'quic' || frpTr === 'kcp')?'UDP':'TCP';return `<span>پورت: ${proto} :${h(fp)}</span><span>ترانسپورت: ${h(frpTr.toUpperCase())}</span>`;})()}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isFrp, `<button class="g" onclick="frpOnIran('${n}')">${t('frp_on')}</button>`, `<button class="r" onclick="disableIranCarrier('${n}','frp')">${t('frp_off')}</button>`)}
            <button class="gh" onclick="run('${n}','frp_show')">${t('show_key')}</button>
          </div>
        </div>

        <div class="carrier-card ${isGre?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🌐 تونل لایه ۳ GRE</b>
                <span class="carrier-desc">کپسوله‌سازی لایه ۳ مستقیم در هسته لینوکس با MTU 1476</span>
              </div>
              ${isGre ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              ${(()=>{const gf=((ov.status||{}).features||{}).gre||{};const gs=(ov.status||{}).gre||{};const gn=gf.name||gs.name||'gre1';const gtip=gf.tunnel_ip||gs.tunnel_ip||'10.10.10.1';return `<span>کارت شبکه: ${h(gn)}</span><span>تونل IP: ${h(gtip)}/30</span>`;})()}
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isGre, `<button class="g" onclick="greOnIran('${n}')">${t('gre_on')}</button>`, `<button class="r" onclick="run('${n}','gre_off')">${t('gre_off')}</button>`)}
            <button class="gh" onclick="run('${n}','gre_status')">وضعیت</button>
          </div>
        </div>

        ${(()=>{const isPaqet=featureOn(ov,'paqet');const pf=((ov.status||{}).features||{}).paqet||{};const po=ov.paqet||{};const pqm=pf.mode||po.mode||'fast';const pqb=pf.block||po.block||'aes-128-gcm';const pqr=pf.remote||po.remote||'—';return `<div class="carrier-card ${isPaqet?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>📦 Paqet Direct PCK (خام TCP+KCP)</b>
                <span class="carrier-desc">ارسال بسته‌های خام بدون هندشیک TLS/SSL برای عبور از فیلترینگ DPI سخت‌گیر</span>
              </div>
              ${isPaqet ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              <span>مقصد نود: ${h(pqr)}</span><span>حالت: ${h(pqm)} (${h(pqb)})</span>
            </div>
          </div>
          <div class="carrier-actions">
            ${toggleAction(isPaqet, `<button class="g" onclick="paqetOnIran('${n}')">${t('paqet_on')}</button>`, `<button class="r" onclick="run('${n}','paqet_off')">${t('paqet_off')}</button>`)}
            <button class="gh" onclick="run('${n}','paqet_show')">${t('show_key')}</button>
            <button class="gh" onclick="run('${n}','paqet_status')">${t('status')}</button>
            <button class="s" onclick="paqetNode('${n}')">${t('paqet_node_on')}</button>
          </div>
        </div>`;})()}
      </div>
      ${connSummary(ov,'iran')}
    </div>`;
  } else if(IRAN_TAB === 'network'){
    const p = (ov.status||{}).ports || {};
    const c = (ov.status||{}).cert || {};
    const isDirect = featureOn(ov, 'direct');
    const isFw = featureOn(ov, 'fakeweb') || (((ov.status||{}).services||{}).fakeweb === 'yes');
    s+=`<div class="sec"><h4>${t('domain_tls')} <button class="g" onclick="domainTls('${n}')">${t('manage')}</button> <button class="gh" onclick="scanXrayCover('${n}')">🔍 ${t('xray_scan_btn')}</button></h4>
      <div class="carrier-meta" style="margin:4px 0 0;gap:16px;">
        <span>دامنه: <b class="mono">${esc((ov.status||{}).domain || ov.domain || '-')}</b></span>
        <span>وضعیت گواهی: ${c.exists==='yes' ? `<span class="badge b-ok">🔒 معتبر</span>` : `<span class="badge b-bad">یافت نشد</span>`}</span>
        ${c.expiry ? `<span>انقضا: <span class="mono">${esc(c.expiry)}</span></span>` : ''}
      </div>
    </div>
    <div class="sec"><h4>${t('ports_sec')} <button class="g" onclick="portsModal('${n}')">${t('manage')}</button></h4>
      <div class="carrier-meta" style="margin:4px 0 0;gap:16px;">
        <span>Control: <b class="mono">${esc(p.control||2333)}</b></span>
        <span>Fake Web: <b class="mono">${esc(p.fake||8080)}</b></span>
        <span>Subscription: <b class="mono">${esc(p.sub||2096)}</b></span>
        <span>Internal: <b class="mono">${esc(p.internal||8443)}</b></span>
      </div>
    </div>
    <div class="sec"><h4>${t('ingress_sec')}</h4>
      <div class="sub" style="margin-bottom:12px">${h(t('ingress_hint'))}</div>
      <div class="carrier-grid${(tabAnim||navAnim)?' stagger-in':''}" style="margin-top:0">
        <!-- Direct-IP -->
        <div class="carrier-card ${isDirect?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>📡 ${t('direct_mode')}</b>
                <span class="carrier-desc">مسیریابی بدون TLS با هدر سفارشی (برای CDN و ورودی مستقیم IP)</span>
              </div>
              ${isDirect ? `<span class="badge b-ok">${t('rc_on')}</span>` : `<span class="badge b-bad">${t('rc_off')}</span>`}
            </div>
            <div class="carrier-meta">
              <span>پورت: HTTP :${esc(p.direct||8081)}</span>
              <span>هدر: <b class="mono">${esc((ov.status||{}).direct_header||'X-Cdn-Id')}</b></span>
            </div>
          </div>
          <div class="carrier-actions">
            ${isDirect
              ? `<button class="r" onclick="run('${n}','direct_off')">${t('direct_off')}</button>`
              : `<button class="g" onclick="directOnIran('${n}')">${t('direct_on')}</button>`}
            <button class="gh" onclick="run('${n}','direct_show')">${t('show_key')}</button>
          </div>
        </div>

        <!-- Fake Web -->
        <div class="carrier-card ${isFw?'active':''}">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🌐 ${t('fakeweb')}</b>
                <span class="carrier-desc">سایت فیک داخلی روی پورت ${esc(p.fake||8080)} برای رفع خطای 502 در مسیر /</span>
              </div>
              ${isFw ? `<span class="badge b-ok">${t('fw_status_on')} (پورت: ${esc(p.fake||8080)})</span>` : `<span class="badge b-bad">${t('fw_status_off')}</span>`}
            </div>
            <div class="carrier-meta">
              <span>وضعیت سرویس: <b>${isFw ? 'فعال' : 'متوقف'}</b></span>
              <span>پورت شنود: <b class="mono">127.0.0.1:${esc(p.fake||8080)}</b></span>
            </div>
          </div>
          <div class="carrier-actions">
            ${isFw
              ? `<button class="s" onclick="fakewebStart('${n}')">${t('fw_change')}</button><button class="r" onclick="run('${n}','fakeweb_stop')">${t('fw_stop')}</button>`
              : `<button class="g" onclick="fakewebStart('${n}')">${t('fw_start_clean')}</button>`}
            <button class="gh" onclick="if(confirm(t('cf_fwrm')))run('${n}','fakeweb_rm')">${t('fw_rm')}</button>
          </div>
        </div>

        <!-- Reverse Proxy -->
        <div class="carrier-card">
          <div>
            <div class="carrier-head">
              <div class="carrier-title">
                <b>🔀 ${t('px_sec')}</b>
                <span class="carrier-desc">پروکسی معکوس Nginx (مسیریابی غیرتونلی مستقیم به سرویس‌های وب دیگر)</span>
              </div>
              <span class="badge b-info">Nginx L7</span>
            </div>
            <div class="carrier-meta">
              <span>مسیردهی مستقیم روی همان پورت ۴۴۳</span>
            </div>
          </div>
          <div class="carrier-actions">
            <button class="g" onclick="pxAdd('${n}')">${t('px_add')}</button>
            <button class="gh" onclick="run('${n}','proxy_ls')">${t('px_ls')}</button>
            <button class="r" onclick="pxRm('${n}')">${t('px_rm')}</button>
          </div>
        </div>
      </div>
    </div>`;
  } else if(IRAN_TAB === 'maint'){
    s+=`<div class="sec"><h4>🛠️ ${t('tab_maint')}</h4>
      <div class="btns" style="margin-top:6px">
        <button class="g" onclick="if(confirm(t('cf_reapply')))run('${n}','regen_full')">${t('reapply')}</button>
        <button class="s" onclick="if(confirm(t('cf_restart')))run('${n}','restart')">${t('restart_rathole')}</button>
        <button class="gh" onclick="statusModal('${n}')">${t('status_btn')}</button>
        <button class="gh" onclick="run('${n}','tune')">tune</button>
        <button class="gh" onclick="doLogs('${n}')">${t('logs_btn')}</button>
      </div>
      <div class="sub" style="margin-top:8px">${h(t('reapply_hint'))}</div>
    </div>`;
  }
  s+='</div>';
  return s;
}

// vaziat-e yek service-e node az doctor-e hameye Iran-ha ('ok'/'warn'/null)
function svcStatus(name){
 let st=null;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  if(name in hn){if(hn[name]==='warn')st='warn';else if(st===null)st='ok';}
 });
 return st;
}
function svcDot(name){
 const st=svcStatus(name);
 return st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
}

// ---------- MODE-e daghigh-e har node az didgah-e Iran (manba-e vahed) ----------
// har node dar har lahze YEK mode darad. tartib-e olaviat: game (sni) > backhaul > noise > ws.
// az .transport-e khod-e node (ratholectl ls) mikhanim va baraye CLI-e ghadimi az
// ov.noise.nodes[] / ov.game[] fallback migirim ta hamishe daghigh bashad.
function iranNodeMode(ov,name){
 ov=ov||{};
 const nd=(ov.nodes||[]).find(x=>x&&x.name===name)||{};
 // olaviat-e GHATIE: game(SNI) > backhaul > noise > ws. game yek switch-e L4 rooye 443 ast
 // ke bar hame ghaleb ast, pas AVAL check mishavad (che az ov.game va che az sni-e khod-e node).
 if((ov.game||[]).some(x=>x&&x.name===name)||nd.sni)return 'game';
 if(nd.transport==='frp')return 'frp';
 if(nd.transport==='frp_gre')return 'frp_gre';
 if(nd.transport==='gre')return 'gre';
 if(nd.transport==='paqet')return 'paqet';
 if(nd.transport==='backhaul')return 'backhaul';
 if(nd.transport==='noise'||((ov.noise||{}).nodes||[]).indexOf(name)>=0)return 'noise';
 if(nd.transport==='kcp')return 'kcp';
 if(nd.transport==='plain')return 'plain';
 return 'ws';
}
// ---------- backhaul: 1:1 ast — neshan bede kodam node-ha rooyash hastand ----------
// backhaul YEK server + YEK token-e sarasari + YEK majmoue-ye ports darad. agar DO mashin-e
// kharej ba haman token vasl shavand sar-e channel-e kontrol daava mikonand va HAR DO ghat
// mishavand. neshane-ash inbound-e tekrari beyn-e node-haye backhaul ast.
function bhNodes(ov){
 return (((ov||{}).nodes)||[]).filter(x=>x&&x.transport==='backhaul');
}
function bhDupInbounds(ov){
 const seen={},dup=[];
 bhNodes(ov).forEach(x=>{const k=String(x.inbound||'');if(!k)return;
  if(seen[k]){if(dup.indexOf(k)<0)dup.push(k);}else seen[k]=1;});
 return dup;
}
function bhUsageLine(ov){
 const list=bhNodes(ov); if(!list.length)return '';
 const dup=bhDupInbounds(ov);
 let s=`<div class="sub" style="margin-top:6px">${h(t('bh_users'))}: `
      +list.map(x=>`<span class="badge b-backhaul">${h(x.name)}</span>`).join(' ')+'</div>';
 if(dup.length){
  s+=`<div class="sub" style="margin-top:4px;color:#f87171">⚠ ${h(t('bh_dup_warn').replace('%p',dup.join(', ')))}</div>`;
 }
 return s;
}

// badge-e mode ba class/rang-e hamsan ba baghye-ye UI.
function modeBadge(mode){
 const cls={ws:'b-ws',kcp:'b-kcp',plain:'b-plain',noise:'b-noise',backhaul:'b-backhaul',game:'b-game',frp:'b-frp',gre:'b-gre',frp_gre:'b-frp_gre',paqet:'b-paqet'}[mode]||'b-ws';
 return `<span class="badge ${cls}">${h(t('mode_'+mode)||mode.toUpperCase())}</span>`;
}

function renderNode(n,ov){
 let s='<div id="det_'+n+'"></div>';
 // Hamel-e rathole moshtarak ast; backhaul registry-e joda darad.
 s+=`<div class="sec"><h4>${t('main_tunnel')} ${esc(ov.main_server||'?')} <button class="g" onclick="setMainSrv('${n}')">${t('set_main')}</button></h4>
   <div class="preset-bar">
     <span class="preset-title">${t('preset_title')}:</span>
     <button class="s" onclick="applyNodePreset('${n}','ws')">${t('preset_ws')}</button>
     <button class="s" onclick="applyNodePreset('${n}','kcp')">${t('preset_kcp')}</button>
     <button class="s" onclick="applyNodePreset('${n}','backhaul')">${t('preset_bh')}</button>
   </div>
   <div class="btns"><span class="sub">${t('carrier')}</span>${carrierSelect(n,ov)}
   <button class="gh" type="button" data-lt-node="${h(n)}" onclick="nodeLinkTest(this.dataset.ltNode)">${t('link_test')}</button><button class="s" onclick="run('${n}','restart')">${t('restart_tunnel')}</button></div>
   <div class="sub" style="margin-top:4px">${h(t('carrier_hint'))}</div>${connSummary(ov,'node')}
   <div class="btns" style="margin-top:8px"><span class="sub">${t('watchdog')}</span>
   ${toggleAction(!!(((ov.status||{}).watchdog||{}).enabled),`<button class="g" onclick="wdOn('${n}')">${t('wd_on')}</button>`,`<button class="r" onclick="run('${n}','watchdog_off')">${t('wd_off')}</button>`)}
   <span class="sub" style="margin-inline-start:12px">${t('adaptive_mode')}</span>
   ${toggleAction(!!(((ov.status||{}).adaptive||{}).enabled),`<button class="g" onclick="adaptiveOnNode('${n}')">${t('adaptive_on')}</button>`,`<button class="r" onclick="run('${n}','adaptive_off')">${t('adaptive_off')}</button>`)}
   </div></div>`;

 const curCarrier=nodeCarrier(ov);
 const sv=(ov.services||[]).map(d=>({name:d.name,inbound:d.inbound,lane:curCarrier}));
 const bsv=(ov.backhaul_services||[]).map(d=>({name:d.name,inbound:d.inbound,lane:'backhaul'}));
 const allSv=[...sv,...bsv];
 s+=`<div class="sec"><div class="sec-head-row"><h4>${t('unified_services')} <button class="g" onclick="addUnifiedSvc('${n}')">${t('add_svc')}</button></h4>
   ${allSv.length?`<div class="search-box inline-search">${icon('search')}<input type="search" data-tbl-filter="node_svcs_tbl" placeholder="${h(t('flt_search_svc'))}" aria-label="${h(t('flt_search_svc'))}"></div>`:''}</div>`;
 if(!allSv.length)s+=`<div class="empty">${t('no_svc')}</div>`;
 else{
  s+=`<div class="table-wrap" tabindex="0" role="region" aria-label="${h(t('unified_services'))}" id="node_svcs_tbl">`+tbl([t('c_svc'),t('l_lane'),t('c_inbound'),t('c_ops')]);
  allSv.forEach(d=>{
   const isMux=d.lane==='backhaul';
   const cClass=['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre','paqet'].includes(d.lane)?d.lane:'ws';
   const cLabel=carrierLabel(d.lane,ov);
   const laneBadge=`<span class="badge b-${cClass}" style="font-size:11px;padding:2px 8px;border-radius:4px;">${h(cLabel)}</span>`;
   const dot=svcDot(d.name);
   const rmAct=isMux?'rm_bh_svc':'rm_svc';
   s+=`<tr><td>${dot}${esc(d.name)}</td><td>${laneBadge}</td><td class="mono">${esc(d.inbound)}</td>
    <td class="btns nowrap">${serviceMenu('node',n,d.name)}<button class="r" type="button" data-act="${rmAct}" data-srv="${h(n)}" data-name="${h(d.name)}">${t('remove')}</button></td></tr>`;
  });
  s+='</table></div>';
 }
 s+='</div>';

 const pq=ov.paqet||{};const xr=ov.xray||{};
 s+=`<div class="sec"><h4>📦 ${t('xray_sec')}</h4>
   <div class="btns" style="align-items:center;flex-wrap:wrap">
    <span class="sub">Paqet Server:</span>
    ${pq.enabled?`<span class="badge b-ok">${h(pq.mode||'fast')} :${h(pq.port||'9999')}</span>`:`<span class="badge b-bad">${t('rc_off')}</span>`}
    <button class="g" onclick="paqetOnNode('${h(n)}')">${t('paqet_on')}</button>
    <button class="gh" onclick="run('${h(n)}','paqet_show')">${t('show_key')}</button>
    ${pq.enabled?`<button class="r" onclick="run('${h(n)}','paqet_off')">${t('paqet_off')}</button>`:''}
   </div>
   <div class="btns" style="align-items:center;flex-wrap:wrap;margin-top:8px">
    <span class="sub">Managed Xray:</span>
    ${xr.configured?`<span class="badge ${xr.active?'b-ok':'b-bad'}">${h((xr.mode||'reality').toUpperCase())} :${h(xr.port||'8443')}</span>`:`<span class="badge b-bad">${t('rc_off')}</span>`}
    <button class="g" onclick="setupXrayNode('${h(n)}')">${t('xray_setup_btn')}</button>
    <button class="gh" onclick="showXrayUri('${h(n)}')">${t('xray_uri_btn')}</button>
    <button class="gh" onclick="scanXrayCover('${h(n)}')">🔍 ${t('xray_scan_btn')}</button>
    ${xr.configured?`<button class="r" onclick="run('${h(n)}','xray_off')">${t('xray_off_btn')}</button>`:''}
   </div>
 </div>`;

 s+=`<details class="diag-sec"><summary>🛠️ ${t('diag_tools')}</summary><div class="diag-content">
   <div class="btns">
    <button class="gh" onclick="run('${n}','logs')">${t('logs')}</button>
    <button class="gh" onclick="run('${n}','backhaul_status')">backhaul ${t('status')}</button>
    <button class="gh" onclick="run('${n}','backhaul_logs')">${t('bh_logs')}</button>
    <button class="gh" onclick="run('${n}','watchdog_status')">${t('wd_status')}</button>
    <button class="gh" onclick="run('${n}','adaptive_status')">${t('adaptive_status')}</button>
    <button class="gh" onclick="run('${n}','adaptive_test')">${t('adaptive_test')}</button>
    <button class="gh" onclick="openEndpointsModal('${h(n)}')">${h(t('ep_title'))}</button>
    <button class="gh" onclick="run('${n}','migrate')">${t('migrate')}</button>
   </div>
 </div></details>`;
 s+=`<div class="sec"><h4>${t('upstreams')} <button class="g" onclick="upAdd('${n}')">${t('add_up')}</button></h4>
   <div class="sub" style="margin-bottom:6px">${h(t('upcarrier_hint'))}</div>`;
 const ups=ov.upstreams||[];
 if(!ups.length)s+=`<div class="empty">${t('no_up')}</div>`;
 ups.forEach(u=>{
  // badge az hamon manba-e vahed-e mode (mesl-e tunnel-e asli) — daghigh va hamrang.
  const kb=modeBadge(upCarrier(u));
  s+=`<div class="up"><div class="btns" style="align-items:center">
   <b>${esc(u.id)}</b> ${kb} <span class="sub">→ ${esc(u.server)}</span><span style="flex:1"></span>
   <span class="sub">${t('carrier')}</span>${upCarrierSelect(n,u)}
   <button class="s" type="button" data-act="up_restart" data-srv="${h(n)}" data-id="${h(u.id)}">restart</button>
   <button class="gh" type="button" data-act="up_status" data-srv="${h(n)}" data-id="${h(u.id)}">${t('status')}</button>
   <button class="gh" type="button" data-act="up_logs" data-srv="${h(n)}" data-id="${h(u.id)}">${t('logs')}</button>
   <button class="g" type="button" data-act="up_add_svc" data-srv="${h(n)}" data-id="${h(u.id)}">${t('add_svc')}</button>
   <button class="r" type="button" data-act="up_rm" data-srv="${h(n)}" data-id="${h(u.id)}">${t('del_up')}</button></div>`;
  if((u.services||[]).length){s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);u.services.forEach(x=>{s+=`<tr><td>${svcDot(x.name)}${esc(x.name)}</td><td>${esc(x.inbound)}</td>
   <td class="btns"><button class="r" type="button" data-act="up_rm_svc" data-srv="${h(n)}" data-id="${h(u.id)}" data-name="${h(x.name)}">${t('remove')}</button></td></tr>`;});s+='</table>';}
  s+='</div>';
 });
 s+='</div>';
 return s;
}

// ---------- safhe: routing (graph-e topology, SVG dasti bedoon lib) ----------
let _gTimer=null,_gDragging=false;
let GVIEW=localStorage.getItem('rh_gview')||'graph';
if(!['graph','table','console'].includes(GVIEW))GVIEW='graph';     // namaye routing: graph|table
function scheduleGraph(){clearTimeout(_gTimer);_gTimer=setTimeout(()=>{if((ROUTE.page==='routing')&&!_gDragging){if(GVIEW==='console')drawConsole();else drawGraph();}},150);}
function setGView(v){GVIEW=['graph','table','console'].includes(v)?v:'graph';localStorage.setItem('rh_gview',v);renderRouting();}
// tartib-e dasti-e box-ha (drag): dar localStorage mimanad
function gOrder(col){try{return JSON.parse(localStorage.getItem('rh_gorder_'+col)||'[]');}catch(e){return[];}}
function gResetOrder(){localStorage.removeItem('rh_gorder_iran');localStorage.removeItem('rh_gorder_node');drawGraph();toast(t('saved'));}
function gApplyOrder(names,col){ // sort-e stable: avval tartib-e save-shode, baghye ba tartib-e ghabli
 const ord=gOrder(col),idx={};ord.forEach((n,i)=>idx[n]=i);
 return names.map((n,i)=>({n,i})).sort((a,b)=>{
  const ia=(a.n in idx)?idx[a.n]:1e9+a.i, ib=(b.n in idx)?idx[b.n]:1e9+b.i; return ia-ib;
 }).map(x=>x.n);
}
function renderRouting(){
 const pg=$('page'); if(!pg)return;
 const isC=GVIEW==='console';
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_routing')}</h2><span style="flex:1"></span>
   <div class="vswitch">
   <button class="${GVIEW==='console'?'on':''}" onclick="setGView('console')">⚡ ${t('view_console')}</button>
   <button class="${GVIEW==='graph'?'on':''}" onclick="setGView('graph')">◈ ${t('view_graph')}</button>
   <button class="${GVIEW==='table'?'on':''}" onclick="setGView('table')">☰ ${t('view_table')}</button></div>
   ${GVIEW==='graph'?`<button class="gh" onclick="gResetOrder()">${t('g_reset')}</button>`:''}
   <button class="gh" onclick="pollByPage()">${t('refresh')}</button></div>
  ${(GVIEW==='graph')?`<div class="legend"><b style="color:var(--text)">${t('g_legend')}:</b>
   <span class="li"><span class="lw lw-ws"></span> ws/443</span>
   <span class="li"><span class="lw lw-kcp"></span> kcp</span>
   <span class="li"><span class="lw lw-backhaul"></span> backhaul</span>
   <span class="li"><span class="lw lw-noise"></span> noise</span>
   <span class="li"><span class="lw lw-plain"></span> plain</span>
   <span class="li"><span class="lw lw-frp"></span> frp</span>
   <span class="li"><span class="lw lw-gre"></span> gre</span>
   <span class="li"><span class="lw lw-frp_gre"></span> frp+gre</span>
   <span class="li"><span class="lw lw-bad"></span> ${t('e_bad')}</span></div>`:''}
  ${isC?`<div class="rc" id="rcwrap"></div>`:`<div class="gwrap" id="gwrap"></div>
  <div class="sub" style="margin-top:8px">${GVIEW==='graph'?(t('g_hint')+' '+t('g_drag')):t('g_hint')}</div>`}`;
 if(isC)drawConsole();  else drawGraph();
 SERVERS.forEach(s=>{if(!OVS[s.name])loadOv(s.name);});
}
// ---------- namaye console: vorodi (ingress) → router → khorooji (node) ----------
// ravesh-haye vorood-e karbar (ingress) mostaghel az transport-e reverse-tunnel-e node.
function ingressLanes(ov){
 const p=ov.plain||{},d=ov.direct||{},g=(ov.game||[]);
 return [
  {key:'tls',cls:'lane-tls',on:true,edit:null,title:t('ing_tls_t'),patt:t('ing_tls_p'),desc:t('ing_tls_d'),port:'443'},
  {key:'direct',cls:'lane-direct',on:!!d.enabled,editFn:'directOnIran',offAct:'direct_off',
   title:t('ing_direct_t'),patt:t('ing_direct_p'),desc:t('ing_direct_d'),port:d.port,header:d.header||'X-Cdn-Id'},
  {key:'plain',cls:'lane-plain',on:!!p.enabled,editFn:'plainOnIran',offAct:'plain_off',
   title:t('ing_plain_t'),patt:t('ing_plain_p'),desc:t('ing_plain_d'),port:p.port},
  {key:'sni',cls:'lane-sni',on:g.length>0,edit:null,title:t('ing_sni_t'),patt:'',desc:t('ing_sni_d'),count:g.length}
 ];
}
function laneHtml(n,ln){
 const st=ln.on?`<span class="badge b-ok">${t('rc_on')}</span>`:`<span class="badge b-bad">${t('rc_off')}</span>`;
 let act='';
 if(ln.editFn){
  act=`<button class="gh" onclick="${ln.editFn}('${h(n)}')">${ln.on?t('rc_edit'):t('rc_enable')}</button>`;
  if(ln.on&&ln.offAct)act+=`<button class="r" onclick="run('${h(n)}','${ln.offAct}')">${t('rc_disable')}</button>`;
 }
 const meta=(ln.port?` <span class="lp">:${h(ln.port)}</span>`:'')+(ln.header?` <span class="lp">${h(ln.header)}</span>`:'')
   +(ln.count!=null&&ln.key==='sni'?` <span class="lp">${ln.count} SNI</span>`:'');
 return `<div class="lane ${ln.cls} ${ln.on?'on':'off'}">
   <div class="lh"><span class="ldot"></span><span class="lt">${h(ln.title)}</span>${meta}${st}
    <span class="lact">${act}</span></div>
   ${ln.patt?`<div class="lh" style="margin-top:5px"><span class="lp">${h(ln.patt)}</span></div>`:''}
   <div class="ld">${h(ln.desc)}</div></div>`;
}
// recipe-ha: baraye har node, chegoone karbar (Xray/V2Ray) be an vasl mishavad — bar asas-e ingress-e roshan.
function iranDomain(iran,ov){
 const nn=(ov.nodes||[]);
 for(const d of nn){const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');if(m)return m[1].replace(/:\d+$/,'');}
 return (fnd(iran).host)||'<domain>';
}
function nodeRecipes(iran,ov,node){
 const host=(fnd(iran).host)||'<IRAN_IP>',dom=iranDomain(iran,ov);
 const p=ov.plain||{},d=ov.direct||{};
 const out=[];
 out.push({tag:'ws/443',cls:'b-ws',lines:[[t('rc_addr'),dom],[t('rc_port'),'443'],[t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_yes')]]});
 if(d.enabled){out.push({tag:'direct',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),d.port||'8081'],
   [t('rc_wshost'),'myket.ir  ('+t('rc_hosthint')+')'],[t('rc_header'),(d.header||'X-Cdn-Id')+': '+node.name],[t('rc_tls'),t('rc_no')]]});}
 if(p.enabled){out.push({tag:'plain',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),p.port||'8880'],
   [t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_no')]]});}
 return out;
}
function recipeCopyText(node,r){return node+' · '+r.tag+'\\n'+r.lines.map(l=>l[0]+': '+l[1]).join('\\n');}
function drawConsole(){
 const w=$('rcwrap'); if(!w)return;
 const irans=SERVERS.filter(s=>s.role==='iran');
 if(!irans.length){w.innerHTML=`<div class="rc-empty">${t('rc_pick_iran')}</div>`;return;}
 let x='';
 irans.forEach(s=>{
  const ov=OVS[s.name];
  x+=`<div class="rcard"><div class="rc-head">
    <span class="dot ${ov?ovDotCls(s.name,ov):'d-un'}"></span>
    <span class="nm">${h(s.name)}</span><span class="hst">${h(s.host)}</span>
    <span style="flex:1"></span><span class="sub" style="font-size:11px">${t('rc_legend')}</span>
    <button class="gh" onclick="nav('#/server/${h(s.name)}')">${t('details')}</button></div>`;
  if(!ov){x+=`<div class="rc-empty" style="padding:14px">${t('loading')}</div></div>`;return;}
  if(ov.reachable===false){x+=`<div class="rc-empty" style="padding:14px"><span class="badge b-bad">${t(s.transport==='api'?'rc_agent_unreach':'rc_unreach')}</span></div></div>`;return;}
  const lanes=ingressLanes(ov),nodes=ov.nodes||[];
  x+=`<div class="rc-body">
    <div class="rc-col"><h5>${t('rc_ingress')} <span class="cnt">${lanes.filter(l=>l.on).length}/${lanes.length}</span></h5>
      <p class="rc-sub">${t('rc_ingress_sub')}</p>${lanes.map(l=>laneHtml(s.name,l)).join('')}</div>
    <div class="rc-col"><h5>${t('rc_outputs')} <span class="cnt">${nodes.length}</span></h5>
      <p class="rc-sub">${t('rc_outputs_sub')}</p>`;
  if(!nodes.length)x+=`<div class="rc-empty">${t('rc_no_nodes')}</div>`;
  else{
   const nn=(ov.noise||{}).nodes||[],hn=(ov.health||{}).nodes||{};
   nodes.forEach(d=>{
    const tr=d.transport||(nn.indexOf(d.name)>=0?'noise':((ov.kcp||{}).enabled?'kcp':'ws'));
    const trCls={ws:'b-ws',kcp:'b-kcp',noise:'b-noise',plain:'b-plain',backhaul:'b-backhaul',frp:'b-frp',gre:'b-gre',frp_gre:'b-frp_gre',paqet:'b-paqet'};
    const trb=trCls[tr]||'b-ws';
    const st=hn[d.name],dot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}"></span>`:'<span class="dot d-un"></span>';
    const recs=nodeRecipes(s.name,ov,d);
    x+=`<div class="onode ${st==='warn'?'off':''}"><div class="oh">${dot}<span class="onm">${h(d.name)}</span>
      <span class="sub" style="font-size:11px">${t('rc_transport')}:</span><span class="badge ${trb}">${tr}</span>
      <span class="otr sub" style="font-size:11px">→ :${h(d.port)}</span></div>`;
    recs.forEach((r,i)=>{
     const rid='rec_'+h(s.name)+'_'+h(d.name)+'_'+i;
     x+=`<div class="recipe"><div class="rl"><span class="rtag badge ${r.cls}">${t('rc_via')} ${h(r.tag)}</span>
       <button class="cpy" onclick="copyRecipe('${rid}')">⧉ ${t('rc_copy')}</button></div>
       <div id="${rid}" data-cp="${h(recipeCopyText(d.name,r))}">`;
     r.lines.forEach(l=>{x+=`<div class="rl"><span class="k">${h(l[0])}</span><span class="v">${h(l[1])}</span></div>`;});
     x+=`</div></div>`;
    });
    x+=`</div>`;
   });
  }
  x+=`</div></div></div>`;
 });
 w.innerHTML=x;
}
function copyRecipe(id){const el=$(id);if(!el)return;const txt=(el.getAttribute('data-cp')||'').replace(/\\n/g,'\n');
 navigator.clipboard&&navigator.clipboard.writeText(txt);toast(t('rc_copied'));}


// Har do safhe az hamin control-haye service estefade mikonand.
function carrierLabel(carrier,ov){
 ov=ov||{};
 const features=((ov.status||{}).features)||{};
 if(carrier==='frp'||carrier==='frp_gre'){
  const tr=(features.frp||{}).transport||(ov.frp||{}).transport;
  return (carrier==='frp_gre'?'FRP + GRE':'FRP')+' / '+(tr?tr.toUpperCase():'?');
 }
 if(carrier==='backhaul'){
  const tr=(features.backhaul||{}).transport||(ov.backhaul||{}).transport;
  return 'Backhaul / '+(tr?tr.toUpperCase():'?');
 }
 if(carrier==='kcp')return 'KCP / UDP'+((ov.kcp||{}).profile?' · '+ov.kcp.profile:'');
 if(carrier==='paqet')return 'Paqet / PCK'+(((ov.status||{}).features||{}).paqet?.mode||(ov.paqet||{}).mode?' · '+(((ov.status||{}).features||{}).paqet?.mode||(ov.paqet||{}).mode):'');
 return ({noise:'Noise / TCP',ws:'WebSocket / TLS',plain:'WebSocket / TCP',gre:'GRE / WebSocket',game:'SNI / TLS',paqet:'Paqet / Direct PCK'})[carrier]||carrier;
}

function serviceButtons(side,server,name){
 const call=side==='iran'?'serviceControl':'nodeServiceAction';
 const btn=(action,label,cls='gh')=>`<button class="${cls}" type="button" data-svc-call="${call}" data-server="${h(server)}" data-name="${h(name)}" data-action="${action}">${label}</button>`;
 return btn('configure',t('service_config'),'s')+btn('health',t('service_health'))+btn('copy',t('service_copy'))+btn('manage',t('service_peer'))+btn('remove',t('service_remove_pair'),'r');
}

// hamn mojoodi-ye 5 akshan-e service dar yek menu-ye compact ('⋯') ta radif-e jadval
// yek-khati bemanad (chideman-e v2.0.1) va hamzaman hame-ye emkanat-e jadid ham basand.
function serviceMenu(side,server,name){
 const call=side==='iran'?'serviceControl':'nodeServiceAction';
 const item=(action,label,cls='')=>`<button class="mi ${cls}" type="button" data-svc-call="${call}" data-server="${h(server)}" data-name="${h(name)}" data-action="${action}">${label}</button>`;
 return `<details class="more"><summary class="gh" title="${t('service_more')}" aria-label="${t('service_more')}">⋯</summary>
  <div class="more-menu">${item('configure',t('service_config'))}${item('health',t('service_health'))}${item('copy',t('service_copy'))}${item('manage',t('service_peer'))}${item('remove',t('service_remove_pair'),'mi-r')}</div></details>`;
}

function serviceControl(iran,name,action,next,peerName){
 if(['configure','copy'].includes(action)&&iranNodeMode(OVS[iran],name)==='game'){toast(t('service_game_hint'));return;}
 if(action==='configure')return quickCarrierModal(iran,name,next||iranNodeMode(OVS[iran],name),peerName);
 if(action==='health')return serviceHealth(iran,name,peerName);
 if(action==='copy')return copyServiceConfig(iran,name);
 if(action==='remove')return removeServicePair(iran,name,peerName);
 const peer=findNodeServer(name,peerName);
 if(peer)nav('#/server/'+peer.name);else toast(t('no_node_dst'));
}

function nodeServiceAction(server,name,action,next){
 const matches=SERVERS.filter(s=>s.role==='iran'&&((OVS[s.name]||{}).nodes||[]).some(x=>x.name===name));
 const apply=iran=>action==='manage'?nav('#/server/'+iran):serviceControl(iran,name,action,next,server);
 if(matches.length===1)return apply(matches[0].name);
 if(!matches.length){toast(t('service_iran_missing'));return;}
 formModal(t('l_iran_srv'),[{id:'iran',label:t('l_iran_srv'),type:'select',val:matches[0].name,opts:matches.map(s=>({v:s.name,t:s.name}))}],v=>{closeModal();apply(v.iran);});
}

let _LT_CB={retest:null,doc:null};

function _ltVerdictBadge(verdict){
 if(verdict==='healthy'||verdict==='open_no_http')return `<span class="badge b-ok">${h(t('lt_healthy'))}</span>`;
 if(verdict==='degraded')return `<span class="badge b-warn">${h(t('lt_degraded'))}</span>`;
 return `<span class="badge b-bad">${h(t('lt_failed'))}</span>`;
}

function _ltSideCard(title,side){
 if(!side){
  return `<div class="lt-card"><h4><span>${h(title)}</span><span class="badge">-</span></h4><div class="sub">${h(t('lt_no_peer'))}</div></div>`;
 }
 const r=side.rtt_ms||{};
 const avgS=(r.avg!=null)?(r.avg+' ms'):'-';
 const jitS=(side.jitter_ms!=null)?(side.jitter_ms+' ms'):'-';
 const lossS=(side.loss_pct!=null)?(side.loss_pct+'%'):'-';
 const rangeS=(r.min!=null&&r.max!=null)?`min ${r.min} / p95 ${r.p95!=null?r.p95:r.max} / max ${r.max} ms`:'';
 const backs=(side.backends||[]).map(b=>{
  const cls=b.up?'b-ok':'b-bad';
  const st=b.up?'UP':'DOWN';
  return `<span class="badge ${cls} mono">${h(b.name)}:${h(b.port)} ${st}</span>`;
 }).join('');
 const gre=side.gre?`<div class="sub">${h(t('lt_gre_underlay'))}: <span class="badge ${side.gre.up?'b-ok':'b-bad'}">${h(side.gre.iface)} → ${h(side.gre.peer_ip)} (${side.gre.up?'UP':'DOWN'}${(side.gre.rtt_ms&&side.gre.rtt_ms.avg!=null)?', '+side.gre.rtt_ms.avg+' ms':''})</span></div>`:'';
 return `<div class="lt-card">
  <h4><span>${h(title)}</span>${_ltVerdictBadge(side.verdict)}</h4>
  <div class="lt-metrics">
   <div class="lt-metric"><span class="k">${h(t('lt_rtt'))}</span><span class="v">${h(avgS)}</span></div>
   <div class="lt-metric"><span class="k">${h(t('lt_jitter'))}</span><span class="v">${h(jitS)}</span></div>
   <div class="lt-metric"><span class="k">${h(t('lt_loss'))}</span><span class="v">${h(lossS)}</span></div>
  </div>
  ${rangeS?`<div class="sub mono">${h(rangeS)}</div>`:''}
  ${side.endpoint||side.port?`<div class="sub mono">${h(side.probe_mode||'')} · ${h(side.endpoint||('127.0.0.1:'+side.port))}${side.http_status?' · HTTP '+h(side.http_status):''}${side.tls_version?' · '+h(side.tls_version):''}</div>`:''}
  ${side.detail?`<div class="sub">${h(side.detail)}</div>`:''}
  ${gre}
  ${backs?`<div><div class="sub" style="margin-bottom:4px">${h(t('lt_backends'))}:</div><div class="lt-backends">${backs}</div></div>`:''}
 </div>`;
}

function renderLinkTestModal(title,data,retestFn,doctorFn){
 _LT_CB={retest:retestFn||null,doc:doctorFn||null};
 const body=`<h3>${h(title)}</h3>
  <div class="lt-summary">
   <div class="lt-summary-top">${_ltVerdictBadge(data.verdict)}<span class="mono" style="font-size:12px">${h(data.diagnosis_code||'')}</span></div>
   <div style="font-size:13px">${h(data.diagnosis||'')}</div>
  </div>
  <div class="lt-grid">
   ${_ltSideCard(t('lt_iran_to_node'),data.iran_to_node)}
   ${_ltSideCard(t('lt_node_to_iran'),data.node_to_iran)}
  </div>
  <div class="modal-actions">
   <button class="gh" type="button" onclick="_LT_CB.retest&&_LT_CB.retest()">${h(t('lt_retest'))}</button>
   <button class="gh" type="button" onclick="_LT_CB.doc&&_LT_CB.doc()">${h(t('lt_full_doctor'))}</button>
   <button class="s" type="button" onclick="closeModal()">${h(t('close'))}</button>
  </div>`;
 modal(body);
}

async function runServerDoctor(srv,label){
 toast(t('service_testing')+' '+label);
 try{
  const {status,j}=await api('POST','api/servers/'+srv+'/action',{action:'doctor',args:{}});
  if(status<200||status>=300||!j)throw new Error((j&&j.error)||'HTTP '+status);
  outModal(t('service_health')+' · '+label,((j.out||'')+'\n'+(j.err||'')).trim()||('rc='+j.rc));
  await loadOv(srv);
 }catch(e){outModal(t('service_health'),e.message);}
}

async function serviceHealth(iran,name,peerName){
 toast(t('lt_running')+' '+name);
 try{
  const {status,j}=await api('POST','api/servers/'+iran+'/link-test',{node:name,peer:peerName||'',count:5});
  if(status===404||(j&&j.unsupported)){
   return await runServerDoctor(iran,name);
  }
  if(status<200||status>=300||!j)throw new Error((j&&j.error)||'HTTP '+status);
  renderLinkTestModal(t('service_health')+' · '+name,j,
   ()=>serviceHealth(iran,name,peerName),
   ()=>runServerDoctor(iran,name));
  await loadOv(iran);
 }catch(e){outModal(t('service_health'),e.message);}
}

async function nodeLinkTest(n){
 toast(t('lt_running')+' '+n);
 try{
  const {status,j}=await api('POST','api/servers/'+n+'/link-test',{count:5});
  if(status===404||(j&&j.unsupported)){
   return await runServerDoctor(n,n);
  }
  if(status<200||status>=300||!j)throw new Error((j&&j.error)||'HTTP '+status);
  renderLinkTestModal(t('link_test')+' · '+n,j,
   ()=>nodeLinkTest(n),
   ()=>runServerDoctor(n,n));
 }catch(e){outModal(t('link_test'),e.message);}
}

function closeDriftPanel(){
 const p=$('driftpanel');
 if(p)p.innerHTML='';
}

function renderDriftPanel(data){
 const sum=(data&&data.summary)||{};
 const items=(data&&data.items)||[];
 const clean=Boolean(sum.clean||(items.length===0));
 const headBadge=clean
  ?`<span class="badge b-ok">${h(t('drift_clean'))}</span>`
  :`<span class="badge b-warn">${h(sum.total||items.length)} ${h(t('drift_issues'))}</span>`;
 const rows=items.map(it=>{
  const sev=it.severity==='error'?'error':(it.severity==='warning'?'warning':'info');
  const sCls=sev==='error'?'b-bad':(sev==='warning'?'b-warn':'b-info');
  const diff=(it.expected||it.actual)
   ?`<div class="drift-item-diff">${it.expected?`<span>${h(t('drift_expected'))}: <code class="mono">${h(it.expected)}</code></span>`:''}${it.actual?`<span>${h(t('drift_actual'))}: <code class="mono">${h(it.actual)}</code></span>`:''}</div>`
   :'';
  const openBtn=it.server?`<button class="gh" type="button" data-drift-srv="${h(it.server)}" onclick="nav('#/server/'+this.dataset.driftSrv)">${h(it.server)}</button>`:'';
  const peerBadge=it.peer?`<span class="badge">${h(it.peer)}</span>`:'';
  const svcBadge=it.service?`<span class="badge b-ws mono">${h(it.service)}</span>`:'';
  return `<div class="drift-item drift-sev-${sev}">
   <div class="drift-item-top"><span class="badge ${sCls}">${h(sev.toUpperCase())}</span><span class="badge mono">${h(it.kind||'')}</span>${openBtn}${peerBadge}${svcBadge}</div>
   <div class="drift-item-msg">${h(it.message||'')}</div>
   ${diff}
  </div>`;
 }).join('');
 const html=`<div class="card drift-panel"><div class="cbody">
  <div class="drift-head">
   <div class="drift-head-meta"><strong>${h(t('drift_title'))}</strong>${headBadge}${data&&data.hub_version?`<span class="sub mono">Hub ${h(data.hub_version)}</span>`:''}</div>
   <button class="gh" type="button" onclick="closeDriftPanel()">${h(t('close'))}</button>
  </div>
  <div class="drift-note">${h(t('drift_readonly_note'))}</div>
  ${rows?`<div class="drift-list">${rows}</div>`:''}
 </div></div>`;
 const p=$('driftpanel');
 if(p)p.innerHTML=html;
 return html;
}

async function checkFleetDrift(){
 const p=$('driftpanel'), btn=$('driftbtn');
 if(btn)btn.disabled=true;
 if(p)p.innerHTML=`<div class="card drift-panel"><div class="cbody">${h(t('drift_checking'))}</div></div>`;
 try{
  const {status,j}=await api('GET','api/fleet/drift');
  if(status<200||status>=300||!j)throw new Error((j&&j.error)||'HTTP '+status);
  renderDriftPanel(j);
 }catch(e){
  if(p)p.innerHTML=`<div class="card drift-panel"><div class="cbody"><span class="badge b-bad">${h(e.message)}</span></div></div>`;
 }finally{
  if(btn)btn.disabled=false;
 }
}

async function copyServiceConfig(iran,name){
 try{
  const main=await serviceRequest('GET','api/servers/'+iran+'/mainconnect');
  const reported=main.domain||main.tls_hostname||'';
  const host=reported&&!/^(127\.|localhost$|\[?::1\]?$)/i.test(reported)?reported:serverPublicIp(fnd(iran),OVS[iran])||'';
  formModal(t('service_copy'),[
   {id:'uuid',label:t('service_uuid'),req:1},
   {id:'host',label:t('service_public_host'),val:host,req:1},
   {id:'port',label:t('c_port'),val:'443',req:1},
   {id:'sni',label:'TLS SNI',val:main.tls_hostname||main.domain||''},
   {id:'path',label:'WebSocket path',val:'/'+name,req:1}
  ],async v=>{
   if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v.uuid)||!/^\d+$/.test(v.port)||+v.port<1||+v.port>65535||!v.path.startsWith('/')||/[\s\/?#@]/.test(v.host)||/^(127\.|localhost$|\[?::1\]?$)/i.test(v.host)){
    toast(t('service_config_invalid'));return;
   }
   const query=new URLSearchParams({type:'ws',security:'tls',path:v.path});
   if(v.sni)query.set('sni',v.sni);
   const address=v.host.includes(':')&&!v.host.startsWith('[')?'['+v.host+']':v.host;
   const link='vless://'+v.uuid+'@'+address+':'+v.port+'?'+query.toString()+'#'+encodeURIComponent(name);
   closeModal();
   try{await navigator.clipboard.writeText(link);toast(t('rc_copied'));}catch(e){outModal(t('service_copy'),link);}
  });
 }catch(e){outModal(t('service_copy'),e.message);}
}

async function removeServicePair(iran,name,peerName){
 const peer=findNodeServer(name,peerName);
 if(!peer){toast(t('no_node_dst'));return;}
 if(!confirm(t('service_remove_confirm').replace('%s',name)))return;
 try{
  const ov=await serviceRequest('GET','api/servers/'+peer.name+'/overview');
  if(ov.reachable===false||!Array.isArray(ov.services)||!Array.isArray(ov.backhaul_services))throw new Error(t('service_peer_unavailable'));
  await serviceAction(iran,'rm_node',{name});
  if((ov.services||[]).some(x=>x.name===name))await serviceAction(peer.name,'rm_svc',{name});
  if((ov.backhaul_services||[]).some(x=>x.name===name))await serviceAction(peer.name,'rm_bh_svc',{name});
  toast(t('done'));
 }catch(e){outModal(t('service_remove_pair'),e.message);}
 await Promise.allSettled([loadOv(iran),loadOv(peer.name)]);
}

async function serviceRequest(method, url, body) {
  const {status, j} = await api(method, url, body);
  if (status < 200 || status >= 300 || !j || j.ok === false || j.error ||
      (body && j.rc !== 0)) {
    throw new Error((j && (j.error || j.err || j.out)) || ('HTTP ' + status));
  }
  return j;
}

async function serviceAction(server, action, args = {}) {
  return serviceRequest('POST', 'api/servers/' + server + '/action', {action, args});
}

function serverPublicIp(srv, ov) {
  if (!srv) return '';
  if (srv.public_ip && !/^(127\.|localhost)/i.test(srv.public_ip)) return srv.public_ip;
  const isLan = ip => /^(10\.|192\.168\.|169\.254\.|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(ip);
  const pub = (ov && (ov.public_ip || (ov.status && ov.status.public_ip))) || '';
  if (pub && !isLan(pub) && !/^(127\.|localhost)/i.test(pub) && /^\d{1,3}(\.\d{1,3}){3}$/.test(pub)) return pub;
  if (srv.host && !/^(127\.|localhost)/i.test(srv.host) && /^\d{1,3}(\.\d{1,3}){3}$/.test(srv.host)) return srv.host;
  if (srv.api_url) {
    const m = String(srv.api_url).match(/:\/\/([^\/:]+)/);
    const h = m ? m[1] : srv.api_url;
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h)) return h;
  }
  if (pub && !/^(127\.|localhost)/i.test(pub) && /^\d{1,3}(\.\d{1,3}){3}$/.test(pub)) return pub;
  return (srv.host && !/^(127\.|localhost)/i.test(srv.host)) ? srv.host : '';
}

function findNodeServer(nodeName, selected) {
  const peers = SERVERS.filter(s => s.role === 'node');
  if (selected) return peers.find(s => s.name === selected);
  const exact = peers.find(s => s.name === nodeName);
  if (exact) return exact;
  const matches = peers.filter(s => {
    const ov = OVS[s.name] || {};
    return [...(ov.services || []), ...(ov.backhaul_services || [])].some(x => x.name === nodeName);
  });
  return matches.length === 1 ? matches[0] : null;
}

async function configureServiceCarrier(iranSrv, nodeName, carrier, port, extra = {}) {
  let changed = false;
  let oldLane = '', frpSwitched = false, frpNodeStarted = false, noiseSwitched = false, nodeServer = '';
  try {
    const sIran = SERVERS.find(s => s.name === iranSrv && s.role === 'iran');
    const sNode = findNodeServer(nodeName, extra.node_server);
    if (!sIran || !sNode) throw new Error('سرور مقصد مشخص نیست؛ نود خارجی را صریح انتخاب کنید.');
    nodeServer = sNode.name;
    if (!['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre'].includes(carrier)) throw new Error('حامل نامعتبر است.');
    if (extra.carrier_port && (!/^\d+$/.test(String(extra.carrier_port)) || +extra.carrier_port < 1 || +extra.carrier_port > 65535)) throw new Error('پورت حامل نامعتبر است.');
    if (!extra.silent) toast('⏳ در حال همگام‌سازی حامل ' + carrier.toUpperCase() + ' با سرور ایران و نود (' + sNode.name + ')...', 0);
    const state = JSON.parse((await serviceAction(iranSrv, 'status')).out);
    const old = (state.nodes || []).find(x => x.name === nodeName);
    const nov = await serviceRequest('GET','api/servers/'+sNode.name+'/overview');
    if(nov.reachable===false||!Array.isArray(nov.services)||!Array.isArray(nov.backhaul_services))throw new Error(t('service_peer_unavailable'));
    OVS[sNode.name]=nov;
    const nodeSvc = [...(nov.services || []), ...(nov.backhaul_services || [])].find(x => x.name === nodeName);
    const memIran = ((OVS[iranSrv] || {}).nodes || []).find(x => x.name === nodeName);
    // Taghir-e hamel nabayad inbound-e service-e mojood ra avaz konad.
    if (old) {
      port = old.inbound_port || old.inbound;
      if (!port) throw new Error("پورت اینباند در وضعیت ایران موجود نیست؛ ابتدا سرور ایران را به‌روزرسانی کنید.");
    }
    if (!port || !/^\d+$/.test(String(port))) {
      port = (old && (old.inbound_port || old.inbound)) ||
             (nodeSvc && nodeSvc.inbound) ||
             (memIran && (memIran.inbound_port || memIran.inbound)) ||
             8443;
    }
    if (!/^\d+$/.test(String(port)) || +port < 1 || +port > 65535) throw new Error('پورت اینباند باید بین ۱ و ۶۵۵۳۵ باشد.');
    const features = state.features || {};
    const iranIp = extra.iran_ip || serverPublicIp(sIran, {status:state}) || serverPublicIp(sIran, OVS[sIran.name]);
    const nodeIp = extra.node_ip || serverPublicIp(sNode, nov);
    const host = iranIp;
    const isGre = carrier === 'gre' || carrier === 'frp_gre';
    let greIp = extra.gre_ip || '10.10.10.1', nodeGreIp;
    if (isGre) {
      const validIpv4 = value => {
        const parts = String(value || '').split('.');
        return parts.length === 4 && parts.every(x => /^\d{1,3}$/.test(x) && +x <= 255) && +parts[0] !== 0 && +parts[0] !== 127;
      };
      if (!validIpv4(iranIp) || !validIpv4(nodeIp)) throw new Error('برای GRE، IP عمومی IPv4 واقعی هر دو سرور را در فیلدهای ایران و نود وارد کنید.');
      const octets = greIp.split('.').map(Number);
      if (octets.length !== 4 || octets.some(x => !Number.isInteger(x) || x < 0 || x > 255) || ![1,2].includes(octets[3] % 4)) {
        throw new Error('آدرس مجازی GRE باید یک IP معتبر در ساب‌نت /30 باشد (مانند 10.10.10.1).');
      }
      nodeGreIp = [...octets.slice(0,3), octets[3] ^ 3].join('.');
      const g = features.gre || {};
      if (g.configured && (g.remote_ip !== nodeIp || g.tunnel_ip !== greIp)) throw new Error('gre1 قبلاً برای مسیر دیگری تنظیم شده؛ ابتدا آن مسیر را مدیریت کنید.');
    }
    // ghofl-e server-side joda ast; in flow transaction-e chand-serveri nist.
    // dar shekast hich success-i neshan nemidahim va state-e vaghei refresh mishavad.
    const A = async (server, action, args) => { changed = true; return serviceAction(server, action, args); };
    if (!old) await A(iranSrv, 'add_node', {name:nodeName,inbound:String(port)});

    const targetLane = carrier === 'backhaul' ? 'backhaul' : carrier === 'noise' ? 'noise' : ['frp','frp_gre'].includes(carrier) ? 'frp' : 'ws';
    oldLane = old && old.transport || 'ws';
    if (isGre) {
      await A(iranSrv, 'gre_on', {remote_ip:nodeIp,tunnel_ip:greIp,name:'gre1'});
      await A(sNode.name, 'gre_on', {remote_ip:iranIp,tunnel_ip:nodeGreIp,name:'gre1'});
      // UP boodan-e interface dalil-e residan-e packet-haye GRE nist.
      await serviceAction(sNode.name, 'gre_probe', {peer_ip:greIp,name:'gre1'}).then(j => {
        if (j.rc !== 0) throw new Error(j.err || j.out || 'GRE peer dastres nist.');
      });
    }
    let connection;
    if (targetLane === 'frp') {
      if (!(features.frp || {}).configured || !(features.frp || {}).active) await A(iranSrv, 'frp_on', {port:String(extra.carrier_port || (features.frp || {}).port || 7000),transport:extra.frp_transport || (features.frp || {}).transport || 'tcp'});
      connection = await serviceRequest('GET', 'api/servers/' + iranSrv + '/frpconnect');
      if (!connection.token || !connection.port || !connection.transport) throw new Error('اطلاعات اتصال FRP ناقص است.');
      if ((extra.carrier_port && +extra.carrier_port !== +connection.port) || (extra.frp_transport && extra.frp_transport !== connection.transport)) {
        await A(iranSrv, 'frp_on', {port:String(extra.carrier_port || connection.port),token:connection.token,transport:extra.frp_transport || connection.transport});
        connection = await serviceRequest('GET', 'api/servers/' + iranSrv + '/frpconnect');
      }
    } else if (targetLane === 'noise') {
      const f = features.noise || {};
      if (!f.configured || !f.active || (extra.carrier_port && +extra.carrier_port !== +f.port)) await A(iranSrv, 'noise_on', {port:String(extra.carrier_port || f.port || 2334)});
      const noiseState = JSON.parse((await serviceAction(iranSrv, 'status')).out);
      if (!(noiseState.features && noiseState.features.noise && noiseState.features.noise.active)) throw new Error('سرویس Noise روی ایران فعال نشد؛ لاگ rathole-noise را بررسی کنید.');
      connection = await serviceRequest('GET', 'api/servers/' + iranSrv + '/noiseconnect');
      if (!connection.remote || !connection.pubkey) throw new Error('آدرس یا کلید Noise از ایران دریافت نشد.');
      if (extra.iran_ip) connection.remote = extra.iran_ip + ':' + connection.remote.split(':').pop();
    } else if (targetLane === 'backhaul') {
      const f = features.backhaul || {};
      const tr = extra.bh_transport || 'wssmux';
      const mode = /^wss/.test(tr) ? 'nginx_tls' : 'direct_ip';
      if (!f.configured || (extra.bh_transport && extra.bh_transport.replace('wss','ws') !== f.transport) || (extra.carrier_port && +extra.carrier_port !== +f.port) || (extra.profile && extra.profile !== f.profile)) await A(iranSrv, 'backhaul_on', {port:String(extra.carrier_port || f.port || 3080),transport:tr.replace('wss','ws'),mode,profile:extra.profile || f.profile || 'balanced'});
      // Token va parametrhaye nahayi ra az server bekhan.
      connection = await serviceRequest('GET', 'api/servers/' + iranSrv + '/backhaulconnect');

    } else if (carrier === 'kcp') {
      await A(iranSrv, 'kcp_on', {port:String(extra.carrier_port || (state.ports || {}).kcp || 443),profile:extra.profile || 'balanced'});
      connection = await serviceRequest('GET', 'api/servers/' + iranSrv + '/kcpconnect');
    } else if (carrier === 'plain' || carrier === 'gre') {
      const f = features.plain || {};
      const listener = String(extra.carrier_port || f.port || 8880);
      if (!f.configured || +listener !== +f.port) await A(iranSrv, 'plain_on', {port:listener});
      if (!host && !isGre) throw new Error('آدرس سرور ایران مشخص نیست.');
      connection = {remote:(isGre ? greIp : host) + ':' + listener};
    }
    const conn = await serviceRequest('GET', 'api/servers/' + iranSrv + '/nodeconnect/' + nodeName);
    if (!conn.name || !conn.token || !conn.inbound || !conn.remote_port) throw new Error('اطلاعات سرویس یا نگاشت پورت ایران ناقص است.');
    const oldIranLane = oldLane === 'frp_gre' ? 'frp' : oldLane;
    if (oldLane !== targetLane) {
      if (oldLane === 'frp' || oldLane === 'frp_gre') await A(sNode.name, 'frp_off');
      else if (oldLane === 'backhaul' && !(nov.backhaul_services||[]).some(x=>x.name!==nodeName)) await A(sNode.name, 'backhaul_off');
      else if (oldLane === 'noise') await A(sNode.name, 'noise_off');
    }
    if (targetLane !== 'noise' && oldIranLane !== targetLane && ['backhaul','noise','frp'].includes(oldIranLane)) await A(iranSrv, oldIranLane + '_node_off', {name:nodeName});
    if (targetLane === 'backhaul') {
      await A(iranSrv, 'backhaul_node_on', {name:nodeName});
      // lane-e backhaul joda ast; service ra dar registry-e dorost sabt kon.
      const bhArgs = {mode:connection.mode,remote_addr:connection.remote_addr || connection.domain,token:connection.token,transport:connection.transport,profile:connection.profile};
      if (connection.mode === 'direct_ip' && /^wss/.test(connection.transport || '')) {
        const prep = await serviceRequest('POST', 'api/ip-tls/prepare', {iran:iranSrv, node:sNode.name}).catch(()=>null);
        if (prep && prep.ok && prep.tls_trusted_root) bhArgs.tls_ca = prep.tls_trusted_root;
      }
      await A(sNode.name, 'backhaul_on', bhArgs);
      await A(sNode.name, 'add_bh_svc', {name:conn.name,token:connection.token,inbound:conn.inbound});
      if ((nov.services || []).some(x=>x.name===conn.name)) await A(sNode.name,'rm_svc',{name:conn.name});
    } else {
      const main = await serviceRequest('GET', 'api/servers/' + iranSrv + '/mainconnect');
      if (!main.server || (targetLane !== 'frp' && !main.control_path)) throw new Error('آدرس یا مسیر کنترل سرور ایران مشخص نیست.');
      // set-main node.env ra ghabl az avalin apply misazad.
      await A(sNode.name, 'set_main', {server:main.server,tls_hostname:main.tls_hostname || main.domain || ''});
      if ((nov.backhaul_services || []).some(x=>x.name===conn.name)) await A(sNode.name,'rm_bh_svc',{name:conn.name});
      await A(sNode.name, 'add_svc', {name:conn.name,token:conn.token,inbound:conn.inbound,remote_port:String(conn.remote_port)});
      if (targetLane === 'frp') {
        frpSwitched = true;
        await A(iranSrv, 'frp_node_on', {name:nodeName});
        frpNodeStarted = true;
        await A(sNode.name, 'frp_on', {
          remote: (isGre ? greIp + ':' + connection.port : (extra.iran_ip ? extra.iran_ip + ':' + connection.port : connection.remote)),
          token: connection.token,
          transport: connection.transport,
          remote_port: String(conn.remote_port)
        });
        await serviceAction(iranSrv, 'frp_ready', {name:nodeName}).then(j => {
          if (j.rc !== 0) throw new Error(j.err || j.out || 'FRP proxy register nashod.');
        });
      } else {
        if (carrier === 'ws') await A(sNode.name,'plain_off');
        else if (carrier === 'kcp') await A(sNode.name,'kcp_on',{remote:extra.iran_ip ? extra.iran_ip + ':' + connection.remote.split(':').pop() : connection.remote,key:connection.key,profile:connection.profile});
        else if (carrier === 'noise') {
          if (oldIranLane !== targetLane && ['backhaul','frp'].includes(oldIranLane)) await A(iranSrv, oldIranLane + '_node_off', {name:nodeName});
          await A(iranSrv, 'noise_node_on', {name:nodeName});
          noiseSwitched = true;
          await A(sNode.name,'noise_on',{remote:connection.remote,pubkey:connection.pubkey,pattern:connection.pattern || ''});
        }
        else await A(sNode.name,'plain_on',{remote:connection.remote});
        if (carrier !== 'noise') {
          if (main.control_path === '/') await A(sNode.name,'control_path_clear');
          else await A(sNode.name,'control_path_set',{path:main.control_path});
        }
      }
    }
    await loadOv(iranSrv); await loadOv(sNode.name);
    if (!extra.silent) toast('✓ تنظیمات حامل سرویس اعمال شد؛ وضعیت اتصال را بررسی کنید.');
    return {...conn,node_server:sNode.name};
  } catch (err) {
    if (noiseSwitched && oldLane !== 'noise') {
      await serviceAction(nodeServer, 'noise_off').catch(()=>{});
      await serviceAction(iranSrv, 'noise_node_off', {name:nodeName}).catch(()=>{});
    }
    if (frpSwitched && oldLane !== 'frp' && oldLane !== 'frp_gre') {
      // dar shekast-e FRP, masir-e pishfarz-e ghabli ra dobare faal kon.
      if (frpNodeStarted) await serviceAction(nodeServer, 'frp_off').catch(()=>{});
      await serviceAction(iranSrv, 'frp_node_off', {name:nodeName}).catch(()=>{});
    }
    if (changed) {
      await Promise.allSettled([loadOv(iranSrv), ...SERVERS.filter(s=>s.role==='node').map(s=>loadOv(s.name))]);
    }
    toast('⚠️ تنظیم حامل سرویس کامل نشد: ' + err.message + (changed ? '؛ بخشی از تنظیمات ممکن است اعمال شده باشد.' : ''));
    return false;
  }
}


function quickCarrierModal(iran, node, curCarrier, peerName) {
  if(curCarrier==='game'){toast(t('service_game_hint'));return;}
  const opts = [
    {v:'frp_gre', t:'🚀🛡️ ترکیبی FRP + GRE (لایه ۳ با استریم مالتی‌پلکس)'},
    {v:'frp', t:'🚀 هسته تونل معکوس FRP (fatedier - مالتی‌پلکس TCP/KCP/QUIC)'},
    {v:'ws', t:'🌐 وب‌سوکت با TLS روی ۴۴۳ (WS)'},
    {v:'kcp', t:'🛡️ پروتکل ضد اختلال KCP (UDP+FEC)'},
    {v:'backhaul', t:'⚡ مالتی‌پلکس ترافیک بالا Backhaul (SMUX)'},
    {v:'noise', t:'🔒 پروتکل امن رمزنگاری Noise'},
    {v:'plain', t:'📡 ساده بدون رمز Plain (HTTP)'},
    {v:'gre', t:'🌐 تونل شبکه L3 لینوکس GRE'}
  ];
  const iov=OVS[iran]||{};
  const nd=(iov.nodes||[]).find(x=>x.name===node)||{};
  const c={backendPort:nd.inbound_port||nd.inbound};
  const sIran = SERVERS.find(s => s.name === iran);
  const peers = SERVERS.filter(s => s.role === 'node');
  const sNode = findNodeServer(node, peerName) || (peers.length === 1 ? peers[0] : null);
  const defIranIp = serverPublicIp(sIran, OVS[iran]);
  const defNodeIp = sNode ? serverPublicIp(sNode, OVS[sNode.name]) : '';
  const frpTrOpts = [
    {v:'quic', t:'QUIC (بر پایه UDP، ضد فیلتر و پرسرعت)'},
    {v:'kcp', t:'KCP (بر پایه UDP با تصحیح خطای FEC)'},
    {v:'websocket', t:'WebSocket (شبیه ترافیک وب)'},
    {v:'tcp', t:'TCP (حالت استاندارد)'}
  ];
  const bhTrOpts = [
    {v:'wssmux', t:'wssmux (TLS + SMUX مالتی‌پلکس روی ۴۴۳)'},
    {v:'wsmux', t:'wsmux (بدون TLS + SMUX مالتی‌پلکس)'},
    {v:'wss', t:'wss (TLS بدون مالتی‌پلکس)'},
    {v:'ws', t:'ws (وب‌سوکت ساده)'}
  ];
  const profOpts = [
    {v:'balanced', t:'Balanced (عادی)'},
    {v:'lossy', t:'Lossy (پکت‌لاس بالا)'},
    {v:'aggressive', t:'Aggressive (اختلال شدید)'}
  ];
  formModal(`تنظیم حامل و پروتکل سرویس ${node}`, [
    {id:'node_server', label:'سرور نود خارجی:', type:'select', val:(sNode ? sNode.name : (c.nodeServer || '')), opts:SERVERS.filter(s=>s.role==='node').map(s=>({v:s.name,t:s.name}))},
    {id:'carrier', label:'پروتکل و حامل جدید:', type:'select', val:curCarrier, opts:opts},
    {id:'iran_ip', label:'IP عمومی سرور ایران (برای Noise / FRP / KCP / GRE):', type:'text', val:c.iran_ip || defIranIp, ph:'مثلاً 45.234.54.9'},
    {id:'node_ip', label:'IP عمومی سرور خارج (برای GRE):', type:'text', val:c.node_ip || defNodeIp, ph:'مثلاً 78.135.77.57'},
    {id:'gre_ip', label:'آدرس مجازی GRE (برای GRE یا FRP+GRE):', type:'text', val:c.gre_ip || '10.10.10.1'},
    {id:'frp_tr', label:'مد ترانسپورت FRP (برای FRP یا FRP+GRE — یک پروتکل UDP فعال روی هر پورت: KCP یا QUIC):', type:'select', val:((iov.status||{}).features||{}).frp?.transport || (iov.frp||{}).transport || 'tcp', opts:frpTrOpts},
    {id:'bh_tr', label:'مد ترانسپورت Backhaul (برای Backhaul):', type:'select', val:((OVS[(sNode||{}).name]||{}).backhaul||{}).transport || 'wssmux', opts:bhTrOpts},
    {id:'profile', label:'پروفایل شتاب KCP / Backhaul:', type:'select', val:c.profile || 'balanced', opts:profOpts},
    {id:'carrier_port', label:'پورت اختصاصی حامل در ایران (اختیاری):', type:'text', val:c.carrier_port || '', ph:'پیش‌فرض: FRP=7000, BH=3080, Plain=8880, Noise=2334'}
  ], async v => {
    closeModal();
    const existingIran = ((OVS[iran]||{}).nodes||[]).find(x => x.name === node);
    const resolvedPort = c.backendPort || (existingIran && (existingIran.inbound_port || existingIran.inbound)) || 8443;
    await configureServiceCarrier(iran, node, v.carrier, resolvedPort, {
      node_server: v.node_server || (sNode ? sNode.name : c.nodeServer),
      frp_transport: v.frp_tr, bh_transport: v.bh_tr,
      profile: v.profile, gre_ip: v.gre_ip,
      iran_ip: v.iran_ip, node_ip: v.node_ip,
      carrier_port: v.carrier_port
    });
  });
}

// ---------- namaye jadval: har edge yek radif ----------
function drawRouteTable(){
 const w=$('gwrap'); if(!w)return;
 const M=buildGraphModel();
 if(!M.edges.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const rows=M.edges.slice().sort((a,b)=>(a.tgt.name+a.node).localeCompare(b.tgt.name+b.node));
 let x=`<div style="direction:${LANG==='fa'?'rtl':'ltr'};padding:4px 10px">`;
 x+=tbl([t('c_node'),t('c_upstream'),t('c_iran'),t('c_tunnel'),t('n_svcs'),t('c_status')]);
 const tbMap={ws:'b-ws',kcp:'b-kcp',noise:'b-noise',plain:'b-plain',backhaul:'b-backhaul',frp:'b-frp',gre:'b-gre',frp_gre:'b-frp_gre',paqet:'b-paqet'};
 rows.forEach(e=>{
  const tb=tbMap[e.tunnel]||'b-ws';
  const st=e.status==='warn'?`<span class="dot d-bad"></span> ${t('tun_down')}`
          :(e.status==='ok'?`<span class="dot d-ok"></span> ${t('tun_up')}`:`<span class="dot d-un"></span>`);
  const tgt=e.tgt.kind==='iran'
    ?`<a style="color:var(--primary-hover);cursor:pointer" onclick="nav('#/server/${h(e.tgt.name)}')">${h(e.tgt.name)}</a>`
    :`${h(e.tgt.name)} <span class="sub">(${t('g_external')})</span>`;
  x+=`<tr><td><a style="color:var(--primary-hover);cursor:pointer" onclick="nav('#/server/${h(e.node)}')">${h(e.node)}</a></td>
   <td class="mono">${h(e.label||'main')}</td><td>${tgt}</td>
   <td><span class="badge ${tb}">${h(e.tunnel)}</span></td>
   <td class="mono">${h(e.svcs.join(', ')||'-')}</td><td>${st}</td></tr>`;});
 x+='</table></div>';
 w.innerHTML=x;
}
// host-e yek "host:port" ra be name-e server-e iran dar inventory map mikonad
function matchIran(hostport,idmap){
 if(!hostport)return null;
 const hst=hostport.replace(/:\d+$/,'').toLowerCase();
 return idmap[hst]||null;
}
function buildGraphModel(){
 const irans=SERVERS.filter(s=>s.role==='iran'), nds=SERVERS.filter(s=>s.role==='node');
 // idmap: host/domain → name-e iran (domain az path-e nodes-e overview darmiayad)
 const idmap={};
 irans.forEach(s=>{idmap[(s.host||'').toLowerCase()]=s.name;
  const ov=OVS[s.name];
  ((ov&&ov.nodes)||[]).forEach(d=>{const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');
   if(m)idmap[m[1].replace(/:\d+$/,'').toLowerCase()]=s.name;});});
 const edges=[],externals={};
 // fallback: agar host match nashod (masalan inventory IP darad vali node ba domain vasl ast),
 // az rooye esm-e service-haye moshtarak irane motenazer ra peyda kon.
 function svcFallback(svcNames){
  const hits=irans.filter(s=>{const ovn=((OVS[s.name]||{}).nodes||[]).map(x=>x.name);
   return svcNames.some(nm=>ovn.indexOf(nm)>=0);});
  return hits.length===1?hits[0].name:null;
 }
 function target(hostport,svcNames){
  const nm=matchIran(hostport,idmap); if(nm)return{kind:'iran',name:nm};
  const fb=svcFallback(svcNames||[]); if(fb)return{kind:'iran',name:fb};
  const hst=(hostport||'?').replace(/:\d+$/,'');
  externals[hst]=externals[hst]||{name:hst}; return{kind:'ext',name:hst};
 }
 nds.forEach(d=>{
  const ov=OVS[d.name]; if(!ov||ov.reachable===false)return;
  if(ov.main_server){edges.push({tgt:target(ov.main_server,(ov.services||[]).map(x=>x.name)),node:d.name,tunnel:ov.main_tunnel||'ws',
   svcs:(ov.services||[]).map(x=>x.name),label:''});}
  (ov.upstreams||[]).forEach(u=>{edges.push({tgt:target(u.server,(u.services||[]).map(x=>x.name)),node:d.name,tunnel:u.tunnel||'ws',
   svcs:(u.services||[]).map(x=>x.name),label:u.id});});
 });
 // vaziat-e har edge az doctor-e iran: agar HAR yeki az service-haye in edge kharab bashad → warn
 edges.forEach(e=>{
  e.svc=e.svcs.length;
  if(e.tgt.kind!=='iran')return;
  const hov=OVS[e.tgt.name]; const hn=((hov||{}).health||{}).nodes||{};
  const keys=e.svcs.concat([e.node]);
  if(keys.some(k=>hn[k]==='warn'))e.status='warn';
  else if(keys.some(k=>hn[k]==='ok'))e.status='ok';
 });
 return {irans,nds,edges,externals:Object.keys(externals)};
}
function drawGraph(){
 const w=$('gwrap'); if(!w)return;
 if(GVIEW==='table'){drawRouteTable();return;}
 const M=buildGraphModel();
 if(!M.irans.length&&!M.nds.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const anyOv=SERVERS.some(s=>OVS[s.name]);
 const BW=195,BH=60,GY=26,X=[26,286,634],WID=856;
 // sotoon-e node-ha ra bar asas-e iran-e mabda sort kon ta edge-ha kamtar ghat shavand
 const firstIran={};
 M.edges.forEach(e=>{if(!(e.node in firstIran))firstIran[e.node]=(e.tgt.kind==='iran'?e.tgt.name:'zz_'+e.tgt.name);});
 let nodeNames=M.nds.slice().sort((a,b)=>((firstIran[a.name]||'~')+a.name).localeCompare((firstIran[b.name]||'~')+b.name)).map(s=>s.name);
 nodeNames=gApplyOrder(nodeNames,'node');                      // tartib-e dasti (drag) oloviat darad
 const nodeCol=nodeNames.map(nm=>M.nds.find(s=>s.name===nm)).filter(Boolean);
 const iranNames=gApplyOrder(M.irans.map(s=>s.name),'iran');
 const iranCol=iranNames.map(nm=>{const s=M.irans.find(x=>x.name===nm);return{name:s.name,host:s.host,ext:false};})
   .concat(M.externals.map(hst=>({name:hst,host:'',ext:true})));
 // mokhtasat-e amoodi
 function place(list,x,hh){let y=46;const pos={};list.forEach(it=>{pos[it.name?it.name:it]={x,y,h:hh};y+=hh+GY;});return{pos,bot:y};}
 const pi=place(iranCol,X[1],BH+8), pn=place(nodeCol,X[2],BH);
 const H=Math.max(pi.bot,pn.bot,190)+14;
 // markaz-e amoodi baraye sotoon-e kootah-tar
 function recenter(p,bot){const off=(H-14-bot)/2;if(off>4)Object.values(p).forEach(o=>o.y+=off);}
 recenter(pi.pos,pi.bot);recenter(pn.pos,pn.bot);
 const uy=H/2-35;
 let sv=`<svg viewBox="0 0 ${WID} ${H}" xmlns="http://www.w3.org/2000/svg">`;
 sv+=`<text x="${X[0]+60}" y="24" text-anchor="middle" class="gcolhead">${t('g_users')}</text>`;
 sv+=`<text x="${X[1]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_iran_col')}</text>`;
 sv+=`<text x="${X[2]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_node_col')}</text>`;
 // --- edges: user → iran (dade-ye vorodi) ---
 const ucx=X[0]+120;
 iranCol.forEach(it=>{if(it.ext)return;const p=pi.pos[it.name];const y2=p.y+ (BH+8)/2;
  sv+=`<path class="edge e-user" d="M ${ucx} ${uy+35} C ${(ucx+X[1])/2} ${uy+35} ${(ucx+X[1])/2} ${y2} ${X[1]} ${y2}" marker-end="url(#arr)"/>`;});
 // --- edges: iran ← node (tunnel-haye barghashti) ---
 // taghsim-e noghat-e etesal rooye labe-ye har box baraye jelogiri az ham-poshani
 const outCnt={},inCnt={};
 M.edges.forEach(e=>{const k=e.tgt.name;outCnt[k]=(outCnt[k]||0)+1;inCnt[e.node]=(inCnt[e.node]||0)+1;});
 const outIdx={},inIdx={};
 let edgeSvg='',labSvg='';
 M.edges.forEach(e=>{
  const P1=pi.pos[e.tgt.name],P2=pn.pos[e.node]; if(!P1||!P2)return;
  outIdx[e.tgt.name]=(outIdx[e.tgt.name]||0)+1; inIdx[e.node]=(inIdx[e.node]||0)+1;
  const y1=P1.y+P1.h*outIdx[e.tgt.name]/(outCnt[e.tgt.name]+1);
  const y2=P2.y+P2.h*inIdx[e.node]/(inCnt[e.node]+1);
  const x1=X[1]+BW,x2=X[2],mx=(x1+x2)/2;
  const cls=e.status==='warn'?'e-bad':('e-'+(['ws','kcp','noise','plain','backhaul','frp','gre','frp_gre','paqet'].indexOf(e.tunnel)>=0?e.tunnel:'ws'));
  const anim=(e.tunnel!=='ws'||e.status==='warn')?' flow':'';
  const dim=e.status==='warn'?'':''; // edge-e kharab ghermez mishavad, dim nemikonim
  edgeSvg+=`<path class="edge ${cls}${anim}${dim}" d="M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}"/>`;
  // label-e vasat-e edge: [upstream-id ·] tunnel · svc
  const txt=(e.label?e.label+' · ':'')+e.tunnel+(e.svc?(' · '+e.svc):'');
  const tw=txt.length*6.6+14, lx=mx-tw/2, ly=(y1+y2)/2-9;
  labSvg+=`<g class="elab" onclick="nav('#/server/${h(e.node)}')"><rect x="${lx}" y="${ly}" width="${tw}" height="18" rx="9"/>`+
   `<text x="${mx}" y="${ly+13}" text-anchor="middle">${h(txt)}</text></g>`;
 });
 sv+=edgeSvg;
 // --- box: users ---
 sv+=`<g><rect class="gbox gbox-ext" x="${X[0]}" y="${uy}" width="120" height="70" rx="12"/>`;
 [[36,uy+26],[60,uy+20],[84,uy+26]].forEach(c=>{sv+=`<circle cx="${c[0]}" cy="${c[1]}" r="6" fill="var(--text-faint)"/><path d="M ${c[0]-9} ${c[1]+18} a 9 9 0 0 1 18 0" fill="var(--text-faint)"/>`;});
 sv+=`<text x="${X[0]+60}" y="${uy+60}" text-anchor="middle" class="gsub">${t('g_users')}</text></g>`;
 // --- box-haye iran ---
 iranCol.forEach(it=>{
  const p=pi.pos[it.name],hh=P=>p.y+P;
  const ov=OVS[it.name],off=!it.ext&&ov&&ov.reachable===false;
  const click=it.ext?'':` onclick="nav('#/server/${h(it.name)}')"`;
  const drag=it.ext?'':` data-gcol="iran" data-gname="${h(it.name)}"`;
  sv+=`<g${click}${drag}><rect class="gbox gbox-iran${it.ext?' gbox-ext':''}${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(it.ext?t('g_external'):it.name)}</title></rect>`;
  const dcls=it.ext?'#8ba0b6':(off?'var(--danger)':(ov?(((ov.health||{}).fail===0)?'var(--success)':'var(--danger)'):'var(--warning)'));
  sv+=`<circle cx="${p.x+16}" cy="${hh(20)}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${hh(24)}" class="gtxt">${h(it.name.length>20?it.name.slice(0,19)+'…':it.name)}</text>`;
  if(it.ext){sv+=`<text x="${p.x+14}" y="${hh(44)}" class="gsub">${t('g_external')}</text>`;}
  else{sv+=`<text x="${p.x+14}" y="${hh(42)}" class="gsub">${h((it.host||'').slice(0,26))}</text>`;
   let inf=':443';
   if(ov){const k=ov.kcp||{},nz=ov.noise||{};inf=':443'+(k.enabled?(' · kcp'+(k.port?(' udp:'+k.port):'')):'')+(nz.enabled?(' · noise:'+(nz.port||'')):'');
    inf+=' · '+((ov.nodes||[]).length)+' '+t('n_nodes');}
   sv+=`<text x="${p.x+14}" y="${hh(58)}" class="gsub">${h(inf.slice(0,30))}</text>`;}
  sv+='</g>';});
 // --- box-haye node ---
 nodeCol.forEach(d=>{
  const p=pn.pos[d.name];const ov=OVS[d.name];const off=ov&&ov.reachable===false;
  const bad=M.edges.some(e=>e.node===d.name&&e.status==='warn');
  const dcls=off||bad?'var(--danger)':(ov?'var(--success)':'var(--warning)');
  sv+=`<g onclick="nav('#/server/${h(d.name)}')" data-gcol="node" data-gname="${h(d.name)}"><rect class="gbox${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(d.name)}</title></rect>`;
  sv+=`<circle cx="${p.x+16}" cy="${p.y+20}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${p.y+24}" class="gtxt">${h(d.name.length>20?d.name.slice(0,19)+'…':d.name)}</text>`;
  const sub=(d.host||'')+(ov&&ov.services?(' · '+ov.services.length+' '+t('n_svcs')):'');
  sv+=`<text x="${p.x+14}" y="${p.y+44}" class="gsub">${h(sub.slice(0,30))}</text></g>`;});
 sv+=labSvg;
 sv+=`<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--text-faint)"/></marker></defs>`;
 sv+='</svg>';
 if(!anyOv)sv=`<div class="empty" style="padding:12px 16px 0">${t('g_loading')}</div>`+sv;
 w.innerHTML=sv;
 bindGraphDrag(w);
}
// ---------- drag-e amoodi-e box-ha (tartib dar localStorage) ----------
function bindGraphDrag(w){
 const svg=w.querySelector('svg'); if(!svg)return;
 svg.querySelectorAll('g[data-gname]').forEach(g=>{
  g.style.cursor='grab';
  g.addEventListener('pointerdown',ev=>{
   const col=g.dataset.gcol,name=g.dataset.gname;
   const vb=svg.viewBox.baseVal,scale=vb.height/svg.getBoundingClientRect().height;
   let moved=false;const y0=ev.clientY;
   const mv=e=>{const dy=(e.clientY-y0)*scale;
    if(!moved&&Math.abs(dy)>6){moved=true;_gDragging=true;g.style.cursor='grabbing';svg.style.userSelect='none';}
    if(moved)g.setAttribute('transform','translate(0,'+dy+')');};
   const up=e=>{
    document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);document.removeEventListener('pointercancel',up);
    svg.style.userSelect='';_gDragging=false;
    if(!moved||e.type==='pointercancel'){if(moved)g.removeAttribute('transform');return;}                      // click-e sade → navigation-e aadi
    // click-e badi (ke browser bad az pointerup mifrestad) navigation nakonad
    g.addEventListener('click',ce=>{ce.stopPropagation();ce.preventDefault();},{capture:true,once:true});
    // tartib-e jadid: markaz-e box-e keshide-shode ra beyn-e baghye peyda kon
    const others=[...svg.querySelectorAll('g[data-gcol="'+col+'"]')].filter(x=>x!==g);
    const cy=el=>{const r=el.querySelector('rect');return parseFloat(r.getAttribute('y'))+parseFloat(r.getAttribute('height'))/2;};
    const myY=cy(g)+(e.clientY-y0)*scale;
    const order=others.map(x=>({n:x.dataset.gname,y:cy(x)}));
    order.push({n:name,y:myY});
    order.sort((a,b)=>a.y-b.y);
    localStorage.setItem('rh_gorder_'+col,JSON.stringify(order.map(x=>x.n)));
    drawGraph();
   };
   document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up);document.addEventListener('pointercancel',up);
  });
 });
}

// ---------- safhe: audit / settings (ghablan modal boodand) ----------
async function renderAuditPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('audit')}</h2><span id="audit_chain_badge"></span></div>
  <div class="filter-bar"><div class="search-box">${icon('search')}<input type="search" data-tbl-filter="audit_tbl" placeholder="${h(t('flt_search_audit'))}" aria-label="${h(t('flt_search_audit'))}"></div></div>
  <section class="card" style="margin-top:0"><div class="cbody" id="auditbody"><div class="empty">${t('loading')}</div></div></section>`;
 const [audRes,verRes]=await Promise.all([api('GET','api/audit?limit=100'),api('GET','api/audit/verify')]);
 const badge=$('audit_chain_badge');
 if(badge&&verRes&&verRes.status===200&&verRes.j){
  const v=verRes.j;
  badge.innerHTML=v.ok
   ?('<span class="badge b-ok">'+h(t('audit_valid'))+' ('+h(String(v.chained||0))+'/'+h(String(v.total||0))+')</span>')
   :('<span class="badge b-bad">'+h(t('audit_broken'))+' #'+h(String(v.broken_line??'?'))+'</span>');
 }
 const j=audRes?audRes.j:[];
 const box=$('auditbody'); if(!box)return;
 const rows=(j||[]);
 if(!rows.length){box.innerHTML=`<div class="empty">${t('no_audit')}</div>`;return;}
 let x=`<div class="table-wrap" tabindex="0" role="region" aria-label="${h(t('audit'))}" id="audit_tbl"><table><thead><tr><th>${t('c_time')}</th><th>${t('c_user')}</th><th>server</th><th>${t('c_action')}</th><th>rc</th></tr></thead><tbody>`;
 rows.forEach(e=>{const d=new Date((e.ts||0)*1000).toLocaleString(LANG==='fa'?'fa-IR':'en-US');
  const rcOk=Number(e.rc)===0;
  x+=`<tr><td class="mono">${h(d)}</td><td class="mono">${h(e.user)}</td><td>${h(e.server)}</td><td class="mono">${h(e.action)}</td><td><span class="badge ${rcOk?'b-ok':'b-bad'}">${h(e.rc)}</span></td></tr>`;});
 box.innerHTML=x+'</tbody></table></div>';
}
async function renderSettingsPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('settings')}</h2></div><div id="setbody"><div class="empty">${t('loading')}</div></div>`;
 const {j}=await api('GET','api/config');const c=j||{};
 const warn=c.insecure?`<div class="settings-alert" role="alert">${t('insecure')}</div>`:'';
 const curTheme=THEME_PREF||'system';
 const box=$('setbody'); if(!box)return;
 box.innerHTML=`${warn}
  <div class="settings-grid">
   <section class="settings-section"><h3>${h(t('theme_appearance'))}</h3>
    <div class="settings-kv" style="margin-bottom:14px">
     <span class="k">${h(t('theme'))}</span>
     <div class="theme-seg" role="group" aria-label="${h(t('theme_appearance'))}">
      <button type="button" class="${curTheme==='system'?'on':''}" data-theme-opt="system" onclick="setThemeMode('system')">${icon('monitor')}<span>${h(t('theme_system'))}</span></button>
      <button type="button" class="${curTheme==='light'?'on':''}" data-theme-opt="light" onclick="setThemeMode('light')">${icon('sun')}<span>${h(t('theme_light'))}</span></button>
      <button type="button" class="${curTheme==='dark'?'on':''}" data-theme-opt="dark" onclick="setThemeMode('dark')">${icon('moon')}<span>${h(t('theme_dark'))}</span></button>
     </div>
     <span class="k">${h(t('lang_label'))}</span>
     <div class="btns"><button class="s" type="button" onclick="toggleLang()">${icon('language')}<span>${LANG==='fa'?'فارسی → English':'English → فارسی'}</span></button></div>
     <span class="k">${h(t('hub_proxy_lbl'))}</span>
     <div class="btns"><span class="mono sub">${h(c.proxy||'direct')}</span><button class="gh" type="button" onclick="editHubProxy()">${h(t('manage'))}</button></div>
    </div>
   </section>
   <section class="settings-section"><h3>${t('t_settings')}</h3><div class="settings-kv">
    <span class="k">${t('l_apitoken')}</span><span class="mono">${h(c.api_token_hint||'')}</span>
    <span class="k">${t('l_listen')}</span><span class="mono">${h(c.listen_host||'')}:${h(c.listen_port||'')}</span>
   </div><div class="sub" style="margin-top:8px">${h(t('metrics_hint'))}</div><div class="modal-actions"><button class="s" type="button" onclick="rotTok()">${t('rot_tok')}</button></div></section>
   <section class="settings-section"><h3>${h(t('sec_2fa_title'))}</h3>
    <div class="settings-kv">
     <span class="k">${h(t('sec_2fa_title'))}</span>
     <span class="badge ${c.totp_enabled?'b-ok':'b-bad'}">${h(c.totp_enabled?t('sec_2fa_on'):t('sec_2fa_off'))}</span>
    </div>
    <div class="modal-actions">${c.totp_enabled
     ?`<button class="s" type="button" onclick="disable2faModal()">${h(t('sec_2fa_disable'))}</button>`
     :`<button class="g" type="button" onclick="setup2fa()">${h(t('sec_2fa_setup'))}</button>`}</div>
   </section>
   <section class="settings-section" style="grid-column:1 / -1">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
     <h3 style="margin:0">${h(t('sec_tokens_title'))}</h3>
     <button class="g" type="button" onclick="createScopedTokenModal()">${h(t('sec_token_create'))}</button>
    </div>
    <div id="tok_list" style="margin-top:10px"><div class="empty">${t('loading')}</div></div>
   </section>
   <section class="settings-section" style="grid-column:1 / -1"><h3>${h(t('mon_title'))}</h3><div id="mon_card"><div class="empty">${t('loading')}</div></div></section>
   <section class="settings-section" style="grid-column:1 / -1"><h3>${h(t('upd_sec_title'))}</h3>
    <div class="sub" style="margin-bottom:10px">${h(t('upd_sec_desc'))}</div>
    <div class="settings-form" style="max-width:540px">
     <div class="field"><label for="upd_chan">${h(t('upd_channel'))}</label>
      <select id="upd_chan">
       <option value="stable"${(c.update_channel||'stable')==='stable'?' selected':''}>stable</option>
       <option value="beta"${c.update_channel==='beta'?' selected':''}>beta</option>
      </select>
     </div>
     <div class="field"><label for="upd_relay">${h(t('upd_relay_mode'))}</label>
      <select id="upd_relay">
       <option value="auto"${(c.update_relay_mode||'auto')==='auto'?' selected':''}>${h(t('upd_relay_auto'))}</option>
       <option value="direct"${c.update_relay_mode==='direct'?' selected':''}>${h(t('upd_relay_direct'))}</option>
       <option value="relay"${c.update_relay_mode==='relay'?' selected':''}>${h(t('upd_relay_relay'))}</option>
      </select>
     </div>
     <div class="field"><label for="upd_proxy">${h(t('upd_proxy'))}</label><input id="upd_proxy" type="text" value="${h(c.update_proxy||'')}" placeholder="socks5h://127.0.0.1:1080"></div>
     <div class="field"><label><input id="upd_req_sig" type="checkbox"${c.update_require_sig?' checked':''}> ${h(t('upd_require_sig'))}</label></div>
     <div class="btns"><button class="g" type="button" onclick="saveUpdateSettings()">${h(t('upd_save'))}</button></div>
    </div>
   </section>
   <section class="settings-section" style="grid-column:1 / -1"><h3>${t('chpw')}</h3><div class="settings-form" style="max-width:460px">
    <div class="field"><label for="cpw">${t('l_curpw')}</label><input id="cpw" type="password" autocomplete="current-password"></div>
    <div class="field"><label for="npw">${t('l_newpw')}</label><input id="npw" type="password" autocomplete="new-password" placeholder="${t('pw_hint')}"></div>
    <div class="btns"><button class="g" type="button" onclick="savePw()">${t('save_pw')}</button></div>
   </div></section>
  </div>`;
 loadTokensList();
 loadMonitorSettings();
}

async function setup2fa(){
 const {status,j}=await api('POST','api/2fa/setup',{});
 if(status!==200||!j){toast('error: '+((j&&j.error)||status));return;}
 modal(`<h3>${h(t('sec_2fa_title'))}</h3>
  <div class="row"><label>${h(t('sec_2fa_secret'))}</label><code class="mono" style="user-select:all">${h(j.secret||'')}</code></div>
  <div class="sub mono" style="word-break:break-all;margin:6px 0">${h(j.otpauth_uri||'')}</div>
  <div class="row"><label for="tfa_code">${h(t('sec_2fa_code'))}</label><input id="tfa_code" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="123456" autofocus></div>
  <div class="modal-actions">
   <button class="gh" type="button" onclick="closeModal()">${h(t('cancel'))}</button>
   <button class="g" type="button" onclick="enable2faSubmit()">${h(t('save'))}</button>
  </div>`);
}

async function enable2faSubmit(){
 const el=$('tfa_code');
 const code=el?(el.value||'').trim():'';
 const {status,j}=await api('POST','api/2fa/enable',{code});
 if(status!==200||!j){toast('error: '+((j&&j.error)||status));return;}
 const codes=(j.recovery_codes||[]).map(x=>'<code>'+h(x)+'</code>').join('');
 modal(`<h3>${h(t('sec_2fa_recovery'))}</h3>
  <p class="sub">${h(t('sec_2fa_recovery_note'))}</p>
  <div class="code-grid">${codes}</div>
  <div class="modal-actions"><button class="g" type="button" onclick="closeModal()">${h(t('close'))}</button></div>`);
 renderSettingsPage();
}

async function saveUpdateSettings(){
 const payload={
  update_channel:($('upd_chan')&&$('upd_chan').value)||'stable',
  update_relay_mode:($('upd_relay')&&$('upd_relay').value)||'auto',
  update_proxy:($('upd_proxy')&&$('upd_proxy').value||'').trim(),
  update_require_sig:!!($('upd_req_sig')&&$('upd_req_sig').checked),
 };
 const {status,j}=await api('POST','api/config',payload);
 if(status!==200){toast('error: '+((j&&j.error)||status));return;}
 toast(t('upd_saved'));
}

function disable2faModal(){
 formModal(t('sec_2fa_disable'),[
  {id:'password',label:t('l_curpw'),type:'password',req:1},
  {id:'code',label:t('sec_2fa_code'),type:'text',ph:t('totp_ph'),req:1}
 ],async v=>{
  const {status,j}=await api('POST','api/2fa/disable',{password:v.password,code:v.code});
  if(status!==200){toast('error: '+((j&&j.error)||status));return;}
  closeModal();
  renderSettingsPage();
 });
}

async function loadTokensList(){
 const {status,j}=await api('GET','api/tokens');
 const box=$('tok_list');
 if(!box)return;
 if(status!==200){box.innerHTML=`<div class="empty">${h((j&&j.error)||String(status))}</div>`;return;}
 const toks=(j&&Array.isArray(j.tokens))?j.tokens:[];
 if(!toks.length){box.innerHTML=`<div class="empty">${h(t('sec_no_tokens'))}</div>`;return;}
 box.innerHTML=toks.map(tok=>`<div class="sec-token-row">
  <div><strong>${h(tok.name||'')}</strong> <span class="badge b-info">${h(tok.scope||'read')}</span> <span class="mono sub">${h(tok.prefix||'')}…</span></div>
  <button class="s" type="button" data-tok-id="${h(tok.id||'')}">${h(t('sec_token_revoke'))}</button>
 </div>`).join('');
 box.querySelectorAll('[data-tok-id]').forEach(b=>{
  b.onclick=()=>revokeScopedToken(b.getAttribute('data-tok-id'));
 });
}

function createScopedTokenModal(){
 formModal(t('sec_token_create'),[
  {id:'name',label:t('sec_token_name'),type:'text',req:1},
  {id:'scope',label:t('sec_token_scope'),type:'select',val:'read',opts:[{v:'read',t:'read'},{v:'operate',t:'operate'},{v:'admin',t:'admin'}]}
 ],async v=>{
  const {status,j}=await api('POST','api/tokens',{name:v.name,scope:v.scope});
  if(status!==201){toast('error: '+((j&&j.error)||status));return;}
  closeModal();
  outModal(t('sec_token_create'),t('sec_token_created_note')+'\n\n'+((j&&j.token)||''));
  loadTokensList();
 });
}

async function revokeScopedToken(id){
 if(!id||!confirm(t('sec_token_revoke')+' '+id+'?'))return;
 const {status,j}=await api('DELETE','api/tokens/'+encodeURIComponent(id));
 if(status!==200){toast('error: '+((j&&j.error)||status));return;}
 loadTokensList();
}

async function loadMonitorSettings(){
 const {status,j}=await api('GET','api/monitor/config');
 const box=$('mon_card');
 if(!box)return;
 if(status!==200||!j){box.innerHTML=`<div class="empty">${h((j&&j.error)||String(status))}</div>`;return;}
 const d=j;
 const modeLbl={
  auto:LANG==='fa'?'auto (خودکار — از طریق نود خارج در ایران)':'auto (direct → foreign SSH relay)',
  ssh_auto:LANG==='fa'?'ssh_auto (همیشه از تونل SSH نود خارج)':'ssh_auto (always via foreign SSH node)',
  proxy:'proxy',
  direct:'direct'
 };
 const modes=['auto','direct','proxy','ssh_auto'];
 const opts=modes.map(m=>`<option value="${h(m)}"${d.relay_mode===m?' selected':''}>${h(modeLbl[m]||m)}</option>`).join('');
 const tokBadge=d.bot_token_set
  ?`<span class="badge b-ok">${h(t('mon_token_set'))}${d.bot_token_hint?' ('+h(d.bot_token_hint)+')':''}</span>`
  :`<span class="badge b-warn">${h(t('mon_token_unset'))}</span>`;
 const svcBadge=`<span class="badge ${d.service_active?'b-ok':'b-bad'}">${h(d.service_active?t('sec_2fa_on'):t('sec_2fa_off'))}</span>`;
 const unitBadge=d.service_installed===false?`<span class="badge b-warn">${LANG==='fa'?'یونیت سرویس هنگام فعال‌سازی نصب می‌شود':'unit installs on enable'}</span>`:'';
 box.innerHTML=`<div class="sub" style="margin-bottom:10px">${h(t('mon_desc'))}</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">${svcBadge} ${tokBadge} ${unitBadge}</div>
  <div class="settings-form" style="max-width:680px">
   <div class="field"><label><input id="mon_enabled" type="checkbox"${d.enabled?' checked':''}> ${h(t('sec_2fa_on'))}</label></div>
   <div class="field"><label for="mon_token">${h(t('mon_bot_token'))}</label><input id="mon_token" type="password" autocomplete="off" placeholder="${h(d.bot_token_hint||'123456:ABC...')}"></div>
   <div class="field"><label for="mon_chats">${h(t('mon_chat_ids'))}</label><input id="mon_chats" type="text" value="${h((d.allowed_chat_ids||[]).join(', '))}" placeholder="-100123456789, 987654321"></div>
   <div class="field"><label for="mon_relay">${h(t('mon_relay_mode'))}</label><select id="mon_relay">${opts}</select></div>
   <div class="field"><label for="mon_proxy">${h(t('mon_proxy'))}</label><input id="mon_proxy" type="text" value="${h(d.proxy||'')}" placeholder="socks5h://127.0.0.1:1080"></div>
   <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px">
    <div class="field"><label for="mon_poll">${h(t('mon_poll_sec'))}</label><input id="mon_poll" type="number" min="15" max="3600" value="${h(String(d.poll_interval_sec??60))}"></div>
    <div class="field"><label for="mon_fail">${h(t('mon_fail_thr'))}</label><input id="mon_fail" type="number" min="1" max="20" value="${h(String(d.fail_threshold??3))}"></div>
    <div class="field"><label for="mon_rec">${h(t('mon_recover_thr'))}</label><input id="mon_rec" type="number" min="1" max="20" value="${h(String(d.recover_threshold??2))}"></div>
    <div class="field"><label for="mon_cool">${h(t('mon_cooldown_sec'))}</label><input id="mon_cool" type="number" min="30" max="86400" value="${h(String(d.cooldown_sec??300))}"></div>
   </div>
   <div class="field"><label><input id="mon_actions" type="checkbox"${d.allow_remote_actions!==false?' checked':''}> ${h(t('mon_allow_actions'))}</label></div>
   <div class="btns" style="flex-wrap:wrap">
    <button class="g" type="button" onclick="saveMonitorConfig()">${h(t('mon_save'))}</button>
    <button class="s" type="button" onclick="diagnoseMonitorRelay()">${h(t('mon_diagnose'))}</button>
    <button class="gh" type="button" onclick="sendMonitorTest()">${h(t('mon_send_test'))}</button>
   </div>
  </div>`;
}

async function saveMonitorConfig(){
 const rawChats=($('mon_chats')&&$('mon_chats').value||'').trim();
 const parts=rawChats?rawChats.split(/[\s,]+/).filter(Boolean):[];
 const chatIds=[];
 for(const p of parts){
  if(!/^-?[0-9]{1,20}$/.test(p)||p==='0'){toast('error: invalid chat id '+p);return;}
  chatIds.push(Number(p));
 }
 const payload={
  enabled:!!($('mon_enabled')&&$('mon_enabled').checked),
  allowed_chat_ids:chatIds,
  relay_mode:($('mon_relay')&&$('mon_relay').value)||'auto',
  proxy:($('mon_proxy')&&$('mon_proxy').value||'').trim(),
  poll_interval_sec:Number(($('mon_poll')&&$('mon_poll').value)||60),
  fail_threshold:Number(($('mon_fail')&&$('mon_fail').value)||3),
  recover_threshold:Number(($('mon_rec')&&$('mon_rec').value)||2),
  cooldown_sec:Number(($('mon_cool')&&$('mon_cool').value)||300),
  allow_remote_actions:!!($('mon_actions')&&$('mon_actions').checked),
 };
 const tok=($('mon_token')&&$('mon_token').value||'').trim();
 if(tok)payload.bot_token=tok;
 const {status,j}=await api('POST','api/monitor/config',payload);
 if(status!==200){toast('error: '+((j&&j.error)||status));return;}
 if(j&&j.service_error)toast('⚠️ '+j.service_error);else toast(t('done'));
 loadMonitorSettings();
}

async function diagnoseMonitorRelay(){
 const px=($('mon_proxy')&&$('mon_proxy').value||'').trim();
 const body=px?{proxy:px}:{};
 const {status,j}=await api('POST','api/monitor/diagnose-relay',body);
 if(status!==200||!j){toast('error: '+((j&&j.error)||status));return;}
 const dir=j.direct||{};
 const prx=j.proxy||{};
 const lines=[
  'Recommended: '+(j.recommended_mode||'none')+(j.best_ssh_node?' (best node: '+j.best_ssh_node+')':''),
  j.summary||'',
  '',
  'Direct: '+(dir.ok?('OK ('+dir.latency_ms+' ms)'):('FAILED ('+(dir.error||'unreachable')+')')),
  'Proxy: '+(prx.configured?(prx.ok?('OK ('+prx.latency_ms+' ms)'):('FAILED ('+(prx.error||'unreachable')+')')):'not configured'),
  'SSH Nodes ('+((j.ssh_nodes||[]).length)+'):',
 ];
 for(const n of (j.ssh_nodes||[])){
  lines.push('  - '+n.name+' ('+n.host+'): '+(n.ok?('OK ('+n.latency_ms+' ms)'):('FAILED ('+(n.error||'error')+')')));
 }
 outModal(t('mon_diagnose'),lines.join('\n'));
}

async function sendMonitorTest(){
 const {status,j}=await api('POST','api/monitor/test',{});
 if(status!==200||!j||!j.ok){toast('error: '+((j&&j.error)||status));return;}
 toast(t('done')+' — '+(j.via||'direct')+(j.node?' ('+j.node+')':''));
}

function outModal(title,text){var id='om_'+Math.random().toString(36).slice(2);modal('<h3>'+h(title)+'</h3><pre id="'+id+'" style="max-height:52vh;overflow:auto;white-space:pre-wrap;user-select:text;-webkit-user-select:text">'+h(text)+'</pre><div class="row" style="margin-top:10px"><button class="g" onclick="copyText(\''+id+'\')">'+t('copy_out')+'</button> <button class="gh" onclick="closeModal()">'+t('close')+'</button></div>');}
async function run(n,a,args){toast(t('running')+' '+a+' '+t('on')+' '+n+' …');
 const {j}=await api('POST','api/servers/'+n+'/action',{action:a,args:args||{}});
 const rc=(j&&typeof j.rc==='number')?j.rc:null;
 const ok=(rc===0), bad=(rc!==null&&rc!==0);
 const verdict=ok?('✓ '+t('ok_rc')):(bad?('✗ '+t('fail_rc')+' (rc='+rc+')'):'');
 const body=((j.cmd?('$ '+j.cmd+'\n'):'')+((j.out||'')+(j.err?('\n'+j.err):''))).trim();
 const full=((verdict?verdict+(body?'\n\n':''):'')+body)||JSON.stringify(j);
 if(bad){outModal(a+' ✗',full);}                                    // shekast: hamishe modal, ta gom nashavad
 else if(body&&(body.length>140||body.indexOf(String.fromCharCode(10))>=0)){outModal(a+' ✓',full);}
 else{toast(verdict+(body?(' — '+body):''));}
 if(!bad)await loadOv(n);}
async function doDeploy(n){if(!confirm(t('cf_deploy')+' '+n+' ?'))return; run(n,'deploy');}
// ---------- jam-avari-ye log: khorooji-ye tolani → modal + dokme-ye download ----------
// az run() joda ast chon (1) momken ast dah-ha kilobyte bashad va nabayad be toast beravad،
// (2) loadOv() lazem nist (chizi taghir nakarde)، (3) zakhire dar file baraye ferestadan.
// token-ha samt-e SERVER redact mishavand (rth_redact dar common.sh) — inja khaam nemiayad.
async function doLogs(n){
 toast(t('collecting_logs')+' '+n+' … ');
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'logs',args:{lines:'200'}});
 const body=((j.out||'')+(j.err?('\n'+j.err):'')).trim()||JSON.stringify(j);
 if(j&&j.rc===124){outModal('logs ✗','timeout — server javab nadad (dastoor samt-e server ba timeout baste shod).');return;}
 const id='lg_'+Math.random().toString(36).slice(2);
 modal('<h3>logs — '+h(n)+'</h3><pre id="'+id+'" style="max-height:52vh;overflow:auto;white-space:pre-wrap;user-select:text;-webkit-user-select:text">'+h(body)+'</pre>'
  +'<div class="row" style="margin-top:10px"><button class="g" onclick="copyText(\''+id+'\')">'+t('copy_out')+'</button> '
  +'<button class="s" onclick="dlLogs(\''+h(n)+'\',\''+id+'\')">'+t('download')+'</button> '
  +'<button class="gh" onclick="closeModal()">'+t('close')+'</button></div>');
}
function dlLogs(n,id){
 const el=document.getElementById(id); if(!el)return;
 const b=new Blob([el.textContent],{type:'text/plain'});
 const u=URL.createObjectURL(b), a=document.createElement('a');
 a.href=u; a.download='rathole-logs-'+n+'-'+new Date().toISOString().slice(0,19).replace(/[:T]/g,'')+'.txt';
 document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(u),1000);
}
// apdit-e hamegani: hameye serverha ra YEKI-YEKI (tartibi) apdit mikonad va progress bar +
// vaziat-e har server ra live neshan midahad. deploy = install.sh --update (snapshot+rollback-e khodkar).
let UPD_BUSY=false;
async function updateAll(){
 if(UPD_BUSY)return;
 const list=SERVERS.slice();
 if(!list.length){toast(t('no_servers'));return;}
 if(!confirm(t('cf_upd_all')+' ('+list.length+')'))return;
 UPD_BUSY=true; const btn=$('updall'); if(btn){btn.disabled=true;}
 const panel=$('updpanel'); const total=list.length; let done=0, okc=0, failc=0;
 const rows=list.map(s=>`<div class="updrow" id="ur_${h(s.name)}"><span class="dot d-un"></span><b>${h(s.name)}</b> <span class="badge b-role">${h(s.role)}</span><span class="us" id="us_${h(s.name)}">${t('upd_wait')}</span></div>`).join('');
 if(panel)panel.innerHTML=`<div class="card"><div class="cbody">
   <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><b>${t('upd_all')}</b>
     <div class="pbar"><div class="pfill" id="pfill" style="width:0%"></div></div>
     <span id="pcnt" class="mono">0/${total}</span>
     <button class="gh" onclick="closeUpdPanel()" id="updclose" disabled>${t('close')}</button></div>
   ${rows}</div></div>`;
 for(const s of list){
  const us=$('us_'+s.name), dot=document.querySelector('#ur_'+CSS.escape(s.name)+' .dot');
  if(us)us.textContent=' — '+t('upd_running'); if(dot)dot.className='dot d-un';
  try{
   const {j}=await api('POST','api/servers/'+s.name+'/action',{action:'deploy',args:{}});
   const rc=(j&&typeof j.rc==='number')?j.rc:1;
   if(rc===0){okc++; if(dot)dot.className='dot d-ok';
     // baad az apdit noskhe-ye jadid ra bekhan
     await loadOv(s.name); const nv=((OVS[s.name]||{}).version||{}).manager||'?';
     if(us)us.textContent=' — ✓ '+t('upd_ok')+' (v'+nv+')';
   }else{failc++; if(dot)dot.className='dot d-bad';
     if(us)us.textContent=' — ✗ '+t('upd_fail')+' (rc='+rc+')';}
  }catch(e){failc++; if(dot)dot.className='dot d-bad'; if(us)us.textContent=' — ✗ '+t('upd_fail');}
  done++; const pct=Math.round(done*100/total);
  const pf=$('pfill'); if(pf)pf.style.width=pct+'%'; const pc=$('pcnt'); if(pc)pc.textContent=done+'/'+total;
 }
 UPD_BUSY=false; if(btn)btn.disabled=false;
 const cb=$('updclose'); if(cb)cb.disabled=false;
 toast(t('upd_done')+': ✓'+okc+' ✗'+failc);
 loadHubStatus();
}
function closeUpdPanel(){const p=$('updpanel'); if(p&&!UPD_BUSY)p.innerHTML='';}
async function showDetails(n){toast(t('loading_det'));
 const {j}=await api('GET','api/servers/'+n+'/details');
 outModal('details · '+n, j.text||JSON.stringify(j));}
// ---------- dashboard-e vaziat (mesl-e panel-e VPN): status --json ra ziba render mikonad ----------
function stDot(v){return '<span class="dot '+(v==='yes'?'d-ok':'d-bad')+'"></span>';}
async function statusModal(n){toast(t('loading'));
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'status',args:{}});
 let d=null; try{d=JSON.parse(j&&j.out||'');}catch(e){}
 if(!d){outModal('status · '+n,((j&&j.cmd?'$ '+j.cmd+'\n':'')+((j&&j.out)||'')+((j&&j.err)?'\n'+j.err:'')).trim()||t('status_err'));return;}
 const P=d.ports||{}, C=d.cert||{}, S=d.services||{};
 const portRow=(port,lbl)=>port?`<tr><td class="mono">${h(String(port))}</td><td>${h(lbl)}</td></tr>`:'';
 const certLine=C.exists==='yes'
   ?`${stDot('yes')} ${t('st_cert_ok')} — ${h(C.expiry||'?')}`+(C.self_signed==='yes'?` <span class="badge" style="background:#7f1d1d">${t('st_selfsigned')}</span>`:'')
   :`${stDot('no')} <span style="color:#f87171">${t('st_cert_missing')}: ${h(C.fullchain||'')}</span>`;
 let nodes='';
 (d.nodes||[]).forEach(x=>{const sni=(x.sni&&x.sni!=='-');
   const url=sni?('SNI: '+h(x.sni)):('https://'+h(d.domain||'')+'/'+h(x.name));
   nodes+=`<tr><td class="mono">${h(x.name)}</td><td class="mono">${h(String(x.port))}</td><td class="mono">${h(String(x.inbound_port))}</td><td class="mono" style="font-size:12px">${url}</td></tr>`;});
 if(!nodes)nodes=`<tr><td colspan="4" class="sub">${t('st_no_nodes')}</td></tr>`;
 modal(`<h3>${t('status_btn')} · ${h(n)}</h3>
  <div class="row"><label>${t('st_domain')}</label><span class="mono">${h(d.domain||'—')}</span></div>
  <div class="row"><label>${t('st_ip')}</label><span class="mono">${h(d.public_ip||'?')}</span></div>
  <div class="row"><label>${t('st_transport')}</label><span class="mono">${h(d.transport||'')}</span></div>
  <h4 style="margin:12px 0 4px">${t('st_services')}</h4>
  <div class="mono">${stDot(S.rathole_server)} rathole-server &nbsp; ${stDot(S.nginx)} nginx (${S.nginx_config_ok==='yes'?t('st_ok'):'<span style=color:#f87171>'+t('st_bad')+'</span>'})${S.noise&&S.noise!=='off'?' &nbsp; '+stDot(S.noise)+' noise':''}</div>
  <h4 style="margin:12px 0 4px">${t('st_ports')}</h4>
  <table><tr><th>PORT</th><th></th></tr>
   ${portRow(443,'443 — '+t('st_p_443'))}
   ${portRow(P.control,t('st_p_control'))}
   ${portRow(P.fake,t('st_p_fake'))}
   ${portRow(P.sub,t('st_p_sub'))}
   ${d.sni_count>0?portRow(P.internal,t('st_p_internal')):''}
   ${portRow(P.plain,t('st_p_plain'))}
   ${portRow(P.direct,t('st_p_direct')+' ('+h(d.direct_header||'')+')')}
   ${portRow(P.hub,t('st_p_hub'))}
   ${portRow(P.noise,t('st_p_noise'))}
  </table>
  <h4 style="margin:12px 0 4px">${t('st_cert')}</h4>
  <div class="mono" style="font-size:13px">${certLine}</div>
  <h4 style="margin:12px 0 4px">${t('st_nodes')} (${(d.nodes||[]).length})</h4>
  <table><tr><th>NAME</th><th>PORT</th><th>INBOUND</th><th>USER URL</th></tr>${nodes}</table>
  <div class="row" style="margin-top:12px"><button class="gh" onclick="closeModal()">${t('close')}</button></div>`);}
function copyText(id){const el=$(id);if(!el)return;const x=el.textContent;
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(x).then(()=>toast(t('rc_copied')),()=>toast('copy?'));}
 else{const r=document.createRange();r.selectNode(el);getSelection().removeAllRanges();getSelection().addRange(r);try{document.execCommand('copy');toast(t('rc_copied'));}catch(e){toast('copy?');}}}
function requireInputs(ids){let first=null;ids.forEach(id=>{const el=$(id),bad=!el||!(el.value||'').trim();if(el)el.setAttribute('aria-invalid',bad?'true':'false');if(bad&&!first)first=el;});if(first){toast(t('fill'));first.focus();return false;}return true;}
async function addSrv(){
 const tr=$('conn_tr')?.value||'ssh';
 const px=($('srv_px')?.value||'').trim();
 let b={name:$('n').value.trim(),role:$('rl').value,transport:tr};
 if(px)b.proxy=px;
 if(tr==='api'){
  if(!requireInputs(['n','api_u','api_tok']))return;
  let u = $('api_u').value.trim();
  if(!/^https?:\/\//i.test(u)) u = 'http://' + u;
  b.api_url=u;
  b.api_token=$('api_tok').value.trim();
 } else {
  if(!requireInputs(['n','hh','uu','pp']))return;
  b.host=$('hh').value.trim();
  b.ssh_user=$('uu').value.trim();
  b.ssh_port=$('pp').value.trim();
 }
 const {status,j}=await api('POST','api/servers',b);
 if(status!==200){toast('error: '+(j.error||status));return;}
 $('n').value=''; if($('hh'))$('hh').value=''; if($('api_u'))$('api_u').value=''; if($('api_tok'))$('api_tok').value=''; if($('srv_px'))$('srv_px').value='';
 loadAll();
}
async function provSrv(){if(!requireInputs(['n','hh','uu','pp','sw']))return;const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value,ssh_password:$('sw').value,iran_server:($('isv')?$('isv').value:'')};
 toast(t('provisioning'));
 const {status,j}=await api('POST','api/provision',b);
 const out=((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):'');
 outModal(t('prov_btn')+' · '+b.name, out.trim()||JSON.stringify(j));
 if(status===200){$('n').value='';$('hh').value='';$('sw').value='';loadAll();}}

// ---------- form-based actions (bedoon prompt zanjire-i) ----------
// afzoodan-e node-e game (SNI): agar in AVALIN node-e SNI bashad، port 443 az L7 be
// nginx stream/L4 (ssl_preread) switch mishavad va vhost-e L7 (sait-e fik + control-e
// rathole + backhaul) be port-e dakheli montaghel mishavad. yani hameye node-haye aadi
// az masir-e jadid obor mikonand — SNI-e eshtebah = ghat-e hame. pas ghabl az an bepors.
function gameAdd(n){
 const ov=OVS[n]||{};
 const first=!((ov.game||[]).length);
 const normal=((ov.nodes||[]).length)||0;
 if(first && !confirm(t('cf_game_l4').replace('%n',String(normal)))) return;
 formModal(t('t_game_add'),[
  {id:'name',label:t('f_name'),ph:'gmtrk',req:1},
  {id:'inbound',label:t('l_inb_tls'),val:'8444',req:1},
  {id:'sni',label:t('l_sni'),ph:'gmtrk.l1t.ir',req:1}],
  v=>{closeModal();run(n,'game_add',v);});}
function gameCert(n){formModal(t('t_game_cert'),[
  {id:'sni',label:t('l_sni_cert'),req:1}],
  v=>{closeModal();run(n,'game_cert',v);});}

function domainTls(n){
 modal(`<h3>${t('domain_tls')} (${h(n)})</h3>
 <div id="dt_list"><div class="empty">${t('loading')}</div></div>
 <div id="dt_domains"></div>
 <div class="row"><label>${t('dt_add')}</label><input id="dt_nd" placeholder="dom2.example.ir" style="min-width:140px"><input id="dt_nfc" placeholder="fullchain (optional)"><input id="dt_nkey" placeholder="privkey (optional)"><button class="g" onclick="dtAddDomain('${h(n)}')">${t('dt_add_btn')}</button></div>
 <div class="row"><button class="s" onclick="run('${h(n)}','tls_info');closeModal();">${t('dt_show')}</button>
   <span class="sub">${t('dt_hint')}</span></div>
 <div class="row"><label>${t('dt_domain')}</label><input id="dt_dom" placeholder="btli.ir">
   <button class="g" onclick="dtSet('${h(n)}','domain','dt_dom')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_fc')}</label><input id="dt_fc" placeholder="/root/cert/x/fullchain.pem">
   <button class="g" onclick="dtSet('${h(n)}','fullchain','dt_fc')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_key')}</label><input id="dt_key" placeholder="/root/cert/x/privkey.pem">
   <button class="g" onclick="dtSet('${h(n)}','key','dt_key')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_le')}</label><input id="dt_ledom" placeholder="dom.example.ir">
   <input id="dt_leem" placeholder="email (optional)">
   <button class="g" onclick="dtCert('${h(n)}')">${t('dt_get')}</button></div>
 <h3 style="margin-top:14px">${t('ports_sec')}</h3>
 <div class="sub" style="margin-bottom:6px">${h(t('ports_hint'))}</div>
 <div id="dt_ports"><div class="empty">${t('loading')}</div></div>
 <div class="row" style="justify-content:flex-end;margin-top:10px">
   <button class="s" onclick="run('${h(n)}','regen_full');closeModal();">${t('dt_apply')}</button>
   <button class="gh" onclick="closeModal()">${t('close')}</button></div>`);dtRefresh(n);}

async function dtLoadList(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'tls_certs',args:{}});
 const box=$('dt_list'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|EXPIRY|ACTIVE|SNI');
 if(!rows.length){box.innerHTML=`<div class="empty">${t('dt_none')}</div>`;return;}
 let h2=`<div class="sub" style="margin:4px 0">${t('dt_list')}</div>`;
 h2+=`<table><tr><th>${t('dt_domain')}</th><th>${t('dt_expiry')}</th><th>${t('dt_active')}</th><th>SNI</th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||''),exp=h(p[1]||''),act=(p[2]||'')==='yes',sni=(p[3]||'')==='yes';
  h2+=`<tr><td>${dom}</td><td>${exp}</td><td>${act?('<span class="badge b-ok">'+t('dt_active')+'</span>'):''}</td><td>${sni?'SNI':''}</td></tr>`;});
 h2+='</table>';
 box.innerHTML=h2;
}
function parseTable(txt,header){const cols=header.split('|').length;const lines=(txt||'').split('\n').map(x=>x.trim());let hi=-1;for(let i=0;i<lines.length;i++){if(lines[i].toUpperCase().indexOf(header.toUpperCase())===0){hi=i;break;}}const start=hi>=0?hi+1:0;const dom=/^[A-Za-z0-9_*-]+(\.[A-Za-z0-9_*-]+)+$/;const out=[];for(let i=start;i<lines.length;i++){const l=lines[i];if(l.indexOf('|')<0)continue;const p=l.split('|');if(p.length<cols)continue;if(!dom.test((p[0]||'').trim()))continue;out.push(p);}return out;}
function dtRefresh(n){dtLoadDomains(n);dtLoadList(n);dtLoadPorts(n);}

// ---------- port-ha ----------
// se port ba `ratholectl set` avaz mishavand؛ baghi motealegh be halat-e khodeshan hastand
// (masalan plain/noise/backhaul port ra moghe-e roshan kardan migirand) va faghat neshan
// dade mishavand ta karbar tasvir-e kamel az port-ha dashte bashad.
const PORT_EDITABLE=[
 {key:'fake-port',    path:'fake',     ph:'8080'},
 {key:'sub-port',     path:'sub',      ph:'2096'},
 {key:'control-port', path:'control',  ph:'2333'},
];
const PATH_EDITABLE=[
 {key:'sub-path', path:'sub', ph:'sub'},
 {key:'hub-path', path:'hub', ph:'hub'},
];
const PORT_READONLY=[
 {path:'internal', k:'p_internal'},
 {path:'hub',      k:'p_hub'},
 {path:'plain',    k:'p_plain'},
 {path:'noise',    k:'p_noise'},
 {path:'backhaul', k:'p_backhaul'},
 {path:'direct',   k:'p_direct'},
];

function portsModal(n){
 modal(`<h3>${t('ports_sec')} (${h(n)})</h3>
 <div class="sub" style="margin-bottom:6px">${h(t('ports_hint'))}</div>
 <div id="pt_ports"><div class="empty">${t('loading')}</div></div>
 <div class="row" style="justify-content:flex-end;margin-top:10px">
   <button class="s" onclick="run('${h(n)}','regen_full');closeModal();">${t('dt_apply')}</button>
   <button class="gh" onclick="closeModal()">${t('close')}</button></div>`);
 dtLoadPorts(n);
}

async function dtLoadPorts(n){
 const box=$('pt_ports')||$('dt_ports'); if(!box)return;
 // agar cache khali bud, avval refresh kon ta port-ha neshan dade shavand
 if(!OVS[n]||!OVS[n].status||!OVS[n].status.ports){
   box.innerHTML=`<div class="empty">${t('loading')}...</div>`;
   await loadOv(n);
 }
 const ov=OVS[n]||{}; const ports=(ov.status&&ov.status.ports)||{};
 const paths=(ov.status&&ov.status.paths)||{};
 let x='';
 PORT_EDITABLE.forEach(p=>{
  const cur=ports[p.path];
  x+=`<div class="row"><label>${h(t('p_'+p.path))}</label>`
   + `<input id="pt_${p.path}" value="${cur==null?'':h(String(cur))}" placeholder="${p.ph}" style="max-width:110px">`
   + `<button class="g" onclick="dtSetPort('${n}','${p.key}','pt_${p.path}')">${t('save')}</button></div>`;
 });
 // masir-ha (path segment): sub/hub — yek kalame sade bedoon slash
 x+=`<div class="sub" style="margin:10px 0 4px">${h(t('paths_sec'))}</div>`;
 PATH_EDITABLE.forEach(p=>{
  const cur=paths[p.path]||p.ph;
  x+=`<div class="row"><label>${h(t('pth_'+p.path))}</label>`
   + `<span class="sub mono" style="align-self:center">/</span>`
   + `<input id="pth_${p.path}" value="${h(String(cur))}" placeholder="${p.ph}" style="max-width:140px">`
   + `<button class="g" onclick="dtSetPath('${n}','${p.key}','pth_${p.path}')">${t('save')}</button></div>`;
 });
 const ro=PORT_READONLY.filter(p=>ports[p.path]!=null)
   .map(p=>`${h(t(p.k))}: <b>${h(String(ports[p.path]))}</b>`).join(' · ');
 x+=`<div class="sub" style="margin-top:6px">${ro||t('ports_none')}</div>`;
 box.innerHTML=x;
}

// masir-ha faghat yek segment-e sade (harf/adad/_/-) — slash dar ratholectl ham rad mishavad.
function dtSetPath(n,key,id){
 const el=$(id); if(!el)return;
 const v=(el.value||'').trim().replace(/^\/+|\/+$/g,'');
 if(!/^[A-Za-z0-9_-]{1,40}$/.test(v)){toast(t('pth_bad'));return;}
 closeModal();
 run(n,'set_config',{key,value:v});
}

// ghabl az ersal tadakhol-e port ra check mikonim — nginx/rathole ba do sherkat rooye yek
// port bala nemiayand va peyda kardanash az log sakht ast.
function dtSetPort(n,key,id){
 const el=$(id); if(!el)return;
 const v=(el.value||'').trim();
 if(!/^[0-9]{1,5}$/.test(v)||+v<1||+v>65535){toast(t('p_bad'));return;}
 const ov=OVS[n]||{}; const ports=(ov.status&&ov.status.ports)||{};
 const mine=({'fake-port':'fake','sub-port':'sub','control-port':'control'})[key];
 const clash=Object.keys(ports).find(k=>k!==mine&&ports[k]!=null&&String(ports[k])===v);
 if(clash&&!confirm(t('p_clash').replace('%s',clash).replace('%p',v)))return;
 if(v==='443'&&!confirm(t('p_443')))return;
 closeModal();
 run(n,'set_config',{key,value:v});
}
async function dtApi(n,action,args){const {j}=await api('POST','api/servers/'+n+'/action',{action,args:args||{}});
 const out=((j&&j.cmd?('$ '+j.cmd+'\n'):'')+(((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):''))).trim();if(out)toast(out);loadOv(n);return j;}
async function dtLoadDomains(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'domain_ls',args:{}});
 const box=$('dt_domains'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|FULLCHAIN|KEY|PRIMARY');
 if(!rows.length){box.innerHTML='';return;}
 let x=`<div class="sub" style="margin:4px 0">${t('dt_served')}</div><table><tr><th>${t('dt_domain')}</th><th>${t('dt_kind')}</th><th></th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||'');const prim=(p[3]||'')==='yes';
  x+=`<tr><td>${dom}</td><td>${prim?('<span class="badge b-role">'+t('dt_primary')+'</span>'):('<span class="badge b-kcp">'+t('dt_extra')+'</span>')}</td><td>${prim?'':('<button class="g" type="button" data-dt-act="primary" data-dt-srv="'+h(n)+'" data-dt-dom="'+dom+'">'+t('dt_makeprimary')+'</button> '+'<button class="r" type="button" data-dt-act="rm" data-dt-srv="'+h(n)+'" data-dt-dom="'+dom+'">'+t('remove')+'</button>')}</td></tr>`;});
 x+='</table>'; box.innerHTML=x;
 box.onclick=e=>{const b=e.target&&e.target.closest('button[data-dt-act]');if(!b)return;const srv=b.dataset.dtSrv,dom=b.dataset.dtDom;if(b.dataset.dtAct==='primary')dtMakePrimary(srv,dom);else if(b.dataset.dtAct==='rm')dtRmDomain(srv,dom);};
}
async function dtAddDomain(n){const d=($('dt_nd').value||'').trim();if(!d){toast(t('fill'));return;}
 const fc=($('dt_nfc').value||'').trim(),key=($('dt_nkey').value||'').trim();
 const a={domain:d}; if(fc&&key){a.fullchain=fc;a.key=key;}else{a.certbot=1;}
 await dtApi(n,'domain_add',a); domainTls(n);}
async function dtRmDomain(n,d){if(!confirm(t('remove')+' '+d+' ?'))return; await dtApi(n,'domain_rm',{domain:d}); domainTls(n);}
async function dtMakePrimary(n,d){if(!confirm(t('dt_mp_confirm')+' '+d+' ?'))return; await dtApi(n,'domain_primary',{domain:d}); domainTls(n);}

function dtSet(n,key,id){const v=($(id).value||'').trim();if(!v){toast(t('fill'));return;}closeModal();run(n,'set_config',{key,value:v});}
function dtCert(n){const d=($('dt_ledom').value||'').trim();if(!d){toast(t('fill'));return;}
 const e=($('dt_leem').value||'').trim();const a={domain:d};if(e)a.email=e;closeModal();run(n,'tls_cert',a);}

function addNode(n){formModal(t('t_add_node'),[
  {id:'name',label:t('l_node_name'),req:1},
  {id:'inbound',label:t('l_xray_inb'),req:1},
  {id:'api_port',label:t('l_api_opt')}],
  v=>{closeModal();const a={name:v.name,inbound:v.inbound};if(v.api_port)a.api_port=v.api_port;run(n,'add_node',a);});}
function rmNode(n,name){if(confirm(t('cf_delnode')+' ('+name+')'))run(n,'rm_node',{name});}
function applyNodePreset(n,preset){
  const cur=nodeCarrier(OVS[n]||{});
  if(preset===cur){toast(t('saved'));return;}
  setCarrier(n,preset,cur);
}
function addUnifiedSvc(n){
  const cur=nodeCarrier(OVS[n]||{});
  const curLabel=t('carrier_'+cur)||cur.toUpperCase();
  formModal(t('t_add_svc'),[
  {id:'name',label:t('f_name'),req:1},
  {id:'lane',label:t('l_lane'),type:'select',val:'standard',opts:[
    {v:'standard',t:`${t('lane_standard')} (${curLabel})`},
    {v:'mux',t:t('lane_mux')}
  ]},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1},
  {id:'remote_port',label:'پورت بک‌اند ایران (برای FRP)',ph:'مثلاً 21001'}],
  v=>{
    closeModal();
    if(v.lane==='mux')run(n,'add_bh_svc',{name:v.name,token:v.token,inbound:v.inbound});
    else run(n,'add_svc',{name:v.name,token:v.token,inbound:v.inbound,remote_port:v.remote_port});
  });}
function rmSvc(n,name){if(confirm(t('cf_delsvc')+' ('+name+')'))run(n,'rm_svc',{name});}
function rmBhSvc(n,name){if(confirm(t('cf_delsvc')+' ('+name+')'))run(n,'rm_bh_svc',{name});}
function upAdd(n){formModal(t('t_up_add'),[
  {id:'id',label:t('l_up_id'),ph:'iran2',req:1},
  {id:'server',label:t('l_up_srv'),ph:'rp02.example.ir:443',req:1}],
  v=>{closeModal();run(n,'upstream_add',v);});}
function upAddSvc(n,id){formModal(t('t_up_addsvc')+' ('+id+')',[
  {id:'name',label:t('f_name'),req:1},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1}],
  v=>{closeModal();run(n,'upstream_add_svc',{id,name:v.name,token:v.token,inbound:v.inbound});});}
function upRm(n,id){if(confirm(t('cf_delup')+' ('+id+') ?'))run(n,'upstream_rm',{id});}
function upRmSvc(n,id,name){if(confirm(t('cf_delupsvc')+' ('+id+'/'+name+') ?'))run(n,'upstream_rm_svc',{id,name});}
function fakewebStart(n){formModal(t('t_fw'),[

  {id:'port',label:t('l_fw_port')}],
  v=>{closeModal();run(n,'fakeweb_start',v.port?{port:v.port}:{});});}
function wdOn(n){formModal(t('t_wd'),[
  {id:'interval',label:t('l_wd_iv'),val:'60',req:1}],
  v=>{closeModal();run(n,'watchdog_on',{interval:v.interval||'60'});});}
function adaptiveOnNode(n){
 formModal(t('t_adaptive_node'),[
  {id:'interval',label:t('l_adaptive_iv'),val:'30',req:1},
  {id:'failures',label:t('l_adaptive_fa'),val:'3',req:1},
  {id:'recoveries',label:t('l_adaptive_re'),val:'5',req:1},
  {id:'chain',label:t('l_adaptive_chain'),val:'ws,kcp',ph:'ws,noise,kcp,frp'},
  {id:'probe_candidates',label:t('l_adaptive_probe_cands'),type:'select',val:'0',opts:[{v:'0',t:'Off'},{v:'1',t:'On'}]}
 ],v=>{
  closeModal();
  const args={interval:v.interval||'30',failures:v.failures||'3',recoveries:v.recoveries||'5'};
  if(v.chain)args.chain=v.chain;
  if(v.probe_candidates==='1')args.probe_candidates='1';
  run(n,'adaptive_on',args);
 });
}

async function openEndpointsModal(n){
 const {status,j}=await api('POST','api/servers/'+encodeURIComponent(n)+'/action',{action:'endpoints_ls',args:{}});
 if(status!==200||!j||j.rc!==0){toast('error: '+((j&&(j.err||j.error))||status));return;}
 let d={};
 try{d=JSON.parse(j.out||'{}')||{};}catch(_e){d={};}
 const active=String(d.active||'');
 const primary=String(d.primary||'');
 const backups=Array.isArray(d.backups)?d.backups:[];
 const scores=(d.scores&&typeof d.scores==='object')?d.scores:{};
 const list=[];
 [active,primary,...backups].forEach(x=>{if(x&&!list.includes(x))list.push(x);});
 const rows=list.map(addr=>{
  const sc=scores[addr]||{};
  const okCls=sc.last_ok===false?'b-bad':'b-ok';
  const scoreTxt=sc.score!=null?(String(sc.score)+(sc.last_ms!=null?' · '+String(sc.last_ms)+'ms':'')):'-';
  const tags=[addr===active?'active':'',addr===primary?'primary':''].filter(Boolean).join(', ');
  const swBtn=addr!==active?`<button class="s" type="button" data-ep-act="switch" data-ep-addr="${h(addr)}">${h(t('ep_switch'))}</button>`:'';
  const rmBtn=backups.includes(addr)?`<button class="gh" type="button" data-ep-act="rm" data-ep-addr="${h(addr)}">${h(t('remove'))}</button>`:'';
  return `<div class="sec-token-row"><div><span class="mono">${h(addr)}</span>${tags?' <span class="badge b-info">'+h(tags)+'</span>':''} <span class="badge ${okCls}">${h(t('ep_score'))}: ${h(scoreTxt)}</span></div><div class="btns">${swBtn}${rmBtn}</div></div>`;
 }).join('')||`<div class="empty">-</div>`;
 modal(`<div id="ep_box"><h3>${h(t('ep_title'))} · ${h(n)}</h3><div class="btns" style="margin-bottom:10px"><button class="g" type="button" data-ep-act="add">${h(t('ep_add'))}</button><button class="s" type="button" data-ep-act="test">${h(t('ep_test'))}</button></div>${rows}<div class="modal-actions"><button class="gh" type="button" onclick="closeModal()">${h(t('close'))}</button></div></div>`);
 const box=$('ep_box');
 if(!box)return;
 box.querySelectorAll('[data-ep-act]').forEach(btn=>{
  btn.onclick=()=>{
   const act=btn.getAttribute('data-ep-act');
   const addr=btn.getAttribute('data-ep-addr')||'';
   if(act==='add')addEndpointModal(n);
   else if(act==='test')testEndpointsAction(n);
   else if(act==='switch')switchEndpointAction(n,addr);
   else if(act==='rm')removeEndpointAction(n,addr);
  };
 });
}

function addEndpointModal(n){
 formModal(t('ep_add'),[{id:'addr',label:t('ep_addr'),ph:'5.202.4.41:443',req:1}],async v=>{
  closeModal();
  await run(n,'endpoints_add',{addr:v.addr});
  openEndpointsModal(n);
 });
}

async function testEndpointsAction(n){
 await run(n,'endpoints_test',{});
 openEndpointsModal(n);
}

async function switchEndpointAction(n,addr){
 if(!addr)return;
 await run(n,'endpoints_switch',{addr});
 openEndpointsModal(n);
}

async function removeEndpointAction(n,addr){
 if(!addr)return;
 await run(n,'endpoints_rm',{addr});
 openEndpointsModal(n);
}
function kcpOnIran(n){formModal(t('t_kcp_iran'),[
  {id:'port',label:t('l_udp'),val:'443',req:1},
  {id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF}],
  v=>{closeModal();run(n,'kcp_on',{port:v.port,profile:v.profile||'balanced'});});}
function plainOnIran(n){formModal(t('t_plain_iran'),[
  {id:'port',label:t('l_plain_port'),val:'8880',req:1}],
  v=>{closeModal();run(n,'plain_on',{port:v.port});});}
function directOnIran(n){formModal(t('t_direct_iran'),[
  {id:'port',label:t('l_direct_port'),val:'8081',req:1},
  {id:'header',label:t('l_direct_header'),val:'X-Cdn-Id',req:1}],
  v=>{closeModal();run(n,'direct_on',{port:v.port,header:v.header});});}
function noiseOnIran(n){formModal(t('t_noise_iran'),[
  {id:'port',label:t('l_noise_port'),val:'2334',req:1}],
  v=>{closeModal();run(n,'noise_on',{port:v.port});});}
function noiseNode(n,act){formModal(t(act==='on'?'noise_node_on':'noise_node_off'),[
  {id:'name',label:t('c_name'),req:1}],
  v=>{closeModal();quickCarrierModal(n,v.name,act==='on'?'noise':'ws');});}
async function disableIranCarrier(n,carrier){
  await loadOv(n);
  if (!OVS[n] || OVS[n].reachable === false || !Array.isArray(OVS[n].nodes)) {
    toast('⚠️ وضعیت نودهای ایران قابل خواندن نیست؛ خاموش‌کردن حامل انجام نشد.');
    return;
  }
  const using=OVS[n].nodes.filter(x=>x.transport===carrier).map(x=>x.name);
  if(using.length){
    toast(`⚠️ ابتدا حامل نودهای ${using.join(', ')} را از ردیف همان سرویس تغییر دهید؛ ${carrier.toUpperCase()} هنوز استفاده می‌شود.`);
    return;
  }
  await run(n,carrier+'_off');
}
// autofill-e noise: az server Iran remote+pubkey ra migirad
async function noiseAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/noiseconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_pubkey'))$('f_pubkey').value=j.pubkey||'';
 if($('f_pattern')&&j.pattern)$('f_pattern').value=j.pattern;
 toast(t('autofilled'));
}
function noiseNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_noise_remote'),ph:'5.202.4.40:2334',req:1});
 f.push({id:'pubkey',label:t('l_noise_key'),req:1});
 f.push({id:'pattern',label:t('l_noise_pattern'),val:'Noise_NK_25519_ChaChaPoly_BLAKE2s'});
 return f;
}

// ---- backhaul (core-e SMUX posht-e nginx/443) ----
// samt-e Iran transport-e BEDOON-e TLS migirad (nginx TLS ra terminate mikonad),
// samt-e node transport-e TLS-dar — in do amdan yeki nistand.
const BH_SRV_TR=[{v:'wsmux',t:'wsmux (mux)'},{v:'ws',t:'ws (bedoon mux)'}];
const BH_CLI_TR=[{v:'wssmux',t:'wssmux (mux)'},{v:'wss',t:'wss (bedoon mux)'}];
const BH_DIRECT_TR=[{v:'wsmux',t:'wsmux (direct, no TLS)'},{v:'ws',t:'ws (direct, no TLS)'}];
function bhOnIran(n){formModal(t('t_bh_iran'),[
  {id:'mode',label:t('l_bh_mode'),type:'select',val:'nginx_tls',opts:[{v:'nginx_tls',t:'nginx TLS/443 (recommended)'},{v:'direct_ip',t:'direct IP (no TLS)'}]},
  {id:'port',label:t('l_bh_port'),val:'3080',req:1},
  {id:'transport',label:t('l_bh_tr_srv'),type:'select',val:'wsmux',opts:BH_SRV_TR},
  {id:'profile',label:t('l_bh_prof'),type:'select',val:'balanced',opts:PROF}],
  v=>{if(v.mode==='direct_ip'&&!confirm(t('bh_direct_warn')))return;closeModal();run(n,'backhaul_on',{port:v.port,transport:v.transport||'wsmux',profile:v.profile||'balanced',mode:v.mode||'nginx_tls'});});}
function bhNode(n,act){formModal(t(act==='on'?'bh_node_on':'bh_node_off'),[
  {id:'name',label:t('c_name'),req:1}],
  v=>{closeModal();quickCarrierModal(n,v.name,act==='on'?'backhaul':'ws');});}
// ============ reverse-proxy-e gheyre-tunnel ============
// /<name>/ rooye haman 443 be yek upstream-e delkhah. esm ba node-ha moshtarak ast
// (har do dar map-e /<name>) — samt-e ratholectl har do jahat check mishavad.
function pxAdd(n){formModal(t('t_px_add'),[
  {id:'name',label:t('px_name'),ph:'grafana',req:1},
  {id:'upstream',label:t('px_up'),ph:'http://127.0.0.1:3000',req:1}],
  v=>{
   if(!/^[A-Za-z0-9_-]{1,40}$/.test(v.name)){toast(t('px_bad_name'));return;}
   if(!/^https?:\/\/[A-Za-z0-9._-]{1,255}:[0-9]{1,5}$/.test(v.upstream)){toast(t('px_bad_up'));return;}
   closeModal();run(n,'proxy_add',{name:v.name,upstream:v.upstream});
  });}

function pxRm(n){formModal(t('t_px_rm'),[{id:'name',label:t('px_name'),req:1}],
  v=>{closeModal();run(n,'proxy_rm',{name:v.name});});}

// ============ HAMEL-e tunnel (carrier) — enhesari ============
// rooye node har panj halat HAMAN motaghayer-e TUNNEL ra minevisand، pas dar har lahze
// daghighan YEKI faal ast. in select haman vaghiat ra neshan midahad va avaz kardanash
// yek amal-e HEDAYAT-SHODE ast: parametrha khodkar az server Iran gerefte mishavand va
// (baraye noise/backhaul) samt-e Iran ham hamahang mishavad.
const CARRIERS=['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre'];

function nodeCarrier(ov){
 const c=(((ov||{}).status||{}).main||{}).transport||(ov||{}).main_tunnel||'ws';
 return CARRIERS.indexOf(c)>=0?c:'ws';
}

function carrierSelect(n,ov){
 const cur=nodeCarrier(ov);
 const opts=CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c))}</option>`).join('');
 return `<select id="car_${n}" onchange="setCarrier('${n}',this.value,'${cur}')">${opts}</select>`;
}

// avaz kardan-e hamel. har halat form/parametr-e khodash ra darad؛ 'ws' bazgasht be
// pishfarz ast va faghat halat-e feli ra khamoosh mikonad.
function setCarrier(n,next,cur){
 if(next===cur)return;
 const sel=$('car_'+n); if(sel)sel.value=cur;
 const ov=OVS[n]||{};
 const names=[...new Set([...(ov.services||[]),...(ov.backhaul_services||[])].map(x=>x.name))];
 if(names.length===1){nodeServiceAction(n,names[0],'configure',next);return;}
 if(!names.length){toast(t('no_svc'));return;}
 formModal(t('carrier'),[{id:'service',label:t('c_svc'),type:'select',val:names[0],opts:names.map(x=>({v:x,t:x}))}],v=>{
  closeModal();nodeServiceAction(n,v.service,'configure',next);
 });
}

function frpOnIran(n){formModal(t('t_frp_iran'),[
  {id:'port',label:t('l_frp_port'),val:'7000',req:1},
  {id:'token',label:t('l_frp_token'),ph:'اختیاری (تولید خودکار)'},
  {id:'transport',label:t('l_frp_tr')+' (یک پروتکل UDP فعال روی هر پورت: KCP یا QUIC)',type:'select',val:'tcp',opts:[{v:'tcp',t:'TCP'},{v:'kcp',t:'KCP'},{v:'quic',t:'QUIC'},{v:'websocket',t:'WebSocket'}]}],
  v=>{closeModal();run(n,'frp_on',{port:v.port,token:v.token||'',transport:v.transport||'tcp'});});}

function frpOnNode(n){
 const irs=iranServers();
 const services=(OVS[n]||{}).services||[];
 const names=services.map(s=>s.name);
 if(!names.length) names.push(n);
 formModal(t('t_frp_iran')+' ('+n+')',[
   {id:'iran',label:'سرور ایران:',type:'select',val:(irs[0]||{}).name||'',opts:irs.map(s=>({v:s.name,t:s.name}))},
   {id:'service',label:'نام سرویس نود:',type:'select',val:names[0],opts:names.map(x=>({v:x,t:x}))}
 ],v=>{
   closeModal();
   if(!v.iran){toast('⚠️ سرور ایران در هاب ثبت نشده است.');return;}
   quickCarrierModal(v.iran,v.service,'frp');
 });
}

function paqetAutofill(nodeName){
 if(!nodeName)return;
 api('GET','api/servers/'+nodeName+'/paqetconnect').then(({j})=>{
  if(!j||!j.ok)return;
  if($('f_remote')&&j.remote)$('f_remote').value=j.remote;
  if($('f_key')&&j.key)$('f_key').value=j.key;
  if($('f_mode')&&j.mode)$('f_mode').value=j.mode;
  if($('f_block')&&j.block)$('f_block').value=j.block;
 });
}

function paqetOnIran(n){
 const nodes=SERVERS.filter(s=>s.role==='node');
 const f=[];
 if(nodes.length){
  f.push({id:'node_src',label:t('l_paqet_node'),type:'select',val:nodes[0].name,
   opts:nodes.map(s=>({v:s.name,t:s.name+' ('+(s.host||'')+')'}))});
 }
 f.push(
  {id:'remote',label:t('l_paqet_remote'),ph:'198.51.100.5:9999',req:1},
  {id:'key',label:t('l_paqet_key'),req:1},
  {id:'mode',label:t('l_paqet_mode'),type:'select',val:'fast',opts:[{v:'fast',t:'fast'},{v:'fast2',t:'fast2'},{v:'fast3',t:'fast3'},{v:'normal',t:'normal'}]},
  {id:'block',label:t('l_paqet_block'),type:'select',val:'aes-128-gcm',opts:[{v:'aes-128-gcm',t:'aes-128-gcm'},{v:'aes-128',t:'aes-128'},{v:'aes',t:'aes'},{v:'salsa20',t:'salsa20'},{v:'xor',t:'xor'},{v:'none',t:'none'}]},
  {id:'conn',label:t('l_paqet_conn'),val:'1'}
 );
 formModal(t('t_paqet_iran'),f,v=>{closeModal();run(n,'paqet_on',{remote:v.remote,key:v.key,mode:v.mode||'fast',block:v.block||'aes-128-gcm',conn:v.conn||'1'});});
 const sel=$('f_node_src');
 if(sel){
  sel.onchange=()=>paqetAutofill(sel.value);
  paqetAutofill(sel.value);
 }
}

function paqetNode(n,preName){
 const nodes=((OVS[n]||{}).nodes||[]).map(x=>x.name);
 const f=[nodes.length
  ?{id:'name',label:t('c_name'),type:'select',val:preName||nodes[0],opts:nodes.map(x=>({v:x,t:x}))}
  :{id:'name',label:t('c_name'),val:preName||'',req:1},
  {id:'act',label:t('c_ops'),type:'select',val:'on',opts:[{v:'on',t:'on (Paqet)'},{v:'off',t:'off (WS/443)'}]}];
 formModal(t('paqet_node_on'),f,v=>{
  closeModal();
  run(n,v.act==='off'?'paqet_node_off':'paqet_node_on',{name:v.name});
 });
}

function paqetOnNode(n){
 formModal(t('t_paqet_node')+' ('+n+')',[
  {id:'port',label:t('l_paqet_port'),val:'9999',req:1},
  {id:'key',label:t('l_paqet_key'),ph:'اختیاری (تولید خودکار)'},
  {id:'mode',label:t('l_paqet_mode'),type:'select',val:'fast',opts:[{v:'fast',t:'fast'},{v:'fast2',t:'fast2'},{v:'fast3',t:'fast3'},{v:'normal',t:'normal'}]},
  {id:'block',label:t('l_paqet_block'),type:'select',val:'aes-128-gcm',opts:[{v:'aes-128-gcm',t:'aes-128-gcm'},{v:'aes-128',t:'aes-128'},{v:'aes',t:'aes'},{v:'salsa20',t:'salsa20'},{v:'xor',t:'xor'},{v:'none',t:'none'}]},
  {id:'conn',label:t('l_paqet_conn'),val:'1'}
 ],v=>{
  closeModal();
  const args={port:v.port||'9999',mode:v.mode||'fast',block:v.block||'aes-128-gcm',conn:v.conn||'1'};
  if(v.key&&v.key.trim())args.key=v.key.trim();
  run(n,'paqet_on',args);
 });
}

function setupXrayNode(n){
 formModal(t('t_xray_setup')+' ('+n+')',[
  {id:'mode',label:t('l_xray_mode'),type:'select',val:'reality',opts:[{v:'reality',t:'VLESS + REALITY + Vision'},{v:'xhttp',t:'VLESS + XHTTP'}]},
  {id:'port',label:t('l_xray_port'),val:'8443',req:1},
  {id:'dest',label:t('l_xray_dest'),val:'www.microsoft.com:443'},
  {id:'sni',label:t('l_xray_sni'),val:'www.microsoft.com'},
  {id:'path',label:t('l_xray_path'),val:'/xhttp'},
  {id:'xhttp_mode',label:t('l_xray_xmode'),type:'select',val:'auto',opts:[{v:'auto',t:'auto'},{v:'packet-up',t:'packet-up'},{v:'stream-up',t:'stream-up'},{v:'stream-one',t:'stream-one'}]},
  {id:'proxy_protocol',label:t('l_xray_pp'),type:'select',val:'0',opts:[{v:'0',t:'Off'},{v:'1',t:'On (acceptProxyProtocol)'}]}
 ],v=>{
  closeModal();
  const mode=v.mode||'reality';
  const args={mode,port:v.port||(mode==='reality'?'8443':'2087'),proxy_protocol:v.proxy_protocol==='1'};
  if(mode==='reality'){
   if(v.dest&&v.dest.trim())args.dest=v.dest.trim();
   if(v.sni&&v.sni.trim())args.sni=v.sni.trim();
  }else{
   args.path=(v.path&&v.path.trim())||'/xhttp';
   args.xhttp_mode=v.xhttp_mode||'auto';
  }
  run(n,'xray_setup',args);
 });
}

async function scanXrayCover(n){
 formModal(t('t_xray_scan')+' ('+n+')',[
  {id:'domains',label:t('l_scan_domains'),ph:'www.microsoft.com,aws.amazon.com'},
  {id:'top',label:t('l_scan_top'),val:'5'}
 ],async v=>{
  closeModal();
  toast(t('running')+' xray_scan '+t('on')+' '+n+' …');
  const args={top:v.top||'5'};
  if(v.domains&&v.domains.trim())args.domains=v.domains.trim();
  const {j}=await api('POST','api/servers/'+n+'/action',{action:'xray_scan',args});
  if(!j){toast(t('err_req'));return;}
  let txt=(j.out||'').trim();
  try{
   const parsed=JSON.parse(txt);
   const list=Array.isArray(parsed.results)?parsed.results:(Array.isArray(parsed.candidates)?parsed.candidates:null);
   if(list){
    const rec=parsed.recommended?`★ recommended: ${parsed.recommended}\n\n`:'';
    txt=rec+list.map(c=>`${c.ok?'✓':'✗'} ${c.domain} | ${c.tls_version||(c.tls13?'TLSv1.3':'-')} | alpn=${c.alpn||'-'} | rtt=${c.rtt_ms!=null?c.rtt_ms+'ms':'-'} | ${c.detail||c.reason||c.verdict||''}`).join('\n');
   }
  }catch(e){}
  outModal(t('t_xray_scan'),txt||j.err||'ok');
 });
}

function showXrayUri(n){run(n,'xray_uri',{});}

function greOnIran(n){formModal(t('t_gre_iran'),[
  {id:'remote_ip',label:t('l_gre_remote'),req:1},
  {id:'tunnel_ip',label:t('l_gre_tunnel'),val:'10.10.10.1',req:1},
  {id:'name',label:t('l_gre_name'),val:'gre1',req:1}],
  v=>{closeModal();run(n,'gre_on',v);});}

// ============ HAMEL-e per-UPSTREAM (mesl-e tunnel-e asli, vali baraye har upstream) ============
// har upstream yek server-e Iran-e mostaghel ast va TUNNEL-e khodash ra dar up_env darad،
// pas daghighan mesl-e tunnel-e asli ENHESARI ast: yek select، na chand dokme.
// backhaul inja NIST — backhaul yek core-e joda-ye 1:1 ast (yek token/yek ports baraye kol-e
// server-e Iran) va per-upstream mani nemidahad.
const UP_CARRIERS=['ws','kcp','plain','noise'];

function upCarrier(u){
 const c=((u||{}).tunnel||'ws');
 return UP_CARRIERS.indexOf(c)>=0?c:'ws';
}
function upCarrierSelect(n,u){
 const cur=upCarrier(u), id='upcar_'+n+'__'+u.id;
 const opts=UP_CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c))}</option>`).join('');
 return `<select id="${h(id)}" title="${h(t('carrier'))}" data-upcar-srv="${h(n)}" data-upcar-id="${h(u.id)}" data-upcar-cur="${h(cur)}">${opts}</select>`;
}
// avaz kardan-e hamel-e yek upstream. har halat form/parametr-e khodash ra darad؛
// 'ws' bazgasht be pishfarz ast va har hamel-e digar ra khamoosh mikonad.
function setUpCarrier(n,id,next,cur){
 if(next===cur)return;
 const sel=$('upcar_'+n+'__'+id);
 const revert=()=>{if(sel)sel.value=cur;};
 if(!confirm(t('upcarrier_confirm').replace('%s',t('carrier_'+next)).replace('%n',id))){revert();return;}
 switch(next){
   case 'ws':    run(n,'upstream_ws',{id}); break;
   case 'kcp':   upKcpOn(n,id); break;
   case 'plain': upPlainOn(n,id); break;
   case 'noise': upNoiseOn(n,id); break;
   default: revert();
 }
}
// plain baraye upstream: faghat adres-e HTTP-e sade-ye an server-e Iran lazem ast.
function upPlainOn(n,id){formModal(t('t_plain_node')+' ('+id+')',[
  {id:'remote',label:t('l_plain_remote'),ph:'5.202.4.40:8880',req:1}],
  v=>{closeModal();run(n,'upstream_plain_on',{id,remote:v.remote});});}
// noise baraye upstream: hamon field-ha va autofill-e tunnel-e asli.
function upNoiseOn(n,id){formModal(t('t_noise_node')+' ('+id+')',noiseNodeFields(),
  v=>{closeModal();run(n,'upstream_noise_on',{id,remote:v.remote,pubkey:v.pubkey,pattern:v.pattern||''});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>noiseAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();noiseAutofill(sel.value);};box.appendChild(b);}
   noiseAutofill(sel.value);
 }}

// ============ MODE-e per-node SAMT-e IRAN (select mesl-e node) ============
const IRAN_NODE_CARRIERS=['ws','kcp','plain','noise','backhaul','frp','gre','frp_gre','paqet'];

// select-e per-node baraye node-haye Iran. baraye node-haye game (L4) select bi-mani ast.
function iranNodeCarrierSel(iran,ov,name){
 const mode=iranNodeMode(ov,name);
 if(mode==='game')return `<span class="badge b-game">${h(t('mode_game'))}</span>`;
 const cur=IRAN_NODE_CARRIERS.indexOf(mode)>=0?mode:'ws';
 const id='icar_'+iran+'__'+name;
 const opts=IRAN_NODE_CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c)||c.toUpperCase())}</option>`).join('');
 return `<select id="${h(id)}" title="${h(t('carrier'))}" data-icar-iran="${h(iran)}" data-icar-name="${h(name)}" data-icar-cur="${h(cur)}">${opts}</select>`;
}

// avaz kardan-e transport-e YEK node samt-e Iran ba hamahang-sazi-ye khodkar-e do-tarafe.
// avaz kardan-e hamel-e YEK node az samte Iran, ba hamzaman-sazi-e KHODKAR-e do-taraf.
// hamel-haye sade (ws/kcp/plain/noise/backhaul) yek-kliki va bedoone modal ejra mishavand;
// hamel-haye frp/gre/frp_gre voroodi-e bishtar (IP/transport) mikhahand → modal.
async function setIranNodeCarrier(iran,name,next,cur){
 if(next===cur)return;
 const getSel=()=>$('icar_'+iran+'__'+name);
 const revert=()=>{const el=getSel();if(el)el.value=cur;};
 if(next==='paqet'){paqetNode(iran,name);revert();return;}
 if(next==='frp'||next==='gre'||next==='frp_gre'){quickCarrierModal(iran,name,next);revert();return;}
 const peers=SERVERS.filter(s=>s.role==='node');
 const sNode=findNodeServer(name)||(peers.length===1?peers[0]:null);
 if(!sNode){
  revert();
  if(peers.length)quickCarrierModal(iran,name,next);
  else toast(t('no_node_dst'));
  return;
 }
 if(!confirm(t('icarrier_confirm').replace('%s',t('carrier_'+next)||next).replace('%n',name))){revert();return;}
 const existingIran=((OVS[iran]||{}).nodes||[]).find(x=>x.name===name);
 const port=(existingIran&&(existingIran.inbound_port||existingIran.inbound))||null;
 const sel0=getSel(); if(sel0)sel0.disabled=true;
 toast(t('carrier_syncing').replace('%s',next.toUpperCase()),0);
 try{
  const ok=await configureServiceCarrier(iran,name,next,port,{node_server:sNode.name,silent:true});
  if(ok===false){revert();return;}          // configureServiceCarrier khodesh toast-e khata midahad
  toast(t('carrier_synced').replace('%s',next.toUpperCase()));
 }catch(e){
  revert();
  toast('⚠️ '+(e&&e.message?e.message:t('carrier_sync_fail')));
 }finally{
  const el=getSel(); if(el)el.disabled=false;
 }
}

 // list-e serverhaye Iran (baraye autofill-e KCP)
function iranServers(){return SERVERS.filter(s=>s.role==='iran');}
// gozine-haye <option> baraye entekhab-e server Iran (host be onvan value)
function iranSrvOptions(){return iranServers().map(s=>`<option value="${h(s.host)}">${h(s.name)} (${h(s.host)})</option>`).join('');}
// tunnel-e asli (main) ye node ra be yek server Iran vasl kon (SERVER=domain:443)
// mohem: dar halat-e pishfarz (ws+TLS) node bayad be DOMAIN-e omoomi vasl shavad, na host/IP-e
// SSH-e inventory — chon ratholenode az SERVER ham remote_addr va ham SNI ra misazad. pas
// entekhab az roo-ye NAM-e server Iran ast va maghsad-e daghigh (domain) ra az server migirim.
async function prepareIpTls(iran,node){
 toast(t('autofilling'));
 const {j}=await api('POST','api/ip-tls/prepare',{iran:iran,node:node});
 if(!j||!j.ok){outModal(t('main_ip_self'),((j&&j.err)||JSON.stringify(j||{})));return null;}
 return j;
}
function setMainSrv(n){
 const irs=iranServers();
 if(!irs.length){toast(t('no_iran'));return;}
 const f=[{id:'iran',label:t('l_iran_srv'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))},
   {id:'dial_mode',label:t('conn_dial'),type:'select',val:'domain',opts:[
    {v:'domain',t:t('main_domain_tls')},{v:'ip',t:t('main_ip_sni')},{v:'ip_self',t:t('main_ip_self')}
   ]}];
 formModal(t('set_main'),f,async v=>{
  const iran=(v.iran||'').trim(); if(!iran){toast(t('fill'));return;}
  closeModal();
  toast(t('autofilling'));
  // domain-e vaghei (ba cert-e mokhtabetesh) ra az server Iran begir, na host-e inventory
  const {j}=await api('GET','api/servers/'+iran+'/mainconnect');
  if(!j||!j.ok||!j.server){toast(t('autofail'));return;}
  if(v.dial_mode==='ip_self'){
   if(!confirm(t('main_ip_self_confirm')))return;
   const r=await prepareIpTls(iran,n);
   if(!r)return;
   await run(n,'set_main',{server:r.server,tls_hostname:r.tls_hostname,tls_trusted_root:r.tls_trusted_root});
   return;
  }
  const server=v.dial_mode==='ip'?(j.dial_ip||j.server):j.server;
  run(n,'set_main',{server:server,tls_hostname:j.tls_hostname||j.domain||''});
 });
}
// sim-keshi: yek node-e Iran (name/token/inbound) ra rooye yek node-e kharej (ya upstream-esh)
// be-onvan service ezafe kon. maghsadha: hameye node-ha + upstream-hayeshan; anha ke tunnel-eshan
// be hamin Iran vasl ast ba ✓ neshan dade va default entekhab mishavand.
function wireTargets(iranHost){
 const opts=[]; let def='';
 SERVERS.filter(s=>s.role==='node').forEach(s=>{
  const ov=OVS[s.name]; if(!ov||ov.reachable===false)return;
  const ms=String(ov.main_server||'');
  const hit=iranHost && (ms===iranHost || ms.split(':')[0]===iranHost);
  opts.push({v:s.name+'|', t:(hit?'✓ ':'')+s.name+' — main ('+(ms||'?')+')'});
  if(hit && !def)def=s.name+'|';
  (ov.upstreams||[]).forEach(u=>{
   const us=String(u.server||''); const uh=us && (us===iranHost || us.split(':')[0]===iranHost);
   opts.push({v:s.name+'|'+u.id, t:(uh?'✓ ':'')+s.name+' ▸ upstream '+u.id+' ('+(us||'?')+')'});
   if(uh && !def)def=s.name+'|'+u.id;
  });
 });
 return {opts, def:def||(opts[0]&&opts[0].v)||''};
}
async function wireNode(iranName,nodeName){
 const s=SERVERS.find(x=>x.name===iranName)||{}; const iranHost=s.host||'';
 const {opts,def}=wireTargets(iranHost);
 if(!opts.length){toast(t('no_node_dst'));return;}
 formModal(t('wire_title')+' · '+nodeName,
   [{id:'dst',label:t('l_dst_node'),type:'select',val:def,opts}],
   async v=>{
    const parts=(v.dst||'').split('|'); const dst=parts[0], up=parts[1]||'';
    if(!dst){toast(t('fill'));return;}
    closeModal();
    toast(t('autofilling'));
    // 1) token/inbound-e vaghei-ye node-e Iran ra begir (token dar 'ls' mask ast)
    const {j}=await api('GET','api/servers/'+iranName+'/nodeconnect/'+nodeName);
    if(!j||!j.ok){toast(t('wire_fail'));outModal(t('wire_title'),(j&&(j.error||j.raw))||'?');return;}
    // 2) rooye node-e kharej (ya upstream-esh) be-onvan service ezafe kon
    if(up)run(dst,'upstream_add_svc',{id:up,name:j.name,token:j.token,inbound:j.inbound});
    else  run(dst,'add_svc',{name:j.name,token:j.token,inbound:j.inbound,remote_port:j.remote_port});
   });
}
// autofill: az server Iran-e entekhab-shode remote/key/profile-e daghigh ra migirad
async function kcpAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/kcpconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_key'))$('f_key').value=j.key||'';
 if($('f_profile')&&j.profile)$('f_profile').value=j.profile;
 toast(t('autofilled'));
}
function kcpNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_remote'),ph:'5.202.4.40:443',req:1});
 f.push({id:'key',label:t('l_key'),req:1});
 f.push({id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF});
 return f;
}
function upKcpOn(n,id){formModal(t('t_kcp_up')+' ('+id+')',kcpNodeFields(),
  v=>{closeModal();run(n,'upstream_kcp_on',{id,remote:v.remote,key:v.key,profile:v.profile||'balanced'});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>kcpAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.onclick=e=>{e.preventDefault();kcpAutofill(sel.value);};box.appendChild(b);}
   kcpAutofill(sel.value);
 }}


function editNode(n,name){formModal(t('t_edit_node')+' ('+name+')',[
  {id:'inbound',label:t('l_inb_new')},
  {id:'api_port',label:t('l_api_new')}],
  v=>{const a={name};if(v.inbound)a.inbound=v.inbound;if(v.api_port)a.api_port=v.api_port;
   if(!a.inbound&&!a.api_port){toast(t('nochg'));return;}closeModal();run(n,'edit_node',a);});}
function renameNode(n,name){formModal(t('t_rename'),[
  {id:'new',label:t('l_new_name'),val:name,req:1}],
  v=>{if(v.new===name){closeModal();return;}closeModal();run(n,'rename_node',{old:name,new:v.new});});}
function editServer(n){const s=fnd(n);
 if(s.transport==='api'){
  formModal(t('t_edit_srv')+' ('+n+')',[
   {id:'api_url',label:t('f_api_url'),val:s.api_url||'',req:1},
   {id:'public_ip',label:'IP عمومی مقصد تونل (اختیاری؛ اگر تشخیص خودکار اشتباه است)',val:s.public_ip||''},
   {id:'api_token',label:t('f_api_token'),val:'',type:'password'}],
   async v=>{const body={api_url:v.api_url.trim(),public_ip:(v.public_ip||'').trim()};if(v.api_token.trim())body.api_token=v.api_token.trim();
    const {status,j}=await api('PUT','api/servers/'+n,body);
    if(status!==200){toast('error: '+(j.error||status));return;}closeModal();toast(t('saved'));loadAll();});
  return;
 }
 formModal(t('t_edit_srv')+' ('+n+')',[
  {id:'host',label:t('f_host'),val:s.host,req:1},
  {id:'public_ip',label:'IP عمومی مقصد تونل (اختیاری؛ اگر IP آدرس SSH نیست)',val:s.public_ip||''},
  {id:'ssh_user',label:t('f_user'),val:s.ssh_user||'root',req:1},
  {id:'ssh_port',label:t('f_port'),val:s.ssh_port||'22',req:1}],
  async v=>{const {status,j}=await api('PUT','api/servers/'+n,{host:v.host,public_ip:(v.public_ip||'').trim(),ssh_user:v.ssh_user,ssh_port:v.ssh_port});
   if(status!==200){toast('error: '+(j.error||status));return;}closeModal();toast(t('saved'));loadAll();});}

async function savePw(){const cur=$('cpw').value,nw=$('npw').value;if(!nw){toast(t('need_newpw'));return;}const {status,j}=await api('POST','api/config',{current_password:cur,new_password:nw});if(status!==200){toast('error: '+(j.error||status));return;}toast(t('pw_changed'));$('cpw').value='';$('npw').value='';}
async function rotTok(){if(!confirm(t('cf_rottok')))return;const {status,j}=await api('POST','api/config',{rotate_token:true});if(status!==200){toast('error: '+(j.error||status));return;}TOKEN=j.api_token;localStorage.setItem('rh_token',TOKEN);toast(t('tok_applied'));renderSettingsPage();}
let TUNER_STATE={activeJobId:null,job:null,lastReport:null,profiles:null,jobs:[],jobsLoaded:false,pollTimer:null,iran:'',node:'',mode:'brutal',goal:'balanced',deep:false,iran_dc:'',node_dc:''};
function clearTunerPoll(){if(TUNER_STATE.pollTimer){clearTimeout(TUNER_STATE.pollTimer);TUNER_STATE.pollTimer=null;}}
function _tunerPhaseLabel(phase){
 const p=String(phase||'starting');
 const key='tuner_ph_'+p;
 const tr=t(key);
 return tr!==key?tr:p;
}
function _upsertTunerJob(job){
 if(!job||!job.job_id)return;
 const list=(TUNER_STATE.jobs||[]).filter(x=>x&&x.job_id!==job.job_id);
 list.unshift(job);
 TUNER_STATE.jobs=list.slice(0,20);
}
async function loadTunerJobs(force=false){
 const {status,j}=await api('GET','api/tuner/jobs');
 TUNER_STATE.jobsLoaded=true;
 if(status!==200||!j)return;
 const jobs=Array.isArray(j.jobs)?j.jobs:[];
 TUNER_STATE.jobs=jobs;
 if(force||!TUNER_STATE.job){
  const picked=jobs.find(x=>x&&x.status==='running')||jobs[0]||null;
  if(picked){
   TUNER_STATE.job=picked;
   if(picked.iran)TUNER_STATE.iran=picked.iran;
   if(picked.node)TUNER_STATE.node=picked.node;
   if(picked.mode)TUNER_STATE.mode=picked.mode;
   if(picked.goal)TUNER_STATE.goal=picked.goal;
   TUNER_STATE.lastReport=(picked.status==='done'&&picked.result)?picked.result:null;
   TUNER_STATE.activeJobId=(picked.status==='running')?picked.job_id:null;
  }
 }
 if(ROUTE.page==='tuner'){
  renderTunerPage();
  if(TUNER_STATE.activeJobId&&!TUNER_STATE.pollTimer)pollTunerJob(TUNER_STATE.activeJobId);
 }
}
async function selectTunerJob(jobId){
 if(!jobId)return;
 clearTunerPoll();
 const {status,j}=await api('GET','api/tuner/jobs/'+encodeURIComponent(jobId));
 const job=(status===200&&j)?j:(TUNER_STATE.jobs||[]).find(x=>x&&x.job_id===jobId);
 if(!job)return;
 _upsertTunerJob(job);
 TUNER_STATE.job=job;
 if(job.iran)TUNER_STATE.iran=job.iran;
 if(job.node)TUNER_STATE.node=job.node;
 if(job.mode)TUNER_STATE.mode=job.mode;
 if(job.goal)TUNER_STATE.goal=job.goal;
 TUNER_STATE.lastReport=(job.status==='done'&&job.result)?job.result:null;
 TUNER_STATE.activeJobId=(job.status==='running')?job.job_id:null;
 renderTunerPage();
 if(TUNER_STATE.activeJobId)pollTunerJob(TUNER_STATE.activeJobId);
}
function dismissTunerJob(){
 clearTunerPoll();
 TUNER_STATE.activeJobId=null;
 TUNER_STATE.job=null;
 TUNER_STATE.lastReport=null;
 renderTunerPage();
}
async function loadTunerProfiles(){
 const {status,j}=await api('GET','api/tuner/profiles');
 if(status===200){TUNER_STATE.profiles=j.profiles||[];}
 else if(!TUNER_STATE.profiles){TUNER_STATE.profiles=[];}
 if(ROUTE.page==='tuner'){const box=$('tn_lib_box');if(box)box.innerHTML=_renderTunerLibraryRows();}
}
async function startTunerJob(profileB64Override=''){
 const ir=($('tn_iran')&&$('tn_iran').value)||TUNER_STATE.iran||'';
 const nd=($('tn_node')&&$('tn_node').value)||TUNER_STATE.node||'';
 if(!ir||!nd){toast(t('tuner_need_pair'));return;}
 const mode=($('tn_mode')&&$('tn_mode').value)||TUNER_STATE.mode||'brutal';
 const goal=($('tn_goal')&&$('tn_goal').value)||TUNER_STATE.goal||'balanced';
 const deep=!!(($('tn_deep')&&$('tn_deep').checked)||false);
 const iran_dc=(($('tn_iran_dc')&&$('tn_iran_dc').value)||'').trim();
 const node_dc=(($('tn_node_dc')&&$('tn_node_dc').value)||'').trim();
 Object.assign(TUNER_STATE,{iran:ir,node:nd,mode,goal,deep,iran_dc,node_dc});
 const body={iran:ir,node:nd,mode,goal,deep,tags:{iran_dc,node_dc}};
 if(profileB64Override){body.profile=profileB64Override;}
 const {status,j}=await api('POST','api/tuner/start',body);
 if(status>=400||!j||!j.ok){toast('error: '+((j&&j.error)||status));return;}
 TUNER_STATE.activeJobId=j.job_id;
 TUNER_STATE.job=j.job||{job_id:j.job_id,iran:ir,node:nd,mode,goal,status:'running',phase:'starting_responder',stage_index:0,stage_total:6,live_trials:[]};
 TUNER_STATE.lastReport=null;
 TUNER_STATE.jobsLoaded=true;
 _upsertTunerJob(TUNER_STATE.job);
 renderTunerPage();
 pollTunerJob(j.job_id);
}
function pollTunerJob(jobId){
 clearTunerPoll();
 if(!jobId||ROUTE.page!=='tuner')return;
 TUNER_STATE.pollTimer=setTimeout(async()=>{
  if(ROUTE.page!=='tuner'||TUNER_STATE.activeJobId!==jobId)return;
  const {status,j}=await api('GET','api/tuner/jobs/'+encodeURIComponent(jobId));
  if(status===404){
   TUNER_STATE.activeJobId=null;
   TUNER_STATE.job={...(TUNER_STATE.job||{job_id:jobId}),status:'error',phase:'error',error:'Job not found on hub'};
   renderTunerPage();
   return;
  }
  if(status===200&&j){
   TUNER_STATE.job=j;
   _upsertTunerJob(j);
   if(j.status==='done'&&j.result){
    TUNER_STATE.lastReport=j.result;
    TUNER_STATE.activeJobId=null;
    renderTunerPage();
    const w=(j.result.benchmarks&&j.result.benchmarks.winner)||j.result.candidate;
    toast('✓ '+(w&&w.throughput_mbps!=null?w.throughput_mbps+' Mbps':'done'));
    return;
   }
   if(j.status==='error'||j.status==='cancelled'){
    TUNER_STATE.activeJobId=null;
    renderTunerPage();
    if(j.error)toast('error: '+j.error);
    return;
   }
   const pb=$('tn_prog_box');
   if(pb)_patchTunerProgressBox(pb);
   else renderTunerPage();
  }
  pollTunerJob(jobId);
 },1200);
}
async function cancelTunerJob(){
 const jid=TUNER_STATE.activeJobId;
 if(!jid)return;
 clearTunerPoll();
 await api('POST','api/tuner/jobs/'+encodeURIComponent(jid)+'/cancel',{});
 TUNER_STATE.activeJobId=null;
 if(TUNER_STATE.job){TUNER_STATE.job.status='cancelled';TUNER_STATE.job.phase='cancelled';_upsertTunerJob(TUNER_STATE.job);}
 renderTunerPage();
}
function _copyTunerText(txt){
 if(!txt)return;
 if(navigator&&navigator.clipboard&&navigator.clipboard.writeText){
  navigator.clipboard.writeText(txt).then(()=>toast('✓ '+t('rc_copied'))).catch(()=>toast(t('rc_copied')));
 }else{
  toast('✓ '+t('rc_copied'));
 }
}
function copyTunerJson(){
 const p=TUNER_STATE.lastReport&&TUNER_STATE.lastReport.profile;
 if(p)_copyTunerText(JSON.stringify(p,null,2));
}
function copyTunerBase64(){
 const b=TUNER_STATE.lastReport&&TUNER_STATE.lastReport.profile_b64;
 if(b)_copyTunerText(b);
}
async function saveTunerProfileToLib(){
 const b=TUNER_STATE.lastReport&&TUNER_STATE.lastReport.profile_b64;
 if(!b)return;
 const p=TUNER_STATE.lastReport.profile||{};
 const nm=(p.meta&&p.meta.name)||'optimal-profile';
 await importTunerProfile(nm,b);
}
async function importTunerProfile(name,rawSpec){
 const txt=String(rawSpec||'').trim();
 if(!txt){toast(t('fill'));return false;}
 let payload=txt;
 if(txt.startsWith('{')){
  try{payload=JSON.parse(txt);}catch(e){toast('error: invalid JSON');return false;}
 }
 const {status,j}=await api('POST','api/tuner/profiles',{name:(name||'').trim(),profile:payload});
 if(status!==200||!j||!j.ok){toast('error: '+((j&&j.error)||status));return false;}
 closeModal();
 toast('✓ '+t('saved'));
 await loadTunerProfiles();
 return true;
}
function openImportTunerModal(){
 modal(`<h3>${h(t('tuner_import_title'))}</h3>
  <div class="row"><label for="tn_imp_nm">${h(t('f_name'))}</label><input id="tn_imp_nm" type="text" placeholder="arvan-hetzner-fast"></div>
  <div style="margin-top:8px"><textarea id="tn_imp_txt" class="tuner-code" placeholder="${h(t('tuner_import_ph'))}"></textarea></div>
  <div class="modal-actions"><button class="gh" type="button" onclick="closeModal()">${h(t('cancel'))}</button>
  <button class="g" type="button" onclick="importTunerProfile($('tn_imp_nm').value,$('tn_imp_txt').value)">${h(t('save'))}</button></div>`);
}
async function deleteTunerProfile(pid){
 const {status,j}=await api('DELETE','api/tuner/profiles/'+encodeURIComponent(pid));
 if(status!==200){toast('error: '+((j&&j.error)||status));return;}
 toast('✓ '+t('done'));
 await loadTunerProfiles();
}
function copyTunerLibItem(idx,fmt){
 const p=(TUNER_STATE.profiles||[])[idx];
 if(!p)return;
 _copyTunerText(fmt==='json'?JSON.stringify(p.profile||{},null,2):(p.profile_b64||''));
}
function testTunerLibItem(idx){
 const p=(TUNER_STATE.profiles||[])[idx];
 if(p&&p.profile_b64)startTunerJob(p.profile_b64);
}
function applyTunerLibItem(idx){
 const p=(TUNER_STATE.profiles||[])[idx];
 if(p)applyTunerProfileBoth(p.profile_b64||'',p.id||'');
}
function deleteTunerLibItem(idx){
 const p=(TUNER_STATE.profiles||[])[idx];
 if(p&&p.id)deleteTunerProfile(p.id);
}
async function applyTunerProfileBoth(profileB64,profileId){
 const ir=($('tn_iran')&&$('tn_iran').value)||TUNER_STATE.iran||'';
 const nd=($('tn_node')&&$('tn_node').value)||TUNER_STATE.node||'';
 if(!ir||!nd){toast(t('tuner_need_pair'));return;}
 if(!confirm(t('tuner_cf_apply')))return;
 const body={iran:ir,node:nd};
 if(profileId)body.profile_id=profileId;
 else body.profile=profileB64||(TUNER_STATE.lastReport&&TUNER_STATE.lastReport.profile_b64)||'';
 const {status,j}=await api('POST','api/tuner/apply',body);
 if(status!==200||!j||!j.ok){toast('error: '+((j&&j.error)||status));return;}
 toast('✓ '+t('done'));
}
async function rollbackTunerBoth(){
 const ir=($('tn_iran')&&$('tn_iran').value)||TUNER_STATE.iran||'';
 const nd=($('tn_node')&&$('tn_node').value)||TUNER_STATE.node||'';
 if(!ir||!nd){toast(t('tuner_need_pair'));return;}
 if(!confirm(t('tuner_cf_rollback')))return;
 const {status,j}=await api('POST','api/tuner/rollback',{iran:ir,node:nd});
 if(status!==200||!j||!j.ok){toast('error: '+((j&&j.error)||status));return;}
 toast('✓ '+t('done'));
}
function _renderTunerProgressTop(job){
 if(!job)return '';
 const isErr=job.status==='error'||!!job.error;
 const isDone=job.status==='done';
 const isCanc=job.status==='cancelled';
 const stTotal=Math.max(1,Number(job.stage_total||6));
 const stIdx=Number(job.stage_index||0);
 const stagePct=Math.round((stIdx/stTotal)*100);
 const estTrials=Number(job.estimated_trials||0);
 const compTrials=Number(job.completed_trials||0);
 const trialPct=estTrials>0?Math.round((compTrials/Math.max(1,estTrials))*100):0;
 const pct=(isErr||isDone||isCanc)?100:Math.min(98,Math.max(6,Math.max(stagePct,trialPct)));
 const barCls=isErr?' is-error':(isDone?' is-done':'');
 const phaseTxt=_tunerPhaseLabel(job.phase||job.status);
 const pairTag=(job.iran&&job.node)?`<span class="badge b-ws mono" dir="ltr">${h(job.iran)} → ${h(job.node)}</span>`:'';
 const trInfo=estTrials>0?` · ${compTrials}/${estTrials}`:'';

 let stagesHtml='<div class="tuner-stages">';
 for(let si=0;si<6;si++){
  let cls='';
  if(isDone||stIdx>si)cls='is-done';
  else if(isErr&&stIdx===si)cls='is-err';
  else if(!isErr&&!isCanc&&stIdx===si)cls='is-active';
  stagesHtml+=`<span class="tuner-stage ${cls}">${h(t('tuner_st_'+si))}</span>`;
 }
 stagesHtml+='</div>';

 const chips=[];
 if(job.pmtu){
  const pm=job.pmtu;
  const pmin=Math.min(Number(pm.forward_bytes||1500),Number(pm.reverse_bytes||1500));
  chips.push(`<span class="badge ${pm.blackhole_detected?'b-warn':'b-ok'} mono" dir="ltr">PMTU ${h(pmin)}B${pm.blackhole_detected?' (blackhole)':''}</span>`);
 }
 if(job.baseline){
  const bl=job.baseline;
  chips.push(`<span class="badge b-ws mono" dir="ltr">${h(t('tuner_baseline'))}: ${h(bl.throughput_mbps??'-')} Mbps · p95 ${h(bl.loaded_rtt_p95_ms??'-')}ms</span>`);
 }
 if(job.best_trial){
  const bt=job.best_trial;
  chips.push(`<span class="badge b-ok mono" dir="ltr">${h(t('tuner_winner'))}: ${h(bt.name)} (${h(bt.throughput_mbps??'-')} Mbps · score ${h(bt.score??'-')})</span>`);
 }
 if(!isErr&&!isDone&&!isCanc&&job.current_candidate){
  chips.push(`<span class="badge b-info mono" dir="ltr">${h(t('tuner_testing_now'))}: ${h(job.current_candidate)}</span>`);
 }
 const stripHtml=chips.length?`<div class="tuner-live-strip">${chips.join('')}</div>`:'';

 const warnsHtml=Array.isArray(job.warnings)&&job.warnings.length
  ?job.warnings.map(w=>`<div class="tuner-alert">${h(w)}</div>`).join('')
  :'';

 const errHtml=(isErr||job.error)?`<div class="tuner-err" role="alert">
  <div class="sec-head-row"><strong>${h(t('tuner_err_title'))}</strong>
   <div class="btns">
    <button class="s" type="button" onclick="startTunerJob()">${h(t('tuner_retry'))}</button>
    <button class="gh" type="button" onclick="dismissTunerJob()">${h(t('tuner_dismiss'))}</button>
   </div></div>
  <pre class="tuner-err-detail" dir="ltr">${h(job.error||job.phase||'unknown error')}</pre>
 </div>`:'';

 return `<div class="sec-head-row"><strong>${h(t('tuner_progress'))}: ${h(phaseTxt)} ${pairTag}</strong>
  <span class="badge ${isErr?'b-bad':(isDone?'b-ok':'b-info')} mono" dir="ltr">${h(stIdx)}/${h(stTotal)}${h(trInfo)} · ${h(job.elapsed_s??0)}s · best=${h(job.best_so_far??0)}</span></div>
  <div class="tuner-bar"><div class="tuner-bar-fill${barCls}" style="width:${pct}%"></div></div>
  ${stagesHtml}${stripHtml}${errHtml}${warnsHtml}`;
}
function _renderTunerLiveRows(trials){
 if(!Array.isArray(trials)||!trials.length)return '';
 let topScore=-1;
 trials.forEach(tr=>{if(!tr.disqualified&&Number(tr.score||0)>topScore)topScore=Number(tr.score||0);});
 return trials.map((tr,i)=>{
  const isBest=!tr.disqualified&&topScore>=0&&Number(tr.score||0)===topScore;
  const rCls=tr.disqualified?' class="tuner-row-disq"':(isBest?' class="tuner-row-best"':'');
  const stBadge=t('tuner_st_'+Math.min(5,Math.max(0,Number(tr.stage||0))));
  const scCell=tr.disqualified
   ?`<span class="badge b-bad mono"><bdi dir="ltr">FAIL${tr.disqualify_reason?': '+h(tr.disqualify_reason):''}</bdi></span>`
   :`<strong class="mono"><bdi dir="ltr">${isBest?'★ ':''}${h(tr.score??'-')}</bdi></strong>`;
  return `<tr${rCls}><td class="num col-idx mono"><bdi dir="ltr">${i+1}</bdi></td><td class="col-start">${h(stBadge)}</td><td class="col-start col-cand"><bdi dir="ltr">${h(tr.name||tr.id)}</bdi></td><td class="num mono"><bdi dir="ltr">${h(tr.throughput_mbps??'-')}</bdi></td><td class="num mono"><bdi dir="ltr">${h(tr.loaded_rtt_p95_ms??'-')}</bdi></td><td class="num mono"><bdi dir="ltr">${h(tr.jitter_ms??'-')}</bdi></td><td class="num mono"><bdi dir="ltr">${h(tr.retrans_pct??'-')}</bdi></td><td class="num">${scCell}</td></tr>`;
 }).join('');
}
function _renderTunerProgressBody(){
 const job=TUNER_STATE.job;
 if(!job)return '';
 const trials=Array.isArray(job.live_trials)?job.live_trials:[];
 return `<div id="tn_prog_top">${_renderTunerProgressTop(job)}</div>
  <div id="tn_live_sec"${trials.length?'':' hidden'}>
   <div class="tuner-sec-lbl">${h(t('tuner_live_trials'))} (<span id="tn_live_cnt">${trials.length}</span>)</div>
   <div class="table-wrap tuner-live-tbl" id="tn_live_wrap">
    <table class="tuner-tbl"><thead><tr>
     <th class="num col-idx">#</th>
     <th class="col-start">${h(t('tuner_col_stage'))}</th>
     <th class="col-start">${h(t('tuner_col_cand'))}</th>
     <th class="num">Mbps</th>
     <th class="num">p95 ms</th>
     <th class="num">Jitter</th>
     <th class="num">Retrans %</th>
     <th class="num">${h(t('tuner_col_score'))}</th>
    </tr></thead><tbody id="tn_live_tbody">${_renderTunerLiveRows(trials)}</tbody></table>
   </div>
  </div>`;
}
function _patchTunerProgressBox(pb){
 if(!pb)return;
 const job=TUNER_STATE.job;
 if(!job){pb.innerHTML='';return;}
 const q=id=>(pb.querySelector?pb.querySelector('#'+id):null)||$(id);
 const topEl=q('tn_prog_top'), secEl=q('tn_live_sec'), cntEl=q('tn_live_cnt'), wrapEl=q('tn_live_wrap'), tbodyEl=q('tn_live_tbody');
 if(!topEl||!secEl||!cntEl||!wrapEl||!tbodyEl){
  pb.innerHTML=_renderTunerProgressBody();
  const topInit=q('tn_prog_top'), tbodyInit=q('tn_live_tbody');
  if(topInit){topInit.dataset=topInit.dataset||{};topInit.dataset.prevHtml=topInit.innerHTML;}
  if(tbodyInit){tbodyInit.dataset=tbodyInit.dataset||{};tbodyInit.dataset.prevHtml=tbodyInit.innerHTML;}
  return;
 }
 const topHtml=_renderTunerProgressTop(job);
 topEl.dataset=topEl.dataset||{};
 if(topEl.dataset.prevHtml!==topHtml){
  topEl.innerHTML=topHtml;
  topEl.dataset.prevHtml=topHtml;
 }
 const trials=Array.isArray(job.live_trials)?job.live_trials:[];
 secEl.hidden=!trials.length;
 if(String(cntEl.textContent)!==String(trials.length))cntEl.textContent=String(trials.length);
 const rowsHtml=_renderTunerLiveRows(trials);
 tbodyEl.dataset=tbodyEl.dataset||{};
 if(tbodyEl.dataset.prevHtml!==rowsHtml){
  const prevTop=wrapEl.scrollTop||0, prevLeft=wrapEl.scrollLeft||0;
  tbodyEl.innerHTML=rowsHtml;
  tbodyEl.dataset.prevHtml=rowsHtml;
  wrapEl.scrollTop=prevTop;
  wrapEl.scrollLeft=prevLeft;
 }
}
function _renderTunerResultsCard(){
 const rep=TUNER_STATE.lastReport;
 if(!rep)return '';
 const isAb=!rep.benchmarks&&rep.baseline&&rep.candidate;
 const bm=rep.benchmarks||{};
 const b=isAb?rep.baseline:(bm.baseline||{});
 const w=isAb?rep.candidate:(bm.winner||{});
 const goalKey=(rep.profile&&rep.profile.meta&&rep.profile.meta.goal)||rep.goal||TUNER_STATE.goal||'balanced';
 const ws=(w.scores||{});
 const bs=(b.scores||{});
 const rows=[
  ['Throughput (Mbps)',b.throughput_mbps,w.throughput_mbps],
  ['Loaded RTT p95 (ms)',b.loaded_rtt_p95_ms,w.loaded_rtt_p95_ms],
  ['Jitter (ms)',b.jitter_ms,w.jitter_ms],
  ['Retrans (%)',b.retrans_pct,w.retrans_pct],
  ['Stability CoV',b.stability_cov,w.stability_cov],
  ['Score ('+goalKey+')',bs[goalKey],ws[goalKey]]
 ].map(r=>`<tr><td class="col-start"><bdi dir="ltr">${h(r[0])}</bdi></td><td class="num mono"><bdi dir="ltr">${h(r[1]??'-')}</bdi></td><td class="num mono"><strong><bdi dir="ltr">${h(r[2]??'-')}</bdi></strong></td></tr>`).join('');
 const cars=Object.entries(bm.carriers||{}).map(([k,v])=>`<span class="badge ${v.status==='tested'?'b-ok':'b-info'} mono" dir="ltr">${h(k)}: ${h(v.status)}${v.throughput_mbps!=null?' · '+h(v.throughput_mbps)+' Mbps':''}</span>`).join(' ');
 const diags=(rep.diagnostics||[]).map(d=>`<div class="tuner-alert"><strong class="mono">${h(d.code)}</strong> — ${h(d.detail)}</div>`).join('');
 const abDelta=isAb&&rep.delta?`<div class="tuner-live-strip" style="margin-bottom:10px"><span class="badge ${rep.delta.goal_score_diff>=0?'b-ok':'b-warn'} mono" dir="ltr">${h(t('tuner_ab_delta'))}: TP ${rep.delta.throughput_pct>=0?'+':''}${h(rep.delta.throughput_pct)}% · RTT ${rep.delta.loaded_rtt_p95_diff_ms>=0?'+':''}${h(rep.delta.loaded_rtt_p95_diff_ms)}ms · Score ${rep.delta.goal_score_diff>=0?'+':''}${h(rep.delta.goal_score_diff)}</span></div>`:'';
 return `<section class="card sec">
  <div class="sec-head-row"><h4>${h(t('tuner_results'))}${isAb&&rep.profile_name?' — '+h(rep.profile_name):''}</h4>
   ${rep.profile_b64?`<div class="btns">
    <button class="gh" type="button" onclick="copyTunerJson()">${h(t('tuner_copy_json'))}</button>
    <button class="gh" type="button" onclick="copyTunerBase64()">${h(t('tuner_copy_b64'))}</button>
    <button class="s" type="button" onclick="saveTunerProfileToLib()">${h(t('tuner_save_lib'))}</button>
    <button class="g" type="button" onclick="applyTunerProfileBoth('','')">${h(t('tuner_apply_both'))}</button>
    <button class="r" type="button" onclick="rollbackTunerBoth()">${h(t('tuner_rollback_both'))}</button>
   </div>`:''}</div>
  ${abDelta}
  <div class="tuner-metrics">
   <div class="tuner-score"><div class="k">Balanced</div><div class="v">${h(ws.balanced??'-')}</div></div>
   <div class="tuner-score"><div class="k">Low Latency</div><div class="v">${h(ws['low-latency']??'-')}</div></div>
   <div class="tuner-score"><div class="k">Max Throughput</div><div class="v">${h(ws['max-throughput']??'-')}</div></div>
   <div class="tuner-score"><div class="k">Anti-Loss</div><div class="v">${h(ws['anti-loss']??'-')}</div></div>
  </div>
  <div class="table-wrap"><table class="tuner-tbl tuner-res-tbl"><thead><tr><th class="col-start">Metric</th><th class="num">${h(t('tuner_baseline'))}</th><th class="num">${h(t('tuner_winner'))}</th></tr></thead><tbody>${rows}</tbody></table></div>
  ${cars?`<div class="tuner-sec-lbl">${h(t('tuner_carriers'))}</div><div class="bstrip">${cars}</div>`:''}
  ${diags?`<div class="tuner-sec-lbl">${h(t('tuner_diagnostics'))}</div>${diags}`:''}
  ${rep.profile_b64?`<textarea class="tuner-code" readonly>${h(rep.profile_b64)}</textarea>`:''}
 </section>`;
}
function _renderTunerLibraryRows(){
 const list=TUNER_STATE.profiles||[];
 if(!list.length)return `<div class="empty">${h(t('tuner_empty_lib'))}</div>`;
 return list.map((p,idx)=>{
  const tags=Object.entries(p.tags||{}).filter(([,v])=>v).map(([k,v])=>`${k}:${v}`).join(' · ');
  const tp=p.summary&&p.summary.throughput_mbps!=null?`${p.summary.throughput_mbps} Mbps`:'';
  return `<div class="tuner-prof-row">
   <div class="tuner-prof-meta"><strong>${h(p.name||p.id)}</strong>${tags?`<span class="badge b-ws mono" dir="ltr">${h(tags)}</span>`:''}${tp?`<span class="badge b-ok mono" dir="ltr">${h(tp)}</span>`:''}</div>
   <div class="btns">
    <button class="gh" type="button" onclick="copyTunerLibItem(${idx},'json')">JSON</button>
    <button class="gh" type="button" onclick="copyTunerLibItem(${idx},'b64')">Base64</button>
    <button class="s" type="button" onclick="testTunerLibItem(${idx})">${h(t('tuner_test_ab'))}</button>
    <button class="g" type="button" onclick="applyTunerLibItem(${idx})">${h(t('tuner_apply_both'))}</button>
    <button class="r" type="button" onclick="deleteTunerLibItem(${idx})">×</button>
   </div></div>`;
 }).join('');
}
function renderTunerPage(){
 const irs=iranServers(), nds=SERVERS.filter(s=>s.role==='node');
 if(!TUNER_STATE.iran&&irs.length)TUNER_STATE.iran=irs[0].name;
 if(!TUNER_STATE.node&&nds.length)TUNER_STATE.node=nds[0].name;
 const pg=$('page'); if(!pg)return;
 const running=!!TUNER_STATE.activeJobId;
 const irOpts=irs.map(s=>`<option value="${h(s.name)}"${s.name===TUNER_STATE.iran?' selected':''}>${h(s.name)}</option>`).join('');
 const ndOpts=nds.map(s=>`<option value="${h(s.name)}"${s.name===TUNER_STATE.node?' selected':''}>${h(s.name)}</option>`).join('');
 const curJid=TUNER_STATE.job&&TUNER_STATE.job.job_id;
 const recentList=Array.isArray(TUNER_STATE.jobs)?TUNER_STATE.jobs:[];
 const recentHtml=(recentList.length>1||(!TUNER_STATE.job&&recentList.length>0))
  ?`<div class="tuner-jobs-bar"><span class="muted">${h(t('tuner_recent_jobs'))}:</span>`+recentList.slice(0,6).map(jb=>{
   const safeId=String(jb.job_id||'').replace(/[^A-Za-z0-9_-]/g,'');
   const act=safeId&&safeId===curJid?' active':'';
   const lbl=`${jb.iran||'?'}→${jb.node||'?'} · ${jb.status}${jb.best_so_far?' ('+jb.best_so_far+')':''}`;
   return `<button type="button" class="tuner-job-pill${act}" onclick="selectTunerJob('${h(safeId)}')">${h(lbl)}</button>`;
  }).join('')+'</div>':'';
 pg.innerHTML=`<div class="ptitle"><h2>${h(t('tuner_title'))}</h2></div>
  <div class="tuner-grid">
   <section class="card sec">
    <p class="tuner-sub">${h(t('tuner_sub'))}</p>
    <div class="tuner-form">
     <div class="field"><label for="tn_iran">${h(t('tuner_iran'))}</label><select id="tn_iran">${irOpts}</select></div>
     <div class="field"><label for="tn_node">${h(t('tuner_node'))}</label><select id="tn_node">${ndOpts}</select></div>
     <div class="field"><label for="tn_mode">${h(t('tuner_mode'))}</label><select id="tn_mode">
      <option value="brutal"${TUNER_STATE.mode==='brutal'?' selected':''}>${h(t('tuner_mode_brutal'))}</option>
      <option value="safe"${TUNER_STATE.mode==='safe'?' selected':''}>${h(t('tuner_mode_safe'))}</option>
     </select></div>
     <div class="field"><label for="tn_goal">${h(t('tuner_goal'))}</label><select id="tn_goal">
      <option value="balanced"${TUNER_STATE.goal==='balanced'?' selected':''}>${h(t('tuner_goal_balanced'))}</option>
      <option value="low-latency"${TUNER_STATE.goal==='low-latency'?' selected':''}>${h(t('tuner_goal_low_latency'))}</option>
      <option value="max-throughput"${TUNER_STATE.goal==='max-throughput'?' selected':''}>${h(t('tuner_goal_max_throughput'))}</option>
      <option value="anti-loss"${TUNER_STATE.goal==='anti-loss'?' selected':''}>${h(t('tuner_goal_anti_loss'))}</option>
     </select></div>
     <div class="field"><label for="tn_iran_dc">${h(t('tuner_iran_dc'))}</label><input id="tn_iran_dc" type="text" value="${h(TUNER_STATE.iran_dc)}"></div>
     <div class="field"><label for="tn_node_dc">${h(t('tuner_node_dc'))}</label><input id="tn_node_dc" type="text" value="${h(TUNER_STATE.node_dc)}"></div>
    </div>
    <div class="tuner-actions">
     <label class="sw"><input type="checkbox" id="tn_deep"${TUNER_STATE.deep?' checked':''}><span>${h(t('tuner_deep'))}</span></label>
     <div class="btns">
      <button class="g" type="button" onclick="startTunerJob()"${running?' disabled':''}>${h(t('tuner_start'))}</button>
      ${running?`<button class="r" type="button" onclick="cancelTunerJob()">${h(t('tuner_stop'))}</button>`:''}
     </div>
    </div>${recentHtml}
   </section>
   ${TUNER_STATE.job?`<section class="card sec" id="tn_prog_box">${_renderTunerProgressBody()}</section>`:''}
   ${_renderTunerResultsCard()}
   <section class="card sec">
    <div class="sec-head-row"><h4>${h(t('tuner_library'))}</h4>
     <button class="s" type="button" onclick="openImportTunerModal()">${h(t('tuner_import_btn'))}</button></div>
    <div id="tn_lib_box">${_renderTunerLibraryRows()}</div>
   </section>
  </div>`;
 if(!TUNER_STATE.jobsLoaded)loadTunerJobs();
 else if(TUNER_STATE.activeJobId&&!TUNER_STATE.pollTimer)pollTunerJob(TUNER_STATE.activeJobId);
 if(TUNER_STATE.profiles===null)loadTunerProfiles();
}

function prefersReducedMotion(){
 return typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
}
function closeMoreMenu(d,instant){
 const menu=(d&&d._menu)||(d&&d.querySelector&&d.querySelector('.more-menu'));
 if(d)d.open=false;
 if(!menu)return;
 clearTimeout(menu._closeTimer);
 menu._closeTimer=null;
 const finish=()=>{
  menu.classList.remove('fixed-menu','more-menu-portal','is-open','is-closing');
  menu.style.top='';
  menu.style.left='';
  menu.style.transformOrigin='';
  delete menu.dataset.side;
  if(d&&d.isConnected){if(menu.parentElement!==d)d.appendChild(menu);}
  else if(menu.parentElement===document.body){menu.remove();}
 };
 if(instant||!menu.classList.contains('more-menu-portal')||prefersReducedMotion()){
  finish();
  return;
 }
 menu.classList.remove('is-open');
 menu.classList.add('is-closing');
 menu._closeTimer=setTimeout(finish,130);
}
function closeAllMoreMenus(except=null,instant=false){
 document.querySelectorAll('details.more[open]').forEach(d=>{if(d!==except)closeMoreMenu(d,instant);});
 document.querySelectorAll('body > .more-menu-portal').forEach(menu=>{
  if(except&&menu._owner===except)return;
  if(menu._owner)closeMoreMenu(menu._owner,instant);
  else menu.remove();
 });
}
function positionMoreMenu(d){
 const menu=(d&&d._menu)||(d&&d.querySelector&&d.querySelector('.more-menu'));
 const sum=d&&d.querySelector&&d.querySelector('summary');
 if(!menu||!sum)return;
 d._menu=menu;
 menu._owner=d;
 if(!d.open){closeMoreMenu(d,false);return;}
 closeAllMoreMenus(d,true);
 clearTimeout(menu._closeTimer);
 menu._closeTimer=null;
 if(document.body&&menu.parentElement!==document.body)document.body.appendChild(menu);
 menu.classList.remove('is-closing','is-open');
 menu.classList.add('fixed-menu','more-menu-portal');
 menu.style.top='0px';
 menu.style.left='0px';
 const origin=menu.getBoundingClientRect();
 const sr=sum.getBoundingClientRect(), mr=menu.getBoundingClientRect();
 const isRtl=document.documentElement.dir==='rtl';
 const openBelow=(sr.bottom+6+mr.height<=window.innerHeight-12)||(sr.top-mr.height-6<12);
 const top=openBelow?Math.min(sr.bottom+6,window.innerHeight-mr.height-12):Math.max(12,sr.top-mr.height-6);
 let left=isRtl?sr.left:(sr.right-mr.width);
 left=Math.max(12,Math.min(left,window.innerWidth-mr.width-12));
 menu.style.top=(top-origin.top)+'px';
 menu.style.left=(left-origin.left)+'px';
 menu.style.transformOrigin=(openBelow?'top ':'bottom ')+(isRtl?'left':'right');
 menu.dataset.side=openBelow?'bottom':'top';
 requestAnimationFrame(()=>{if(d.open&&menu.parentElement)menu.classList.add('is-open');});
}
function toggleDiagDetails(d,forceOpen){
 if(!d)return;
 const sum=d.querySelector(':scope > summary');
 const body=sum&&sum.nextElementSibling;
 const willOpen=typeof forceOpen==='boolean'?forceOpen:(!d.open||d.dataset.closing==='1');
 if(willOpen===d.open&&d.dataset.closing!=='1'&&d.dataset.opening!=='1')return;
 const startH=d.offsetHeight;
 if(d._anim){try{d._anim.cancel();}catch(_){}d._anim=null;}
 if(d._bodyAnim){try{d._bodyAnim.cancel();}catch(_){}d._bodyAnim=null;}
 if(!sum||!body||typeof d.animate!=='function'||prefersReducedMotion()){
  delete d.dataset.closing;
  delete d.dataset.opening;
  d.style.overflow='';
  d.open=willOpen;
  if(willOpen&&body&&typeof body.animate==='function'){
   body.animate([{opacity:0},{opacity:1}],{duration:120,easing:'ease'});
  }
  return;
 }
 if(willOpen){
  d.dataset.closing='0';
  d.dataset.opening='1';
  d.style.overflow='hidden';
  d.open=true;
  const endH=d.offsetHeight;
  const anim=d.animate([{height:startH+'px'},{height:endH+'px'}],{duration:240,easing:'cubic-bezier(0.23, 1, 0.32, 1)'});
  d._anim=anim;
  d._bodyAnim=body.animate([{opacity:0,transform:'translateY(-6px)'},{opacity:1,transform:'translateY(0)'}],{duration:220,easing:'cubic-bezier(0.23, 1, 0.32, 1)'});
  anim.onfinish=()=>{
   if(d._anim!==anim)return;
   d._anim=null;
   d._bodyAnim=null;
   d.style.overflow='';
   delete d.dataset.opening;
   delete d.dataset.closing;
  };
  anim.oncancel=()=>{if(d._anim===anim){d.style.overflow='';}};
 }else{
  d.dataset.opening='0';
  d.dataset.closing='1';
  d.style.overflow='hidden';
  const cs=typeof getComputedStyle==='function'?getComputedStyle(d):null;
  const borderY=cs?((parseFloat(cs.borderTopWidth)||0)+(parseFloat(cs.borderBottomWidth)||0)):2;
  const endH=sum.offsetHeight+borderY;
  const anim=d.animate([{height:startH+'px'},{height:endH+'px'}],{duration:180,easing:'cubic-bezier(0.23, 1, 0.32, 1)'});
  d._anim=anim;
  d._bodyAnim=body.animate([{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(-4px)'}],{duration:150,easing:'cubic-bezier(0.23, 1, 0.32, 1)'});
  anim.onfinish=()=>{
   if(d._anim!==anim)return;
   d._anim=null;
   d._bodyAnim=null;
   d.open=false;
   d.style.overflow='';
   delete d.dataset.closing;
   delete d.dataset.opening;
  };
  anim.oncancel=()=>{if(d._anim===anim){d.style.overflow='';}};
 }
}
function filterTableRows(wrapId,query){
 const wrap=$(wrapId); if(!wrap)return;
 const q=String(query||'').trim().toLowerCase();
 wrap.querySelectorAll('tr').forEach((tr,idx)=>{
  if(tr.querySelector('th')&&idx===0)return;
  if(tr.closest('thead'))return;
  tr.style.display=(!q||tr.textContent.toLowerCase().includes(q))?'':'none';
 });
}
function bindDelegatedEvents(){
 if(typeof document==='undefined'||document._rthBound)return;
 document._rthBound=true;
 document.addEventListener('toggle',e=>{
  const d=e.target;
  if(d&&d.matches&&d.matches('details.more'))positionMoreMenu(d);
 },true);
 document.addEventListener('click',e=>{
  const tgt=e.target&&e.target.closest?e.target:null;
  const curMenu=tgt?tgt.closest('.more-menu'):null;
  const curMore=(tgt&&tgt.closest('details.more'))||(curMenu&&curMenu._owner)||null;
  closeAllMoreMenus(curMore,false);
  if(!tgt)return;
  const diagSum=tgt.closest('details.diag-sec > summary');
  if(diagSum){e.preventDefault();toggleDiagDetails(diagSum.parentElement);return;}
  const roleBtn=tgt.closest('[data-flt-role]');
  if(roleBtn){setDashFilter({role:roleBtn.dataset.fltRole});return;}
  const stBtn=tgt.closest('[data-flt-st]');
  if(stBtn){setDashFilter({status:stBtn.dataset.fltSt});return;}
  const svcBtn=tgt.closest('[data-svc-call]');
  if(svcBtn){
   const menu=svcBtn.closest('.more-menu');
   const m=(menu&&menu._owner)||svcBtn.closest('details.more');
   if(m)closeMoreMenu(m,true);
   const ds=svcBtn.dataset;
   if(ds.svcCall==='serviceControl')serviceControl(ds.server,ds.name,ds.action);
   else if(ds.svcCall==='nodeServiceAction')nodeServiceAction(ds.server,ds.name,ds.action);
   return;
  }
  const actBtn=tgt.closest('[data-act]');
  if(!actBtn)return;
  const ds=actBtn.dataset, srv=ds.srv, nm=ds.name, id=ds.id;
  switch(ds.act){
   case 'show_node': run(srv,'show_node',{name:nm}); break;
   case 'wire_node': wireNode(srv,nm); break;
   case 'edit_node': editNode(srv,nm); break;
   case 'rename_node': renameNode(srv,nm); break;
   case 'rotate_node': if(confirmT('cf_rotate',nm))run(srv,'rotate_node',{name:nm}); break;
   case 'rm_node': rmNode(srv,nm); break;
   case 'game_rm': run(srv,'game_rm',{name:nm}); break;
   case 'rm_bh_svc': rmBhSvc(srv,nm); break;
   case 'rm_svc': rmSvc(srv,nm); break;
   case 'up_restart': run(srv,'upstream_restart',{id}); break;
   case 'up_status': run(srv,'upstream_status',{id}); break;
   case 'up_logs': run(srv,'upstream_logs',{id}); break;
   case 'up_add_svc': upAddSvc(srv,id); break;
   case 'up_rm': upRm(srv,id); break;
   case 'up_rm_svc': upRmSvc(srv,id,nm); break;
  }
 });
 document.addEventListener('input',e=>{
  const el=e.target;
  if(el&&el.dataset&&el.dataset.tblFilter)filterTableRows(el.dataset.tblFilter,el.value);
 });
 document.addEventListener('change',e=>{
  const el=e.target;
  if(!el||!el.dataset)return;
  if(el.dataset.icarIran!=null)setIranNodeCarrier(el.dataset.icarIran,el.dataset.icarName,el.value,el.dataset.icarCur);
  else if(el.dataset.upcarSrv!=null)setUpCarrier(el.dataset.upcarSrv,el.dataset.upcarId,el.value,el.dataset.upcarCur);
 });
 document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&String(e.key).toLowerCase()==='k'&&TOKEN){
   e.preventDefault();
   const d=$('cmdk');
   if(d&&d.open)closeCmdPalette();
   else openCmdPalette();
   return;
  }
  if(e.key==='Escape')closeAllMoreMenus(null,true);
 });
 if(typeof window!=='undefined'&&window.addEventListener){
  window.addEventListener('scroll',e=>{if(e&&e.target&&e.target.closest&&e.target.closest('.more-menu'))return;closeAllMoreMenus(null,true);},true);
  window.addEventListener('resize',()=>closeAllMoreMenus(null,true));
  window.addEventListener('storage',e=>{
   if(e.key==='rh_theme'){THEME_PREF=(e.newValue==='light'||e.newValue==='dark')?e.newValue:'';applyStatic();}
   else if(e.key==='rh_sb_collapsed'){applyStatic();}
  });
  if(typeof matchMedia==='function'){
   const mq=matchMedia('(prefers-color-scheme:light)');
   if(mq&&mq.addEventListener)mq.addEventListener('change',()=>{if(!THEME_PREF)applyStatic();});
  }
 }
}
// refresh-e khodkar: faghat overview-haye safhe-ye faal (server SSH kamtar mikhorad)
setInterval(()=>{if($('auto')&&$('auto').checked&&TOKEN&&!document.querySelector('details.more[open], .more-menu-portal'))pollByPage();},20000);
bindDelegatedEvents();
shell();
