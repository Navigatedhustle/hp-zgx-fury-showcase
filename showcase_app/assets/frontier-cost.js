/* Cost scenarios only: no inference, external price requests or ownership-cost claims. */
(() => {
 const finite=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
 const amount=value=>value===''||value===null||value===undefined?null:finite(Number(value))?Number(value):null;
 function calculate(pricing,counts,power){
  const n=id=>amount(counts[id])??0;
  const input=n('prompts')*2000+n('vision')*1000+n('pages')*900;
  const output=n('prompts')*600+n('vision')*400+n('pages')*900;
  const image=n('images')*(pricing.workloads?.image?.usd_per_unit??0);
  const video=n('video')*(pricing.workloads?.video?.usd_per_unit??0);
  if(![input,output,image,video].every(finite))return {invalid:true};
  const watts=amount(power.watts),hours=amount(power.hours),tariff=amount(power.tariff);
  const energy=watts===null||hours===null?null:watts/1000*hours;
  const kwh=finite(energy)?energy:null;
  const electricity=kwh===null||tariff===null?null:kwh*tariff;
  const cloud=pricing.models.map(model=>({id:model.id,name:model.name,source:model.source,note:model.note,input:model.input,output:model.output,text:(input*model.input+output*model.output)/1e6,total:(input*model.input+output*model.output)/1e6+image+video}));
  if(!cloud.every(model=>finite(model.text)&&finite(model.total)))return {invalid:true};
  return {input,output,image,video,kwh,local:finite(electricity)?electricity:null,cloud};
 }
 function electricity(watts,hours,cloudKwh){
  const w=amount(watts),h=amount(hours),cloud=amount(cloudKwh),value=w===null||h===null?null:w*h/1000;
  const local=finite(value)?value:null;
  const ratio=local!==null&&local>0&&cloud!==null?cloud/local:null;
  return {local,cloud,ratio:finite(ratio)?ratio:null,difference:local!==null&&cloud!==null?cloud-local:null};
 }
 const api={calculate,electricity};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
 if(typeof window==='undefined')return;
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const usd=value=>value===null?'Enter power assumptions':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:value>0&&value<.01?5:2}).format(value);
 api.section=()=>`<section class="mc-panel frontier-cost" aria-labelledby="frontier-cost-title">
  <div class="mc-panel-header"><div><p class="mc-eyebrow">THE LOCAL AI COST STORY</p><h2 id="frontier-cost-title">Fury power vs cloud AI</h2></div><span class="mc-badge">MONTHLY SCENARIO · USD</span></div>
  <p class="frontier-intro">Illustrative monthly scenario. Adjust power, runtime and tariff for your workload.</p>
  <div class="frontier-assumptions mc-form"><label>Fury average system power (W)<input id="compare-watts" type="number" min="0" step="50" value="1200"></label><label>Fury runtime (hours / month)<input id="compare-hours" type="number" min="0" step="1" value="40"></label><label>Electricity (USD / kWh)<input id="electricity-price" type="number" min="0" step="0.01" value="0.25"></label></div>
  <div class="frontier-context"><span id="frontier-workload"></span><a href="#monthly-workload">Edit workload ↓</a></div>
  <div class="frontier-legend"><span><i class="frontier-key-local"></i>Fury electricity</span><span><i class="frontier-key-cloud"></i>Cloud API + image/video · provider power bundled</span><span id="frontier-asof" class="frontier-asof"></span></div>
  <div id="frontier-bars" class="frontier-bars" role="img" aria-label="Monthly Fury electricity and frontier cloud API cost comparison"></div>
  <p id="frontier-equation" class="mc-form-note"></p>
  <p class="frontier-caveat">Power, runtime and tariff are editable illustrative assumptions. Runtime must cover the workload shown. Local hardware and support are excluded; this is not total ownership cost or a claim of equal outputs. Cloud provider electricity is bundled into API prices, with no separately published per-request power charge to add.</p>
  <details class="frontier-sources"><summary>Rates, sources and what is included</summary><p id="frontier-date" class="mc-form-note"></p><div class="frontier-source-table"><table><thead><tr><th>Text model</th><th>Input / 1M</th><th>Output / 1M</th></tr></thead><tbody id="frontier-rates"></tbody></table></div><p class="mc-form-note">Standard uncached USD rates. Chat: 2,000 input / 600 output tokens; vision: 1,000 / 400; translated page: 900 / 900. Image and video generation use the same Imagen 4 / Veo 3.1 Fast API assumptions for every cloud row. Tokenizers, reasoning usage, throughput and output quality differ. Client-device electricity, taxes, tools and network costs are excluded from both options.</p></details>
  <section id="frontier-energy" class="frontier-energy" aria-labelledby="frontier-energy-title"><div class="mc-panel-header"><div><p class="mc-eyebrow">ELECTRICITY IS A DIFFERENT MEASURE</p><h2 id="frontier-energy-title">One Fury vs cloud electricity</h2></div><span class="mc-badge">kWh / MONTH</span></div><p class="frontier-intro">Compare energy for the same completed workload. Fury uses the whole-system power and runtime above. Cloud energy is an explicit scenario input, separate from its API bill.</p><div id="frontier-energy-inputs" class="frontier-energy-inputs mc-form"></div><div id="frontier-energy-bars" class="frontier-bars" role="img" aria-label="Monthly electricity scenario, in kilowatt-hours"></div><p id="frontier-energy-ratio" class="mc-form-note" aria-live="polite"></p><p class="frontier-caveat">Current model-specific electricity is not inferred from API prices or model size. Unavailable values stay unknown. Include provider servers, idle allocation and cooling in cloud inputs, and use a wall meter for Fury where possible. This comparison excludes training and device/network energy on both sides, and does not establish equal quality or throughput.</p><details class="frontier-sources"><summary>Why there is no automatic “cloud uses more” claim</summary><p class="mc-form-note">Energy changes with prompt length, reasoning, batching, hardware and utilization. A historical primary-source reference is <a href="https://cloud.google.com/blog/products/infrastructure/measuring-the-environmental-impact-of-ai-inference" target="_blank" rel="noopener">Google’s May 2025 Gemini Apps median text prompt: 0.24 Wh</a>, including serving-system overhead. It is not a measurement of the frontier models above or of this mixed image/video workload. At 10,000 prompts it would be 2.4 kWh for that historical text-only reference; it cannot justify a blanket claim that cloud consumes more than this Fury.</p></details></section>
 </section>`;
 let previous='',energyModels='',energyState=null;
 function energyRender(){
  if(!energyState)return;const {pricing,power}=energyState,inputs=document.getElementById('frontier-energy-inputs'),chart=document.getElementById('frontier-energy-bars');if(!inputs||!chart)return;
  const ids=JSON.stringify(pricing.models.map(m=>m.id));
  if(ids!==energyModels){energyModels=ids;inputs.innerHTML=pricing.models.map(m=>'<label>'+esc(m.name)+' cloud electricity (kWh / month)<input data-cloud-energy="'+esc(m.id)+'" type="number" min="0" step="0.1" placeholder="Unknown — enter a sourced estimate"></label>').join('');inputs.addEventListener('input',energyRender)}
  const local=electricity(power.watts,power.hours,null).local;
  const rows=[{name:'HP ZGX Fury',value:local,fury:true},...pricing.models.map(m=>({name:m.name,...electricity(power.watts,power.hours,inputs.querySelector('[data-cloud-energy="'+m.id+'"]').value),value:amount(inputs.querySelector('[data-cloud-energy="'+m.id+'"]').value)}))];
  const max=Math.max(1,...rows.map(r=>r.value??0));
  const number=v=>new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(v);
  chart.innerHTML='<div class="frontier-axis" aria-hidden="true"><span>0 kWh</span><span>'+number(max/2)+'</span><span>'+number(max)+' kWh</span></div>'+rows.map(r=>'<div class="frontier-row '+(r.fury?'frontier-local':'')+'"><div class="frontier-label"><strong>'+esc(r.name)+'</strong><small>'+(r.fury?'Whole-system power × runtime':'Same-workload cloud scenario input')+'</small></div><div class="frontier-track" aria-hidden="true"><i style="width:'+((r.value??0)/max*100)+'%"></i></div><strong class="frontier-value">'+(r.value===null?'Unknown':number(r.value)+' kWh')+'</strong></div>').join('');
  chart.setAttribute('aria-label',rows.map(r=>r.name+': '+(r.value===null?'unknown':number(r.value)+' kilowatt-hours per month')).join('; '));
  const comparisons=rows.slice(1).filter(r=>r.ratio!==null).map(r=>r.name+': '+number(r.ratio)+'× Fury electricity; '+number(Math.abs(r.difference))+' kWh '+(r.difference>0?'more':r.difference<0?'less':'difference')+' under these assumptions.');
  document.getElementById('frontier-energy-ratio').textContent=comparisons.length?comparisons.join(' '):'Enter cloud electricity estimates to calculate how many times more or less energy each scenario uses. Unknown is not zero.';
 }
 api.render=(pricing,counts,power)=>{
  const chart=document.getElementById('frontier-bars');if(!chart)return;
  energyState={pricing,counts,power};energyRender();
  const signature=JSON.stringify([pricing,counts,power]);if(signature===previous)return;previous=signature;
  const c=calculate(pricing,counts,power);
  if(c.invalid){chart.textContent='Workload values are too large to calculate. Reduce the inputs.';return;}
  const local={id:'fury',name:'HP ZGX Fury',total:c.local,local:true};
  const rows=[local,...c.cloud],largest=Math.max(...rows.map(row=>row.total??0),0);
  const base=largest>0?10**Math.floor(Math.log10(largest)):1;
  const maximum=largest>0?[1,2,5,10].map(n=>n*base).find(n=>n>=largest):1;
  const number=value=>new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(value);
  chart.innerHTML='<div class="frontier-axis" aria-hidden="true"><span>'+usd(0)+'</span><span>'+usd(maximum/2)+'</span><span>'+usd(maximum)+'</span></div>'+rows.map(row=>'<div class="frontier-row '+(row.local?'frontier-local':'')+'" data-frontier-id="'+esc(row.id)+'"><div class="frontier-label"><strong>'+esc(row.name)+'</strong><small>'+(row.local?'Electricity only':'AI API charge · power included')+'</small></div><div class="frontier-track" aria-hidden="true"><i style="width:'+((row.total??0)/maximum*100)+'%"></i></div><strong class="frontier-value" data-usd="'+(row.total===null?'':row.total)+'">'+usd(row.total)+'</strong></div>').join('');
  chart.setAttribute('aria-label',rows.map(row=>row.name+': '+usd(row.total)+' per month').join('; '));
  document.getElementById('frontier-workload').textContent=number(amount(counts.prompts)??0)+' chats · '+number(amount(counts.images)??0)+' images · '+number(amount(counts.video)??0)+' video seconds · '+number(amount(counts.vision)??0)+' vision images · '+number(amount(counts.pages)??0)+' pages';
  document.getElementById('frontier-equation').textContent=c.local===null?'Enter nonnegative power, runtime and tariff values. Cloud estimates remain visible.':number(Number(power.watts))+' W ÷ 1,000 × '+number(Number(power.hours))+' hours × '+usd(Number(power.tariff))+'/kWh = '+usd(c.local)+' Fury electricity / month · '+number(c.kwh)+' kWh.';
  document.getElementById('frontier-asof').textContent='Rates checked '+pricing.checked;
  document.getElementById('frontier-date').textContent='Representative frontier models as of '+pricing.checked+'; not a performance or usage ranking. Official text rates checked '+pricing.checked+'. Prices are cached locally; no paid cloud calls. '+(pricing.models.some(m=>m.effective_until)?'Time-limited promotions and their expiry are shown below.':'');
  document.getElementById('frontier-rates').innerHTML=c.cloud.map(m=>'<tr><td><a href="'+esc(m.source)+'" target="_blank" rel="noopener">'+esc(m.name)+' ↗</a><small>'+esc(m.note)+'</small></td><td>'+usd(m.input)+'</td><td>'+usd(m.output)+'</td></tr>').join('');
 };
 window.FuryFrontierCost=api;
})();
