/* Add request protection to same-origin binary/multipart controls. No UI changes. */
(() => {
 const nativeFetch=window.fetch.bind(window);let pendingToken;
 const token=()=>pendingToken||(pendingToken=nativeFetch('/api/security/csrf-token',{cache:'no-store',credentials:'same-origin'}).then(async r=>{if(!r.ok)throw Error('Station request protection is unavailable');const value=await r.json();if(!/^[a-f0-9]{64}$/.test(value.token))throw Error('Invalid station request protection');return value.token}).catch(error=>{pendingToken=null;throw error}));
 window.fetch=async(input,options)=>{
  const request=new Request(input,options),url=new URL(request.url);
  if(url.origin!==location.origin||['GET','HEAD','OPTIONS'].includes(request.method))return nativeFetch(request);
  const headers=new Headers(request.headers),kind=(headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
  if(kind!=='application/json'&&!(kind.startsWith('application/')&&kind.endsWith('+json')))headers.set('X-Fury-CSRF',await token());
  return nativeFetch(new Request(request,{headers}));
 };
})();

/* One shared shell; view preferences belong to this browser, never the server. */
(() => {
 const html=document.documentElement;
 if(window.self!==window.top)html.dataset.furyEmbedded='true';
 const height=()=>html.style.setProperty('--fury-height',Math.floor(window.visualViewport?.height||innerHeight)+'px');
 height();addEventListener('resize',height);window.visualViewport?.addEventListener('resize',height);
 let choice='dark';try{choice=localStorage.getItem('hp-experience-theme')||'dark'}catch{}
 function theme(){html.dataset.hpTheme=choice;html.classList.toggle('dark',choice==='dark'||(choice==='system'&&matchMedia('(prefers-color-scheme:dark)').matches));document.querySelectorAll('.hp-theme').forEach(b=>b.textContent='Theme: '+choice)}
 function notify(text){let node=document.getElementById('fury-shell-status');if(!node){node=document.createElement('p');node.id='fury-shell-status';node.setAttribute('role','status');document.body.append(node)}node.textContent=text;clearTimeout(notify.timer);notify.timer=setTimeout(()=>node.remove(),6000)}
 function fullscreen(){if(document.fullscreenElement)document.exitFullscreen().catch(()=>notify('Use Escape to leave fullscreen.'));else if(document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(()=>notify('Fullscreen is unavailable here. The workspace remains usable in this window.'));else notify('Use your browser’s fullscreen control if available.')}
 function remote(url){const u=new URL(url,location.href);if(location.hostname.endsWith('.ts.net')){u.protocol='https:';u.hostname=location.hostname;if(u.port==='8080')u.port=''}return u.href}
 matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if(choice==='system')theme()});
 function start(){
  let shell=document.querySelector('.hp-shell');if(!shell){shell=document.createElement('header');shell.className='hp-shell';shell.innerHTML='<a class="hp-home" href="http://localhost:8080/demos"><img class="hp-logo" src="/showcase-assets/hp-logo-keyline.png" width="48" height="48" alt="HP"><span>HP ZGX Fury<br>demo experience</span></a><nav aria-label="Experience"></nav>';document.body.prepend(shell)}
  shell.querySelector('.hp-home').href=remote('http://localhost:8080/demos');
  shell.querySelector('nav').innerHTML='<a class="all-demos" href="'+remote('http://localhost:8080/demos')+'">All demos</a><a href="'+remote('http://localhost:8080/operator')+'">Economics</a><a href="'+remote('http://localhost:8080/why-hp')+'">Why HP</a><a href="'+remote('http://localhost:8080/stations')+'">Station setup</a><button class="hp-present" type="button">Present fullscreen</button><button class="hp-theme" type="button" aria-label="Change color theme"></button>';
  if(['8200','8501','8765','8800'].includes(location.port)){shell.querySelector('.all-demos').target='_blank';shell.querySelector('.all-demos').rel='noopener';shell.querySelector('.all-demos').title='Open the chooser while keeping this work running'}
  document.querySelectorAll('.hp-theme').forEach(b=>b.onclick=()=>{choice=choice==='light'?'dark':choice==='dark'?'system':'light';try{localStorage.setItem('hp-experience-theme',choice)}catch{}theme()});theme();
  shell.querySelector('.hp-present').onclick=fullscreen;
  document.addEventListener('fullscreenchange',()=>shell.querySelector('.hp-present').textContent=document.fullscreenElement?'Exit fullscreen':'Present fullscreen');
  if(!document.querySelector('.hp-skip')){const a=document.createElement('a');a.className='hp-skip';a.href='#main';a.textContent='Skip to content';document.body.prepend(a)}
  document.querySelectorAll('.hp-skip').forEach(a=>a.onclick=e=>{const main=document.querySelector('main')||document.getElementById('root');if(main){e.preventDefault();main.tabIndex=-1;main.focus()}});
  document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);b.textContent='Copied'}catch{b.textContent='Select the example text to copy'}});
  if(document.body.dataset.workflow==='atlas'){
   const details=document.createElement('details');details.className='atlas-secondary';details.innerHTML='<summary>Camera, devices & model details</summary><div class="atlas-secondary-content"></div>';
   const content=details.lastElementChild;for(const selector of ['.camera-block','.model-strip']){const node=document.querySelector(selector);if(node)content.append(node)}
   document.querySelector('.action-bar')?.before(details);
   const fitAtlas=()=>{if(innerWidth>=1000&&!document.body.classList.contains('record-vertical')&&document.getElementById('orb-setting')?.checked){const chart=document.querySelector('.chart-block');if(chart)document.querySelector('.left-column')?.append(chart)}};
   requestAnimationFrame(fitAtlas);addEventListener('resize',()=>requestAnimationFrame(fitAtlas));new MutationObserver(()=>requestAnimationFrame(fitAtlas)).observe(document.body,{attributes:true,attributeFilter:['class']});
  }
  if(document.body.dataset.hpApp==='factory'){if(new URLSearchParams(location.search).get('station')==='1'&&!document.getElementById('product').disabled){document.getElementById('product').value='short';document.getElementById('product').dispatchEvent(new Event('change'))}factoryWorkspace();}
  const main=document.querySelector('main');if(main&&!main.id)main.id='main';
  if(!document.querySelector('link[href="/showcase-assets/mission.css"]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/showcase-assets/mission.css';document.head.append(css)}
  if(!document.querySelector('script[src="/showcase-assets/mission.js"]')){const js=document.createElement('script');js.src='/showcase-assets/mission.js';document.head.append(js)}
 }
 function factoryWorkspace(){
  const main=document.querySelector('main'),progress=document.querySelector('.presenter-progress'),metrics=document.querySelector('main>.metrics');progress.tabIndex=0;progress.setAttribute('role','region');progress.setAttribute('aria-label','Build progress and token metrics');if(metrics){progress.querySelector('#stage-explanation').after(metrics);const notes=['Observed output over 5 s','Final endpoint usage','Two development slots','Final endpoint usage','Checked versions'];[...metrics.querySelectorAll('article span')].forEach((span,i)=>{span.title=span.textContent;span.textContent=notes[i]||span.textContent})}
  for(const id of ['error','failure-details']){const e=document.getElementById(id);if(e)progress.append(e)}
  const work=document.createElement('section');work.id='factory-workspace';work.setAttribute('aria-label','Factory workspace');work.innerHTML='<div class="factory-tabs" role="tablist" aria-label="Workspace"><button type="button" id="factory-tab-application" role="tab" aria-controls="factory-pane-application" data-workspace="application">Application</button><button type="button" id="factory-tab-backend" role="tab" aria-controls="factory-pane-backend" data-workspace="backend">Backend</button><button type="button" id="factory-tab-development" role="tab" aria-controls="factory-pane-development" data-workspace="development">Development</button></div>';
  const build=document.getElementById('build-view'),backend=document.querySelector('details.backend'),technical=document.getElementById('technical-details');
  const nodes={application:build,backend,development:technical};for(const [key,node] of Object.entries(nodes)){const pane=document.createElement('div');pane.id='factory-pane-'+key;pane.className='factory-pane';pane.setAttribute('role','tabpanel');pane.setAttribute('aria-labelledby','factory-tab-'+key);pane.append(node);work.append(pane)}
  main.append(work);
  for(const [id,label] of Object.entries({'api-output':'Backend response','test-output':'Latest test results','events':'Development events','code-output':'Generated code','latest-diff':'Latest code change'})){const node=document.getElementById(id);if(node){node.tabIndex=0;node.setAttribute('role','region');node.setAttribute('aria-label',label)}}
  document.getElementById('start').addEventListener('click',()=>document.getElementById('advanced-controls').open=false);
  let view='application';try{view=sessionStorage.getItem('fury-factory-workspace')||view}catch{}
  function select(key){if(!nodes[key])key='application';document.getElementById('product-focus').textContent='Focus product';window.FuryFactoryTabs?.(key==='development'?'team':'build');for(const pane of work.querySelectorAll('.factory-pane'))pane.hidden=pane.id!=='factory-pane-'+key;for(const button of work.querySelectorAll('[data-workspace]')){const yes=button.dataset.workspace===key;button.setAttribute('aria-selected',String(yes));button.tabIndex=yes?0:-1}if(key==='backend')backend.open=true;if(key==='development')technical.open=true;try{sessionStorage.setItem('fury-factory-workspace',key)}catch{}}
  const buttons=[...work.querySelectorAll('[data-workspace]')];buttons.forEach((button,i)=>{button.onclick=()=>select(button.dataset.workspace);button.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;select(buttons[n].dataset.workspace);buttons[n].focus()}}});select(view);new MutationObserver(()=>{buttons[2].disabled=technical.hidden;if(technical.hidden&&buttons[2].getAttribute('aria-selected')==='true')select('application')}).observe(technical,{attributes:true,attributeFilter:['hidden']});
 }
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',start):start();
})();
