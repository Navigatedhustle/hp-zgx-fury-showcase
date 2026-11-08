/* Customer identity belongs to the server, never browser storage, exports or previews. */
(() => {
 if(window.FurySkinLoaded)return;window.FurySkinLoaded=true;
 const esc=window.FuryUI.esc,embedded=self!==top,root=document.documentElement;
 let disabled=false,originalHero=null;
 function disable(){
  disabled=true;
  root.classList.remove('skin-controls-ready','skin-dark-surfaces','skin-brand-red','skin-fade');
  for(const key of [...root.style])if(themeKeys.has(key))root.style.removeProperty(key);
  const bar=document.querySelector('.mc-telemetry'),metrics=bar?.querySelector('.skin-metrics');
  if(metrics){bar.querySelector('.skin-top-row')?.remove();while(metrics.firstChild)bar.append(metrics.firstChild);metrics.remove()}
  document.querySelector('.skin-dialog')?.remove();document.getElementById('skin-room')?.remove();
  document.querySelectorAll('.skin-launch-sample').forEach(n=>n.remove());
  if(originalHero!==null){const hero=document.querySelector('.mc-hero h1');if(hero)hero.innerHTML=originalHero}
 }
 const themeKeys=new Set('--mc-bg --mc-panel --mc-raise --mc-blue --mc-cyan --mc-line --mc-text --mc-muted --bg --page --panel --surface --surface-raised --action --accent --border --text --subtle --on-action --focus'.split(' '));
 try {
 const paletteIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-4c-1-1 0-2 1-2h3a3 3 0 0 0 3-3 9 9 0 0 0-9-9Z"/><circle cx="7" cy="10" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7" r="1"/></svg>';
 let liveTelemetry=null;
 let state={active:null},allPacks={},recent=[],selected=null,job=null,pollTimer=null,lookupEpoch=0,manualName='',previewTheme=null,overrides={},packChoice='default',lastRevision=null;
 const sheet=document.createElement('link');sheet.rel='stylesheet';sheet.href='/showcase-assets/skin.css';sheet.onerror=disable;document.head.append(sheet);
 async function api(path,data,options={}){
  const response=await fetch('/skin/'+path,{cache:'no-store',signal:AbortSignal.timeout(8000),...options,...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
  const value=await response.json();if(!response.ok)throw Error(value.detail||'Skin service unavailable');return value;
 }
 const frameOrigin=window.FuryUI.addr('/');
 function logo(value,cls='skin-logo'){return value?'<img class="'+cls+(value.plate?' skin-plate':'')+'" src="'+esc(value.logo)+'" alt="'+esc(value.name)+' logo">':''}
 const topbar=document.querySelector('.mc-telemetry');
 if(topbar){
  const metrics=document.createElement('div');metrics.className='skin-metrics';while(topbar.firstChild)metrics.append(topbar.firstChild);topbar.append(metrics);
  const row=document.createElement('div');row.className='skin-top-row';row.innerHTML='<div class="skin-identity"><img src="/showcase-assets/hp-logo-keyline.png" alt="HP"><b>HP ZGX Fury</b><div class="skin-prepared" id="skin-prepared"></div></div><div class="skin-actions"><button id="skin-customize" type="button">'+paletteIcon+'<span class="skin-customize-label">Customize for customer</span></button><details class="skin-menu" id="skin-menu"><summary>Skins ▾</summary><div id="skin-recent"></div></details></div>';topbar.prepend(row);
 }
 const hero=document.querySelector('.mc-hero h1'),heroOriginal=hero?.innerHTML;originalHero=heroOriginal??null;
 if(hero){const card=document.createElement('section');card.className='skin-room';card.id='skin-room';card.innerHTML='<div><h2>Who is in the room today?</h2><p>Prepare this HP ZGX Fury for your customer. On screen only.</p></div><button type="button" id="skin-room-open">'+paletteIcon+' Customize for customer</button>';document.querySelector('.mc-facts')?.after(card)}
 const dialog=document.createElement('dialog');dialog.className='skin-dialog';dialog.setAttribute('aria-labelledby','skin-title');dialog.innerHTML='<header><div><small>HP ZGX FURY / CUSTOMER SKIN</small><h2 id="skin-title">Prepare the room</h2></div><button type="button" class="secondary" id="skin-close" aria-label="Close customer customization">Close ✕</button></header><div class="skin-content" id="skin-content"></div>';document.body.append(dialog);
 const content=dialog.querySelector('#skin-content');
 function show(html){content.innerHTML=html;content.scrollTop=0;dialog.scrollTop=0;if(!dialog.open)dialog.showModal();content.querySelector('input')?.focus()}
 function error(e){let node=content.querySelector('.skin-error');if(!node){node=document.createElement('p');node.className='skin-error';node.setAttribute('role','alert');content.append(node)}node.textContent=e.message||String(e)}
 function counter(){return '<p class="skin-counter">Public web lookups: <span id="skin-web-count">'+esc(state.public_web_lookups??'unknown')+'</span> · External AI API calls: <span id="skin-external-count">measured in telemetry</span></p>'}
 async function cancelLookup(){++lookupEpoch;clearTimeout(pollTimer);const pending=job;job=null;if(pending?.id&&pending.status!=='cancelled'){try{await api('research/'+pending.id+'/cancel',{})}catch{}}}
 document.getElementById('skin-close').onclick=()=>{dialog.close();cancelLookup()};dialog.addEventListener('cancel',()=>cancelLookup());
 function first(){if(disabled)return;cancelLookup();selected=null;overrides={};show('<p class="mc-eyebrow">01 / WHO</p><h3>Who is in the room today?</h3><p>HP ZGX Fury stays visible. The customer identity is a presentation wrapper.</p><form class="skin-form" id="skin-who"><label>Which customer is this demo for?<input name="name" id="skin-name" maxlength="80" required autocomplete="off" value="'+esc(manualName)+'"></label><label>Official website (optional)<input name="website" id="skin-website" type="text" inputmode="url" placeholder="https://official-domain.example" autocomplete="off"></label><div class="skin-buttons"><button>Research identity and logos ↗</button><button type="button" class="secondary" id="skin-manual">Use a logo offline</button></div></form>'+counter());
  document.getElementById('skin-who').onsubmit=async e=>{e.preventDefault();manualName=document.getElementById('skin-name').value.trim();const epoch=lookupEpoch;try{const found=await api('research',{name:manualName,website:document.getElementById('skin-website').value.trim()||null});if(epoch!==lookupEpoch){api('research/'+found.id+'/cancel',{}).catch(()=>{});return}job=found;researchView();poll()}catch(e){if(epoch===lookupEpoch)error(e)}};
  document.getElementById('skin-manual').onclick=()=>{manualName=document.getElementById('skin-name').value.trim();if(!manualName){error(Error('Enter a customer name first.'));return}uploadView()};
 }
 function researchView(){show('<p class="mc-eyebrow">02 / RESEARCH</p><h3>Finding an official identity</h3><p>Public sources only. Model decisions run on this Fury.</p><div class="skin-route" id="skin-route"></div><ol class="skin-progress" id="skin-steps" aria-live="polite"></ol><p id="skin-elapsed" class="mc-mono"></p><button type="button" class="secondary" id="skin-cancel">Cancel</button>'+counter());document.getElementById('skin-cancel').onclick=()=>first();renderProgress()}
 function renderProgress(){if(!job)return;const route=document.getElementById('skin-route');if(route)route.textContent=(job.routing?.model||'Selecting local lane')+' · '+(job.routing?.reason||'DeepSeek if free, otherwise Qwen')+(job.routing?.note?' · '+job.routing.note:'');const list=document.getElementById('skin-steps');if(list)list.innerHTML=(job.steps||[]).map(s=>'<li><span>'+esc(s.label)+'</span><time>'+Number(s.elapsed).toFixed(1)+'s</time></li>').join('');const elapsed=document.getElementById('skin-elapsed');if(elapsed)elapsed.textContent='Elapsed '+Number(job.elapsed).toFixed(1)+' seconds';const count=document.getElementById('skin-web-count');if(count)count.textContent=job.public_web_lookups??state.public_web_lookups??'unknown'}
 async function poll(){const epoch=lookupEpoch,id=job?.id;if(!id)return;try{const found=await api('research/'+id);if(epoch!==lookupEpoch||job?.id!==id)return;job=found;state.public_web_lookups=job.public_web_lookups;renderProgress();if(job.status==='researching')pollTimer=setTimeout(poll,250);else if(job.status==='entities')entitiesView();else if(job.status==='candidates')candidatesView();else if(job.status==='manual')uploadView(job.message);else first()}catch(e){if(epoch===lookupEpoch)error(e)}}
 function entitiesView(){show('<p class="mc-eyebrow">03 / CONFIRM IDENTITY</p><h3>Which organization do you mean?</h3><p>Confirm the official domain before selecting a logo.</p><div class="skin-entities">'+job.entities.slice(0,4).map(e=>'<article class="skin-entity"><strong>'+esc(e.name)+'</strong><p>'+esc(e.description)+'</p><small>'+esc(e.domain||'No official domain listed')+'</small><div class="skin-buttons"><button type="button" data-entity="'+esc(e.qid)+'">Choose this entity</button></div></article>').join('')+'</div><div class="skin-buttons"><button class="secondary" id="skin-different">Try a different name</button></div>'+counter());content.querySelectorAll('[data-entity]').forEach(b=>b.onclick=async()=>{const epoch=lookupEpoch;try{const found=await api('research/'+job.id+'/entity',{qid:b.dataset.entity});if(epoch!==lookupEpoch)return;job=found;researchView();poll()}catch(e){if(epoch===lookupEpoch)error(e)}});document.getElementById('skin-different').onclick=first}
 function candidatesView(){show('<p class="mc-eyebrow">03 / CONFIRM LOGO</p><h3>Choose the mark you recognize</h3><p>Official source candidates, shown unchanged on light and dark. The presenter confirms identity and permission.</p><div class="skin-candidates">'+job.candidates.slice(0,6).map((c,i)=>'<article class="skin-candidate"><div class="skin-tiles"><div class="skin-tile skin-light"><img src="'+esc(c.logo)+'" alt="Logo candidate '+(i+1)+' on light"></div><div class="skin-tile skin-dark"><img src="'+esc(c.logo)+'" alt="Logo candidate '+(i+1)+' on dark"></div></div><small>'+esc(c.source)+'</small><button type="button" data-logo="'+i+'">Use this logo</button></article>').join('')+'</div><div class="skin-buttons"><button class="secondary" id="skin-upload-other">None of these — upload</button><button class="secondary" id="skin-different">Try a different name</button></div>'+counter());content.querySelectorAll('[data-logo]').forEach(b=>b.onclick=()=>{selected=job.candidates[Number(b.dataset.logo)];packChoice=selected.pack;overrides={};preview()});document.getElementById('skin-upload-other').onclick=()=>uploadView();document.getElementById('skin-different').onclick=first}
 function uploadView(message='Choose a PNG or SVG. Colors are extracted locally, with no internet required.'){
  show('<p class="mc-eyebrow">03 / MANUAL LOGO</p><h3>Bring a logo from this station</h3><p role="status">'+esc(message)+'</p><div class="skin-upload"><label>PNG or SVG logo · maximum 2 MB<input id="skin-file" type="file" accept="image/png,image/svg+xml,.png,.svg"></label></div><p>Use the original mark. It is never recolored, cropped or embedded in a generated application.</p><div class="skin-buttons"><button class="secondary" id="skin-different">Try a different name</button></div>'+counter());document.getElementById('skin-different').onclick=first;
  document.getElementById('skin-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>2*1024*1024){error(Error('Logo exceeds two megabytes.'));return}const epoch=lookupEpoch;try{const response=await fetch('/skin/upload',{signal:AbortSignal.timeout(15000),method:'POST',headers:{'Content-Type':file.name.toLowerCase().endsWith('.svg')?'image/svg+xml':'image/png','x-skin-name':encodeURIComponent(manualName)},body:file});const value=await response.json();if(!response.ok)throw Error(value.detail||'Upload failed');if(epoch!==lookupEpoch)return;selected=value;packChoice=value.pack;overrides={};preview()}catch(e){error(e)}};
 }
 function mini(label,value,theme){
  const defaults=theme?.monochrome?{'--mc-bg':'#060c17','--mc-panel':'#101c2e','--mc-line':'#263d57','--mc-blue':'#4c9cff','--mc-cyan':'#69d9ee','--mc-text':'#edf5ff','--mc-muted':'#9eb0c7'}:{};
  const vars=Object.entries({...defaults,...theme?.variables}).filter(([k,v])=>themeKeys.has(k)&&/^#[0-9a-f]{6}$/i.test(v)).map(([k,v])=>k+':'+v).join(';');
  const level=liveTelemetry?.gpu?.utilization,known=typeof level==='number'&&Number.isFinite(level),percent=known?Math.min(100,Math.max(0,level)):0;
  return '<section class="skin-mini" style="'+vars+'"><header><b>HP ZGX Fury</b>'+logo(value)+'</header><div><div class="skin-mini-label">'+label+'</div><h4>Quick Demo Launcher</h4><p>Atlas · Fictional insights, on this Fury</p><span class="skin-status">● Healthy status example</span><h4>'+(known?Math.round(level)+'%':'—')+' <small>GPU utilization · measured</small></h4><div class="mc-track"><i style="width:'+percent+'%"></i></div></div></section>';
 }
 function preview(){previewTheme=selected.theme;show('<p class="mc-eyebrow">04 / PREVIEW</p><h3>HP ZGX Fury, prepared for '+esc(selected.name)+'</h3><div class="skin-swatches">'+selected.theme.swatches.map(c=>'<span class="skin-swatch" style="background:'+esc(c)+'" title="'+esc(c)+'"></span>').join('')+'</div><div class="skin-preview-grid" id="skin-preview-grid"></div><p id="skin-theme-note"></p><div class="skin-checks" id="skin-checks"></div><div class="skin-tweaks"><label>Primary color<input type="color" id="skin-primary" value="'+esc(selected.theme.primary)+'"></label><label>Accent color<input type="color" id="skin-accent" value="'+esc(selected.theme.accent)+'"></label><label>Fictional industry sample pack<select id="skin-pack">'+Object.entries(allPacks).map(([id,p])=>'<option value="'+esc(id)+'" '+(id===packChoice?'selected':'')+'>'+esc(p.label)+'</option>').join('')+'</select></label></div><p>Samples use fictional data. Customer marks stay on screen and out of downloads. '+(selected.plate?'A light plate protects this logo’s contrast.':'The original logo is kept unchanged.')+'</p><div class="skin-buttons"><button id="skin-apply">Apply across stations ↗</button><button class="secondary" id="skin-back">Back</button></div>'+counter());renderPreview();
  let sequence=0;const previewEpoch=lookupEpoch;const tweak=async()=>{const n=++sequence;overrides={primary:document.getElementById('skin-primary').value,accent:document.getElementById('skin-accent').value};try{const value=await api('preview',{id:selected.id,...overrides});if(n===sequence&&previewEpoch===lookupEpoch&&document.getElementById('skin-preview-grid')){previewTheme=value.theme;renderPreview()}}catch(e){error(e)}};
  document.getElementById('skin-primary').oninput=tweak;document.getElementById('skin-accent').oninput=tweak;document.getElementById('skin-pack').onchange=e=>packChoice=e.target.value;
  document.getElementById('skin-back').onclick=()=>job?.candidates?.length?candidatesView():uploadView();document.getElementById('skin-apply').onclick=async()=>{try{const value=await api('apply',{id:selected.id,pack:packChoice,...overrides});update(value,{animate:true});dialog.close();await refresh()}catch(e){error(e)}};
 }
 function renderPreview(){const grid=document.getElementById('skin-preview-grid');if(!grid)return;grid.innerHTML=mini('Current theme',state.active,state.active?.theme)+mini('Proposed theme',selected,previewTheme);document.getElementById('skin-theme-note').textContent=previewTheme.note;const c=previewTheme.contrast;document.getElementById('skin-checks').textContent='✓ Text '+c.text.toFixed(2)+':1 / 4.5 required · ✓ Accent '+c.accent.toFixed(2)+':1 / 4.5 · ✓ UI '+c.ui.toFixed(2)+':1 / 3.0 · Status colors unchanged';}
 let appliedKeys=[];
 function update(value,options={}){if(disabled)return;try{applyUpdate(value,options)}catch{disable()}}
 function applyUpdate(value,{animate=false}={}){
  if(!value||typeof value!=='object')return;
  const active=value.active,vars=active?.theme?.variables;
  if(active&&(!vars||typeof vars!=='object'||typeof active.name!=='string'||active.name.length>80||!/^\/skin\/logo\/[a-f0-9]{24}\/logo\.(svg|png)$/.test(active.logo)||Object.entries(vars).some(([k,v])=>!themeKeys.has(k)||typeof v!=='string'||!/^#[0-9a-f]{6}$/i.test(v))))value={...value,active:null,sample_pack:null,revision:'invalid-default'};if(state.active&&!value.active)manualName='';state={...state,...value};if(value.active&&value.sample_pack)allPacks[value.active.pack]=value.sample_pack;if(value.revision===lastRevision)return;lastRevision=value.revision;
  const swap=()=>{
   appliedKeys.forEach(k=>root.style.removeProperty(k));const vars=value.active?.theme?.variables||{};appliedKeys=Object.keys(vars).filter(k=>themeKeys.has(k));for(const k of appliedKeys)if(/^#[0-9a-f]{6}$/i.test(vars[k]))root.style.setProperty(k,vars[k]);
   // Only server JSON supplies colors; reset restores native shell tokens.
   root.classList.toggle('skin-dark-surfaces',Boolean(value.active&&appliedKeys.length));root.classList.toggle('skin-brand-red',Boolean(value.active?.theme?.red_brand));
   const prepared=document.getElementById('skin-prepared');if(prepared)prepared.innerHTML=value.active?logo(value.active)+'<span title="'+esc(value.active.name)+'">Prepared for '+esc(value.active.name)+'</span>':'';
   if(hero){const count=document.querySelectorAll('.mc-launch-card[data-demo]').length;hero.innerHTML=value.active?esc(count===8?'Eight':count)+' AI workloads.<br>One HP ZGX Fury. <em>Built for '+esc(value.active.name)+'.</em>':heroOriginal}
  };
  // Color-only transitions cannot cover the launcher or trap pointer input.
  // Background SSE and initial load always swap instantly.
  if(animate&&!matchMedia('(prefers-reduced-motion:reduce)').matches){root.classList.add('skin-fade');setTimeout(()=>root.classList.remove('skin-fade'),500)}
  swap();
  // All retained workspaces, including hidden frames, receive skin-only state.
  document.querySelectorAll('#station-workspaces iframe').forEach(frame=>frame.contentWindow?.postMessage({type:'fury:skin',value},new URL(frame.src).origin));
  renderPack();boothPalette();
 }
 function renderPack(){const pack=allPacks[state.active?.pack||'default'];document.querySelectorAll('.skin-launch-sample').forEach(n=>n.remove());if(!pack||!state.active)return;document.querySelectorAll('.mc-launch-card[data-demo]').forEach(a=>{const key=a.dataset.demo;if(!pack[key])return;const p=document.createElement('p');p.className='skin-launch-sample';p.textContent=pack.label+' sample ready';p.title=pack[key];a.append(p)})}
 async function refresh(){try{const value=await api('state');recent=value.recent||[];allPacks=value.packs||allPacks;update(value);const menu=document.getElementById('skin-recent');if(menu){menu.innerHTML='<a class="skin-default-link" href="/demos?skin=off">Default appearance (safe mode)</a><button id="skin-reset" type="button">Reset to default</button>'+recent.map(c=>'<button type="button" data-cached="'+esc(c.id)+'">'+esc(c.name)+'</button>').join('');document.getElementById('skin-reset').onclick=async()=>{try{update(await api('reset',{}));document.getElementById('skin-menu').open=false}catch(e){error(e)}};menu.querySelectorAll('[data-cached]').forEach(b=>b.onclick=async()=>{try{update(await api('apply',{id:b.dataset.cached}));document.getElementById('skin-menu').open=false}catch(e){error(e)}})}renderPack()}catch{const menu=document.getElementById('skin-recent');if(menu)menu.innerHTML='<a href="/demos?skin=off">Default appearance (safe mode)</a><p>Customization unavailable. The demo is ready.</p>'}}
 document.getElementById('skin-customize')?.addEventListener('click',first);document.getElementById('skin-room-open')?.addEventListener('click',first);
 document.getElementById('skin-menu')?.addEventListener('toggle',e=>{if(e.target.open)refresh()});
 addEventListener('fury:telemetry',e=>{liveTelemetry=e.detail?.telemetry;if(dialog.open&&document.getElementById('skin-preview-grid'))renderPreview();if(e.detail?.skin)update(e.detail.skin);const web=document.getElementById('secure-public-web');if(web)web.textContent=e.detail?.telemetry?.public_web_lookups??'—';const external=document.getElementById('skin-external-count');if(external)external.textContent=e.detail?.telemetry?.external_api_calls??'unavailable'});
 addEventListener('message',e=>{if(embedded&&e.source===parent&&e.origin===new URL(frameOrigin).origin&&e.data?.type==='fury:skin')update(e.data.value)});
 // Forward a chosen generic sample through the existing shell; never submit it.
 const initializedFrames=new WeakMap(),appliedSamples=new Map();let sampleControlsTouched=false;
 if(embedded){
  const customized=e=>{if(e.isTrusted&&e.target.closest('#main input,#main textarea,#main select,#image-drop,#document-drop,#go,#question-form button,[data-sample],[data-prompt],[data-question],[data-persona]'))sampleControlsTouched=true};
  document.addEventListener('input',customized);document.addEventListener('click',customized);document.addEventListener('drop',customized);
 }
 document.addEventListener('click',e=>{
  const a=e.target.closest('.mc-launch-card[data-demo]');if(!a||!state.active)return;const pack=allPacks[state.active.pack];if(!pack||!pack[a.dataset.demo])return;
  setTimeout(()=>{const frame=window.FuryStations?.ensure(a.dataset.demo);if(!frame||initializedFrames.get(frame)===state.active.pack)return;initializedFrames.set(frame,state.active.pack);const send=()=>frame.contentWindow?.postMessage({type:'fury:skin-sample',kind:a.dataset.demo,sample:pack[a.dataset.demo]},new URL(frame.src).origin);frame.addEventListener('load',send,{once:true});send()},0);
 });
 addEventListener('message',e=>{
  if(!embedded||e.source!==parent||e.origin!==new URL(frameOrigin).origin||e.data?.type!=='fury:skin-sample')return;
  const {kind,sample}=e.data;if(typeof sample!=='string'||sample.length>2000)return;
  const apply=()=>{
   if(sampleControlsTouched||appliedSamples.get(kind)===sample||document.querySelector('#status[data-state]:not([data-state="idle"])')||(document.body.dataset.state&&document.body.dataset.state!=='idle'))return;
   const node=document.querySelector(kind==='atlas'?'#question-input':'#prompt');
   if(['atlas','slides','image','video'].includes(kind)&&node){const nativeDefault=kind==='atlas'&&[...document.querySelectorAll('#golden-questions button')].some(b=>b.textContent.trim().endsWith(node.value));if(node.value&&node.value!==node.defaultValue&&node.value!==appliedSamples.get(kind)&&!nativeDefault)return;node.value=sample;node.dispatchEvent(new Event('input',{bubbles:true}))}
   if(kind==='vision'&&['chart','whiteboard','document','defects','scene'].includes(sample))document.querySelector('[data-sample="'+sample+'"]')?.click();
   if(kind==='translate'&&['brief','operations'].includes(sample))document.getElementById('sample-'+sample)?.click();
   appliedSamples.set(kind,sample);
  };
  let attempts=0;const ready=()=>{if((['vision','translate','video'].includes(kind)&&!window.FuryExperienceReady)||(kind==='atlas'&&document.body.dataset.state!=='idle')){if(attempts++<25)setTimeout(ready,200);return}apply()};ready();
 });
 let touched=0;for(const name of ['pointerdown','keydown'])addEventListener(name,()=>{if(state.active&&Date.now()-touched>60000){touched=Date.now();api('touch',{}).catch(()=>{})}},{passive:true});
 async function boothPalette(){
  if(document.body.dataset.workflow!=='slides')return;
  for(const frame of document.querySelectorAll('#stage iframe')){
   if(!frame.src||new URL(frame.src).origin!==location.origin||!/^\/api\/projects\/[^/]+\/deck$/.test(new URL(frame.src).pathname))continue;
   try{const revision=state.revision;const css=state.booth_palette&&state.active?await (await fetch('/skin/booth.css?revision='+encodeURIComponent(revision),{cache:'no-store'})).text():'';if(revision!==state.revision)return;frame.contentWindow?.postMessage({type:'hpdeck',cmd:'palette',css},'*')}catch{}
  }
 }
 if(document.body.dataset.workflow==='slides'){const stage=document.getElementById('stage');if(stage)new MutationObserver(()=>{for(const frame of stage.querySelectorAll('iframe'))if(!frame.dataset.skinWatched){frame.dataset.skinWatched='true';frame.addEventListener('load',boothPalette)}boothPalette()}).observe(stage,{childList:true,subtree:false})}
 root.classList.add('skin-controls-ready');
 refresh();
 window.FurySkin={refresh,update};
 } catch {disable()}
})();
