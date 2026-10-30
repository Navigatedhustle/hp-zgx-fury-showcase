/* Read-only explanation of the existing local routes. Never starts inference. */
((root) => {
 const MODEL_INFO={
  'fury-lead':{name:'DeepSeek V4 Flash',checkpoint:'nvidia/DeepSeek-V4-Flash-NVFP4',role:'Architecture, contract review and integration',key:'lead'},
  'unsloth/Qwen3.6-27B-NVFP4':{name:'Qwen3.6 27B',checkpoint:'unsloth/Qwen3.6-27B-NVFP4',role:'Frontend, backend, UX, QA and release notes',key:'qwen'}
 };
 const friendly=alias=>MODEL_INFO[alias]?.name||alias||'Manual work';
 function summarize(run,alias,stale=false){
  const calls=(run?.calls||[]).filter(c=>c.model===alias),known=calls.filter(c=>Number.isInteger(c.usage?.completion_tokens));
  return {calls,completed:calls.filter(c=>c.status==='complete').length,generating:stale?null:calls.filter(c=>c.status==='generating').length,queued:stale?null:calls.filter(c=>c.status==='queued').length,admitted:stale?null:calls.filter(c=>c.status==='admitted').length,output:known.reduce((n,c)=>n+c.usage.completion_tokens,0),unknown:known.length!==calls.length,rate:stale||calls.some(c=>!Number.isFinite(c.current_tps))?null:calls.reduce((n,c)=>n+c.current_tps,0)};
 }
 let run=null,health={},identities={},checked=0,disconnected=false,filter='fury-lead';const previous=new Map();
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function text(id,value){const node=document.getElementById(id);if(node)node.textContent=value}
 function render(){
  if(typeof document==='undefined')return;
  const stale=disconnected||Boolean(run?.sampled_at&&Date.now()/1000-run.sampled_at>4),calls=run?.calls||[],names=Object.fromEntries((run?.actors||[]).map(a=>[a.id,a.name]));
  for(const [alias,info] of Object.entries(MODEL_INFO)){
   const s=summarize(run,alias,stale),out=s.output.toLocaleString()+(s.unknown?' + unknown':''),ready=Date.now()-checked<20000&&typeof health[alias]==='boolean'?health[alias]:null;
   const identity=identities[alias];text(info.key+'-readiness',ready===true?(identity?.identity_verified===true?'Runtime identity verified':identity?.identity_verified===false?'Identity mismatch':'Ready · identity unknown'):ready===false?'Endpoint unavailable':'Readiness unknown');text(info.key+'-identity',identity?.identity_verified===true?'vLLM reports '+identity.reported_checkpoint+' · context '+(Number.isFinite(identity.max_context)?identity.max_context.toLocaleString():'unknown')+' · pinned revision '+identity.pinned_revision:identity?.identity_verified===false?'Runtime identity differs from the configured checkpoint.':'Runtime identity has not been verified.');
   text(info.key+'-activity',stale?'Live activity unknown':`${s.generating} generating · ${s.queued} queued · ${s.admitted} awaiting output`);
   text(info.key+'-completed',s.completed.toLocaleString());text(info.key+'-output',out);text(info.key+'-rate',s.rate===null?'Unknown':s.rate.toFixed(1)+' tok/s');
   text(info.key+'-strip',`${s.completed} completed requests · ${out} output tokens`);
   const card=document.getElementById(info.key+'-model');if(card){card.dataset.state=stale?'unknown':s.generating?'generating':s.queued?'queued':'idle';const changed=previous.has(alias)&&s.output>previous.get(alias)&&!stale;card.classList.toggle('output-event',changed);previous.set(alias,s.output)}
  }
  text('stack-queue',stale?'Live queue unknown':`${calls.filter(c=>c.status==='queued').length} queued in this run`);
  text('stack-assigned',(run?.tasks||[]).filter(t=>t.status==='merged').length+' / '+(run?.tasks||[]).length+' tasks merged');
  const version=run?.versions?.at(-1);text('stack-preview',version?'Published preview '+version.version:'No published preview');
  text('stack-validation',run?.tests?run.tests.passed?run.tests.tests+' sandbox tests passed':'Latest candidate tests failed':'Tests pending');
  text('stack-review',run?.gate?.status==='waiting'?'Waiting for operator review':run?.automatic?'Disclosed automatic gates':'Manual review gates');
  text('stack-run',run?.id?'Run '+run.id:'Ready for a development run');
  const rows=calls.filter(c=>filter==='all'||c.model===filter).slice().reverse();
  const tbody=document.getElementById('route-evidence');if(tbody)tbody.innerHTML=rows.length?rows.map(c=>'<tr><td>'+esc(names[c.actor]||c.actor)+'<small>'+esc(friendly(c.model))+'</small></td><td><code>'+esc((run?.id||'')+':'+c.id)+'</code></td><td>'+esc(c.status==='admitted'?'Awaiting output':c.status)+'</td><td>'+(Number.isInteger(c.usage?.completion_tokens)?c.usage.completion_tokens.toLocaleString():'Unknown')+'</td><td>'+(Number.isFinite(c.ttft_s)?c.ttft_s.toFixed(2)+' s':'Unknown')+'</td></tr>').join(''):'<tr><td colspan="5">No requests on this route in the current run.</td></tr>';
  for(const button of document.querySelectorAll('[data-model-filter]'))button.setAttribute('aria-pressed',String(button.dataset.modelFilter===filter));
 }
 const api={friendly,summarize,models:MODEL_INFO,update(data){run=data;disconnected=false;render()},readiness(config){health=config.backends||{};identities=config.model_details||{};checked=Date.now();render()},stale(){disconnected=true;render()}};
 root.FuryStack=api;if(typeof module==='object'&&module.exports)module.exports=api;
 if(typeof document!=='undefined')for(const button of document.querySelectorAll('[data-model-filter]'))button.addEventListener('click',()=>{filter=button.dataset.modelFilter;render()});
})(globalThis);
