(() => {
 const key='fury-station-v2',routes={economics:'/operator',why:'/why-hp',demos:'/demos'};
 const page=document.body.dataset.stationPage;
 if(page==='setup'){
  let saved='demos';try{saved=localStorage.getItem(key)||saved}catch{}
  const radio=document.querySelector('input[value="'+saved+'"]');if(radio)radio.checked=true;
  document.getElementById('station-form').onsubmit=e=>{e.preventDefault();const choice=new FormData(e.target).get('station');if(!routes[choice])return;try{localStorage.setItem(key,choice)}catch{}location.assign(routes[choice])};
  document.getElementById('station-reset').onclick=()=>{try{localStorage.removeItem(key)}catch{}document.getElementById('station-note').textContent='This browser’s assignment was cleared. Demo jobs and other stations are unchanged.'};
 }
 if(page==='demos'){
  if(location.pathname==='/'&&!location.search&&!location.hash){let assigned;try{assigned=localStorage.getItem(key)}catch{}if(assigned&&assigned!=='demos'){location.replace(routes[assigned]);return}}
  if(location.hash==='#why'){location.replace('/why-hp');return}if(['#presenter','#concurrency'].includes(location.hash)){location.replace('/presenter');return}
  const frames=new Map(),destinations={atlas:[8200,'/'],slides:[8765,'/booth'],agent:[8501,'/devteam'],image:[8800,'/']};
  function choose(demo,push=true){
   const selected=destinations[demo];document.body.classList.toggle('chooser-active',Boolean(selected));document.getElementById('station-workspaces').hidden=!selected;
   if(selected&&!frames.has(demo)){const frame=document.createElement('iframe');const url=new URL(location.href);url.protocol=location.hostname.endsWith('.ts.net')?'https:':'http:';url.port=String(selected[0]);url.pathname=selected[1];url.search='?station=1';url.hash='';frame.src=url.href;frame.title={atlas:'Atlas workspace',slides:'Presentation generation workspace',agent:'Agent Factory workspace',image:'Image generation workspace'}[demo];frame.allow='microphone; camera; fullscreen; clipboard-write';frame.dataset.demo=demo;document.getElementById('station-workspaces').append(frame);frames.set(demo,frame)}
   frames.forEach((frame,key)=>frame.hidden=key!==demo);
   if(push)history.pushState({demo},'',selected?'/demos?demo='+demo:'/demos');
   document.querySelector('.all-demos')?.setAttribute('aria-current',selected?'false':'page');
   try{sessionStorage.setItem('fury-demo-view',selected?demo:'chooser')}catch{}
  }
  document.querySelectorAll('a[data-demo]').forEach(a=>a.onclick=e=>{e.preventDefault();choose(a.dataset.demo)});
  document.addEventListener('click',e=>{const a=e.target.closest('a.all-demos,.hp-home');if(a){e.preventDefault();choose(null)}});
  addEventListener('popstate',()=>choose(new URLSearchParams(location.search).get('demo'),false));choose(new URLSearchParams(location.search).get('demo'),false);
  async function ready(){try{const response=await fetch('/api/event',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error();const d=await response.json(),fresh=Date.now()/1000-d.timestamp<20;for(const [key,service] of Object.entries({atlas:'atlas',slides:'slides',agent:'agent',image:'image'})){const node=document.querySelector('[data-readiness="'+key+'"]'),s=d.services[service],a=d.activity[key]||{};node.textContent=!fresh?'Status delayed':!s?.connected||!s.ready?'Starting / unavailable':key==='agent'&&d.capacity?.agent?.active>0?'Live busy · Guided available':a.active>0||a.queued>0?'Busy · '+a.active+' active / '+a.queued+' queued':'Ready';}}catch{document.querySelectorAll('[data-readiness]').forEach(n=>n.textContent='Status unavailable')}setTimeout(ready,5000)}ready();
 }
})();
