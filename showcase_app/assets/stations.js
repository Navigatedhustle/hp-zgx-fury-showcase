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
  const frames=new Map(),destinations={atlas:[8200,'/'],slides:[8765,'/booth'],agent:[8501,'/devteam'],image:[8800,'/'],vision:[8080,'/experience/vision'],translate:[8080,'/experience/translate'],video:[8080,'/experience/video'],trailer:[8080,'/experience/trailer']};
  function ensure(demo){const selected=destinations[demo];
   if(selected&&!frames.has(demo)){const frame=document.createElement('iframe');const url=new URL(location.href);url.protocol=location.hostname.endsWith('.ts.net')?'https:':'http:';url.port=location.hostname.endsWith('.ts.net')&&selected[0]===8080?'':String(selected[0]);url.pathname=selected[1];url.search='?station=1';if(demo==='video'&&new URLSearchParams(location.search).get('image_id'))url.search+='&image_id='+encodeURIComponent(new URLSearchParams(location.search).get('image_id'));url.hash='';frame.src=url.href;frame.hidden=true;frame.addEventListener('load',()=>frame.contentWindow?.postMessage({type:'fury:visibility',visible:!frame.hidden},new URL(frame.src).origin));frame.title={atlas:'Atlas workspace',slides:'Presentation generation workspace',agent:'Agent Factory workspace',image:'Image generation workspace',vision:'Vision Lab workspace',translate:'Translate Desk workspace',video:'Video Studio workspace',trailer:'Action Trailer workspace'}[demo];frame.allow='microphone; camera; fullscreen; clipboard-write';frame.dataset.demo=demo;document.getElementById('station-workspaces').append(frame);frames.set(demo,frame)}
   return frames.get(demo);
  }
  window.FuryStations={ensure,choose};
  function choose(demo,push=true){
   const selected=destinations[demo];document.body.classList.toggle('chooser-active',Boolean(selected));document.getElementById('station-workspaces').hidden=!selected;
   if(selected)ensure(demo);
   frames.forEach((frame,key)=>{frame.hidden=key!==demo;frame.contentWindow?.postMessage({type:'fury:visibility',visible:key===demo},new URL(frame.src).origin)});
   if(push)history.pushState({demo},'',selected?'/demos?demo='+demo:'/demos');
   document.querySelector('.all-demos')?.setAttribute('aria-current',selected?'false':'page');
   try{sessionStorage.setItem('fury-demo-view',selected?demo:'chooser')}catch{}
  }
  document.querySelectorAll('a[data-demo]').forEach(a=>a.onclick=e=>{e.preventDefault();choose(a.dataset.demo)});
  document.addEventListener('click',e=>{const a=e.target.closest('a.all-demos,.hp-home');if(a){e.preventDefault();choose(null)}});
  addEventListener('message',event=>{
   if(event.data?.type!=='fury:send-video'||!/^[0-9a-f]{32}(?:-[1-4])?\.png$/.test(event.data.name||''))return;
   const source=frames.get('image');if(event.source!==source?.contentWindow||event.origin!==new URL(source.src).origin)return;
   const frame=ensure('video'),send=()=>frame.contentWindow?.postMessage({type:'fury:image-reference',name:event.data.name},new URL(frame.src).origin);frame.addEventListener('load',send,{once:true});choose('video');send();history.replaceState({demo:'video'},'','/demos?demo=video&image_id='+encodeURIComponent(event.data.name));
  });
  addEventListener('popstate',()=>choose(new URLSearchParams(location.search).get('demo'),false));choose(new URLSearchParams(location.search).get('demo'),false);
  async function ready(){if(window.FuryMissionLoaded)return;try{const response=await fetch('/api/event',{cache:'no-store',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error();const d=await response.json(),fresh=Date.now()/1000-d.timestamp<20;for(const [key,service] of Object.entries({atlas:'atlas',slides:'slides',agent:'agent',image:'image'})){const node=document.querySelector('[data-readiness="'+key+'"]'),s=d.services[service],a=d.activity[key]||{};if(!node)continue;node.textContent=!fresh?'Status delayed':!s?.connected||!s.ready?'Starting / unavailable':key==='agent'&&d.capacity?.agent?.active>0?'Live busy · Guided available':a.active>0||a.queued>0?'Busy · '+a.active+' active / '+a.queued+' queued':'Ready';}}catch{document.querySelectorAll('[data-readiness]').forEach(n=>n.textContent='Status unavailable')}setTimeout(ready,5000)}ready();
 }
})();
