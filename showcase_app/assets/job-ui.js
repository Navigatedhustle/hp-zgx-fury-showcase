/* Finite, resumable job controls shared by the existing image and booth pages. */
(() => {
 const kind=document.currentScript.dataset.workflow, image=kind==='image', $=id=>document.getElementById(id);
 const form=$('prompt-form'),prompt=$('prompt'),go=$('go'),stage=$('stage'),status=$('status'),result=$('result'),initial=stage.innerHTML;
 const key='fury-'+kind+'-job',cancel=document.createElement('button');cancel.type='button';cancel.className='secondary';cancel.textContent='Cancel job';cancel.hidden=true;go.after(cancel);
 let busy=false,current=null;
 function state(s,message){stage.dataset.state=s;status.dataset.state=s;status.textContent=message}
 async function api(url,options={}){
  const r=await fetch(url,{...options,signal:AbortSignal.timeout(20000),cache:'no-store'}),raw=await r.text();let d;
  try{d=JSON.parse(raw)}catch{throw Error('Service returned an unexpected response (HTTP '+r.status+'). Your brief is preserved; retry after checking the service.')}
  if(!r.ok)throw Error(r.status===429?'Capacity is busy. Try again after the current jobs finish.':r.status===404?'This job is no longer available. You can submit a new brief.':typeof d.detail==='string'?d.detail:'Service unavailable (HTTP '+r.status+'). Please retry.');return d
 }
 function controls(active){busy=active;go.disabled=active;prompt.disabled=active;$('again').disabled=active;cancel.hidden=!active;cancel.disabled=false;form.setAttribute('aria-busy',String(active));document.querySelectorAll('[data-prompt]').forEach(b=>b.disabled=active)}
 function link(text,url,primary=false){const a=document.createElement('a');a.textContent=text;a.href=url;a.className=primary?'button':'button secondary';return a}
 cancel.onclick=async()=>{if(!current)return;cancel.disabled=true;try{await api(image?'/api/jobs/'+current.id+'/cancel':'/api/projects/'+current.id+'/cancel',{method:'POST'});state('cancelling','Cancellation requested · releasing this job’s resources')}catch(e){state('failed',e.message);cancel.disabled=false}};
 async function follow(job){
  current=job;sessionStorage.setItem(key,JSON.stringify(job));controls(true);prompt.value=job.prompt;result.replaceChildren();stage.innerHTML=initial;
  const start=Date.now();let missing=0;
  try{
   while(true){
    let d;try{d=await api(image?'/api/jobs/'+job.id:'/api/projects/'+job.id);missing=0}catch(e){if(++missing>=3)throw e;state('waiting','Connection interrupted · reconnecting to your job');await new Promise(r=>setTimeout(r,1500));continue}
    if(['error','failed'].includes(d.status))throw Error(d.error||'Generation failed. Your brief is preserved.');
    if(['cancelled','canceled'].includes(d.status)){state('cancelled','Job cancelled. Ready for another brief.');sessionStorage.removeItem(key);break}
    if(d.status==='complete'){
     stage.replaceChildren();const actions=document.createElement('div');actions.className='actions';
     if(image){const img=document.createElement('img');img.className='result-image';img.alt='Generated image: '+job.prompt;img.src=d.url;img.onerror=()=>state('failed','Image completed but download is unavailable. Ask the operator to inspect job '+job.id.slice(0,12));stage.append(img);const a=link('Download image',d.url,true);a.download='fury-image.png';actions.append(a);state('complete','Image ready · '+d.seconds.toFixed(2)+' seconds on Fury')}
     else{const iframe=document.createElement('iframe');iframe.title='Generated presentation preview';iframe.className='result-preview';iframe.src='/api/projects/'+job.id+'/deck';stage.append(iframe);actions.append(link('Download editable PPTX','/api/projects/'+job.id+'/export.pptx?editable=true',true),link('Present HTML ↗','/api/projects/'+job.id+'/deck'),link('Review in creator','/p/'+job.id+'/review'));state('complete','Your three-slide draft is ready. Review it before use.')}
     result.append(actions);break
    }
    state(d.status==='queued'?'queued':'running',d.stage_note||(d.status==='queued'?'Queued · waiting for the local image model':d.status==='cancelling'?'Cancellation requested':'Generating with FLUX.2 klein 4B'));
    if(Date.now()-start>600000)throw Error('Job exceeded the ten-minute display budget. Refresh to reconnect or cancel this job.');
    await new Promise(r=>setTimeout(r,500));
   }
  }catch(e){state('failed',e.message);if(String(e.message).includes('no longer available'))sessionStorage.removeItem(key)}
  finally{controls(false);go.textContent=image?'Generate another image':'Create another deck'}
 }
 form.onsubmit=async e=>{e.preventDefault();if(busy)return;const brief=prompt.value.trim();if(brief.length<5){prompt.reportValidity();return}controls(true);state('queued','Submitting your request…');try{const j=await api(image?'/api/generate':'/api/booth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(image?{prompt:brief}:{brief})});await follow({id:j.id,prompt:brief})}catch(e){state('failed',e.message);controls(false)}};
 $('again').onclick=()=>{if(busy)return;sessionStorage.removeItem(key);current=null;stage.innerHTML=initial;result.replaceChildren();state('idle','Ready when you are');prompt.focus()};
 document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{prompt.value=b.dataset.prompt;prompt.focus()});prompt.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();form.requestSubmit()}};
 try{const saved=JSON.parse(sessionStorage.getItem(key));if(saved?.id&&saved.prompt)follow(saved)}catch{sessionStorage.removeItem(key)}
})();
