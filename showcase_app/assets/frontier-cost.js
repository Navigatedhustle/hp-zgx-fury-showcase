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
 const api={calculate};
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
 </section>`;
 let previous='';
 api.render=(pricing,counts,power)=>{
  const chart=document.getElementById('frontier-bars');if(!chart)return;
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
