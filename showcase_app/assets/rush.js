/* Launcher automation uses each retained station's existing Go controls and ownership. */
(() => {
 if(window.FuryRushLoaded)return;window.FuryRushLoaded=true;
 const sample={atlas:'What happens to Q4 profit if our Commit stage win rate drops by 8 percentage points?',slides:'Explain reliable local AI workflows, evidence, human review, and next steps.',image:'A cinematic architectural concept of an original deep sea research observatory, luminous teal water, beautiful natural light, no text, no logos.'};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const deadline=async(test,seconds)=>{const until=Date.now()+seconds*1000;while(Date.now()<until){const v=test();if(v)return v;await sleep(250)}throw Error('Station did not reach its expected state')};
 if(window.self!==window.top){
  const requests=new Map();
  addEventListener('message',async event=>{
   if(event.source!==parent||event.data?.type!=='fury:launch')return;
   let allowed=false;try{const u=new URL(event.origin);allowed=u.hostname===location.hostname&&(u.protocol==='https:'&&u.port===''||u.protocol==='http:'&&u.port==='8080')}catch{}if(!allowed)return;
   const id=event.data.request;if(typeof id!=='string'||id.length>64)return;
   const demo=event.data.demo;
   const send=(state,detail='')=>{requests.set(id,{state,detail});parent.postMessage({type:'fury:launch-state',request:id,demo,state,detail},event.origin)};
   if(requests.has(id)){const current=requests.get(id);send(current.state,current.detail);return}
   send('queued','Waiting for the existing station controls');
   try{
    if(demo==='agent'){
     const idleUntil=Date.now()+900000;
     while(true){
      const response=await fetch('/api/devteam/status',{cache:'no-store'});
      if(!response.ok)throw Error('Factory admission status is unavailable');
      const capacity=await response.json();if(!capacity.active)break;
      send('queued','Waiting for the current shared Factory build');
      if(Date.now()>idleUntil)throw Error('Factory remained busy for fifteen minutes');
      await sleep(1500);
     }
     await deadline(()=>document.getElementById('start')&&!document.getElementById('start').disabled,900);
     for(const [name,value] of [['demo-mode','live'],['product','short']]){const el=document.getElementById(name);el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}))}
     const automatic=document.getElementById('automatic');automatic.checked=true;automatic.dispatchEvent(new Event('change',{bubbles:true}));document.getElementById('start').click();send('submitted','Automatic short Live build');
     await deadline(()=>['running','failed','blocked'].includes(document.getElementById('run-state').textContent),45);
     const state=await deadline(()=>{const s=document.getElementById('run-state').textContent;return ['finished','failed','blocked','stopped'].includes(s)&&s},1800);
     if(state!=='finished')throw Error('Live build '+state);
    }else if(demo==='atlas'){
     await deadline(()=>document.getElementById('question-input')&&typeof config!=='undefined'&&config&&typeof state!=='undefined'&&state!=='thinking',180);
     const input=document.getElementById('question-input');input.value=sample.atlas;input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#question-form button').click();send('submitted','Grounded Atlas question');
     await deadline(()=>typeof last!=='undefined'&&last?.question===sample.atlas&&last.grounding&&state!=='thinking',180);
     if(!last.grounding.passed)throw Error('Atlas grounding did not pass');
    }else{
     if(['vision','translate'].includes(demo))await deadline(()=>window.FuryExperienceReady,45);
     await deadline(()=>document.getElementById('go')&&!document.getElementById('go').disabled,900);
     if(sample[demo]){const input=document.getElementById('prompt');input.value=sample[demo];input.dispatchEvent(new Event('input',{bubbles:true}))}
     document.getElementById('go').click();send('submitted','Existing Go control submitted');
     const status=await deadline(()=>{const s=document.getElementById('status')?.dataset.state;return ['complete','failed'].includes(s)&&s},600);
     if(status!=='complete')throw Error('Station generation failed');
    }
    send('complete','Real station checks completed');
   }catch(error){send('failed',error.message)}
  });
  return;
 }
 const button=document.getElementById('fury-rush'),board=document.getElementById('rush-board');if(!button||!board)return;
 const labels={agent:'Agent Factory',atlas:'Atlas',slides:'Presentations',vision:'Vision Lab',translate:'Translate Desk',image:'Image Studio'};
 let run=null;
 const draw=()=>{board.hidden=false;board.replaceChildren(...Object.entries(run.jobs).map(([demo,j])=>{const s=document.createElement('span');s.dataset.state=j.state;s.textContent=labels[demo]+' · '+j.state;s.title=j.detail||'';return s}));if(Object.values(run.jobs).every(j=>['complete','failed'].includes(j.state))){button.disabled=false;button.textContent='↗ Launch Fury Rush'}};
 addEventListener('message',event=>{
  if(!run||event.data?.type!=='fury:launch-state')return;
  const d=event.data,j=run.jobs[d.demo],frame=window.FuryStations?.ensure(d.demo);
  if(!j||j.request!==d.request||event.source!==frame?.contentWindow||event.origin!==new URL(frame.src).origin)return;
  j.state=d.state;j.detail=d.detail;j.ack=true;draw();
 });
 button.onclick=async()=>{
  if(button.disabled)return;button.disabled=true;button.textContent='Fury Rush in progress';
  run={jobs:Object.fromEntries(Object.keys(labels).map(demo=>[demo,{request:crypto.randomUUID(),state:'queued',ack:false}]))};draw();
  async function launch(demo){
   const frame=window.FuryStations.ensure(demo),job=run.jobs[demo],origin=new URL(frame.src).origin;
   for(let tries=0;tries<45&&!job.ack;tries++){frame.contentWindow?.postMessage({type:'fury:launch',request:job.request,demo},origin);await sleep(1000)}
   if(!job.ack){job.state='failed';job.detail='Station launcher could not connect';draw()}
  }
  launch('agent');setTimeout(()=>document.getElementById('mc-live-jobs')?.scrollIntoView({block:'end',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'}),1800);await sleep(2000);for(const demo of ['atlas','slides','vision','translate','image'])launch(demo);
 };
})();
