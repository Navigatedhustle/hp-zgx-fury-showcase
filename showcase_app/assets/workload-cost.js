/* Cumulative, source-backed comparison. Polling updates existing bars in place. */
(() => {
 const el=id=>document.getElementById(id);
 const money=value=>value.toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:value>0&&value<.01?5:2,maximumFractionDigits:value>0&&value<.01?5:2});
 const counterMoney=value=>value.toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:value>0&&value<.01?5:4,maximumFractionDigits:value>0&&value<.01?5:4});
 const number=value=>value.toLocaleString('en-US');
 const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let scale=0,shape='',previous=new Map(),frame=0,animation=0;
 function clearChart(){cancelAnimationFrame(frame);animation++;el('workload-cost-chart').replaceChildren();shape='';scale=0;previous.clear();}
 function niceScale(value){if(value<=0)return 1;const base=10**Math.floor(Math.log10(value));return [1,2,5,10].find(n=>n*base>=value)*base;}
 function renderBars(entries){
  const chart=el('workload-cost-chart'),key=entries.map(e=>e.id).join('|'),reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const max=Math.max(...entries.map(e=>e.value),0);
  // Preserve the axis across polls so increments lengthen bars instead of re-normalizing them.
  if(!scale||max>scale)scale=niceScale(max*1.25);
  if(shape!==key){clearChart();scale=niceScale(max*1.25);shape=key;
   chart.innerHTML='<div class="cost-chart-unit">Cumulative estimated cost · USD · linear scale from $0</div><div class="cost-axis" aria-hidden="true"><span>$0</span><span data-mid></span><span data-max></span></div>'+entries.map(e=>`<div class="cost-chart-row${e.local?' cost-chart-local':''}" data-cost-id="${escape(e.id)}"><div class="cost-model"><b>${escape(e.label)}</b><small>${escape(e.note)}</small></div><div class="cost-track" aria-hidden="true"><div class="cost-mark" style="width:0%"></div></div><div class="cost-amount"><strong class="cost-value">$0.00</strong><small class="cost-ratio"></small></div></div>`).join('');
  }
  void chart.offsetWidth;
  chart.querySelector('[data-mid]').textContent=money(scale/2);chart.querySelector('[data-max]').textContent=money(scale);
  chart.setAttribute('aria-label','Cumulative estimated costs in USD for all completed text experiences');
  const power=entries.find(e=>e.local).value,starts=new Map();let changed=false;
  for(const e of entries){const row=chart.querySelector(`[data-cost-id="${e.id}"]`),before=previous.get(e.id)??0;starts.set(e.id,before);
   const mark=row.querySelector('.cost-mark');mark.style.width=(e.value/scale*100)+'%';
   row.querySelector('.cost-ratio').textContent=e.local?'Electricity only':power>0?(e.value/power).toLocaleString('en-US',{maximumFractionDigits:1})+'× electricity':'Ratio unavailable';
   if(e.value!==before){changed=true;row.classList.remove('cost-increment');if(e.value>before){void row.offsetWidth;row.classList.add('cost-increment');}}
  }
  if(!changed)return;
  cancelAnimationFrame(frame);const generation=++animation,start=performance.now();
  const tick=now=>{if(generation!==animation)return;const progress=reduced?1:Math.min(1,(now-start)/750),ease=1-(1-progress)**3;for(const e of entries){const value=starts.get(e.id)+(e.value-starts.get(e.id))*ease;chart.querySelector(`[data-cost-id="${e.id}"] .cost-value`).textContent=counterMoney(value);previous.set(e.id,value);}if(progress<1)frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);
 }
 window.renderWorkloadCost=data=>{
  const summary=el('cost-power-summary'),volume=el('cost-volume');
  const reset=message=>{clearChart();volume.textContent=message;summary.textContent='';el('cost-experiences').replaceChildren();el('cost-rates').replaceChildren();el('cost-pricing-date').textContent='';};
  const c=data?.cost_comparison;
  document.querySelector('.cost-live-badge').textContent=c?'LIVE WORKLOAD':'DATA UNAVAILABLE';
  if(!c){reset(data?'Cost comparison is waiting for measured usage.':'Live usage unavailable. Cost estimates will return with a fresh sample.');return;}
  const s=c.scopes.all;
  el('cost-experiences').innerHTML=[['atlas','Atlas'],['slides','Presentations'],['agent','Agent Factory']].map(([id,name])=>`<span><i></i>${name}<b>${number(c.scopes[id]?.requests||0)} calls</b></span>`).join('')+`<span class="cost-image-activity"><i></i>Image Studio<b>${number(data.totals?.image?.images||0)} images · separate</b></span>`;
  const checked=new Date(c.pricing_checked+'T00:00:00Z'),stale=data.timestamp*1000-checked.getTime()>30*86400000;
  el('cost-pricing-date').textContent=`Official prices checked ${checked.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}. Standard USD token rates; ${stale?'pricing snapshot is over 30 days old — recheck sources before use.':'not an automatically refreshed price feed.'}`;
  el('cost-rates').innerHTML=c.models.map(m=>`<tr><td><a href="${escape(m.source)}" target="_blank" rel="noopener noreferrer">${escape(m.name)} ↗</a><small>${escape(m.note)}</small></td><td>${money(m.input)}</td><td>${money(m.output)}</td></tr>`).join('');
  if(!s?.requests){clearChart();volume.textContent='No completed text requests with known usage and timing yet.';summary.textContent='Excluded requests: '+number(s?.excluded_requests||0)+'. Run a text experience to populate this chart.';return;}
  volume.textContent=`${number(s.input)} tokens read + ${number(s.output)} generated · ${number(s.requests)} completed text-model calls · ${number(s.excluded_requests)} excluded`;
  const kw=Number(el('cost-kw').value),rate=Number(el('cost-kwh').value);
  if([el('cost-kw'),el('cost-kwh')].some(input=>input.value===''||!Number.isFinite(Number(input.value))||Number(input.value)<0)){
   clearChart();summary.textContent='Enter nonnegative system power and electricity values to compare costs.';return;
  }
  const power=kw*s.wall_seconds/3600*rate;
  const entries=c.models.map(m=>({id:m.id,label:m.name,note:m.provider+' · same measured tokens',value:s.api_costs.find(x=>x.model_id===m.id).usd,local:false}));
  entries.push({id:'fury-electricity',label:'Fury electricity',note:'Estimated · same request time',value:power,local:true});
  renderBars(entries);
  summary.textContent=`Fury estimate: ${money(power)} · ${kw} kW × ${(s.wall_seconds/3600).toFixed(4)} covered hours × ${money(rate)}/kWh. Updates as completed usage arrives (sampled every 2 seconds).`;
 };
})();
