/* Dated, offline cost scenarios. No provider requests or estimated token counts. */
'use strict';
window.NanoEconomics=(()=>{
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const count=value=>Number(value).toLocaleString('en-US');
  const money=value=>Number(value).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:0,maximumFractionDigits:2});
  const valid=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
  function project(tokens,config,overrides={}){
    if(!config?.models?.length||!valid(tokens?.input_tokens)||!valid(tokens?.output_tokens)||tokens.output_tokens===0)return null;
    const customers=config.customers_per_employee_day,employees=config.employees,days=config.days_per_month,months=config.months_per_year;
    const electricity={...config.electricity,...overrides};
    for(const key of Object.keys(electricity))electricity[key]=Number(electricity[key]);
    if(![customers,employees,days,months,...Object.values(electricity)].every(valid))return null;
    const dailyRuns=customers*employees,monthlyRuns=dailyRuns*days,annualRuns=monthlyRuns*months;
    const usage=runs=>({input:tokens.input_tokens*runs,output:tokens.output_tokens*runs,total:(tokens.input_tokens+tokens.output_tokens)*runs});
    const kwh=electricity.devices*electricity.watts/1000*electricity.hours_per_day*days;
    const monthlyElectricity=kwh*electricity.usd_per_kwh;
    const cloud=config.models.map(model=>{
      const perRun=(tokens.input_tokens*model.input+tokens.output_tokens*model.output)/1e6;
      return {...model,monthly:perRun*monthlyRuns,annual:perRun*annualRuns};
    });
    return {customers,employees,days,months,dailyRuns,monthlyRuns,annualRuns,electricity,kwh,
      daily:usage(dailyRuns),monthly:usage(monthlyRuns),annual:usage(annualRuns),
      rows:[{name:'HP ZGX Nano',local:true,monthly:monthlyElectricity,annual:monthlyElectricity*months},...cloud]};
  }
  function chart(title,period,projection){
    const max=Math.max(...projection.rows.map(row=>row[period]),1);
    return `<section class="panel cost-chart" aria-label="${esc(title)} operating cost comparison"><div class="chart-heading"><h2>${esc(title)}</h2><span>USD / ${period==='monthly'?'30 days':'360 days'}</span></div><div class="chart-zero">$0 <span>Each chart starts at zero · linear scale</span></div>${projection.rows.map(row=>`<div class="cost-row ${row.local?'nano-cost':''}"><div class="cost-label"><strong>${esc(row.name)}</strong><small>${row.local?'Electricity only · $0 token fees':`$${row.input} in / $${row.output} out per 1M`}</small></div><div class="cost-bar"><svg viewBox="0 0 1000 24" preserveAspectRatio="none" aria-hidden="true"><rect class="bar-track" width="1000" height="24" rx="4"/><rect class="bar-fill" width="${(row[period]/max*1000).toFixed(3)}" height="24" rx="4"/></svg></div><strong class="cost-value">${money(row[period])}</strong></div>`).join('')}</section>`;
  }
  function render(state,config,overrides,exit){
    const tokens=state.telemetry?.pricing_totals,projection=project(tokens,config,overrides);
    if(!projection)return `<div class="content economics-empty panel"><div class="section">Cloud vs local / monthly + yearly</div><h2>${config?'Complete a live presentation to calculate the comparison.':'Frontier pricing is unavailable.'}</h2><p>${config?'Actual recorded text tokens power the projections. Warmup and recorded playback are excluded.':'Reload the stage to load the bundled pricing snapshot.'}</p>${exit}</div>`;
    const p=projection;
    const metric=(title,usage,runs)=>`<article><span class="section">${title}</span><strong>${count(usage.output)} <small>output tokens</small></strong><span>${count(usage.input)} input · ${count(usage.total)} total</span><small>${count(runs)} customer workflows</small></article>`;
    return `<div class="content economics-layout"><div class="projection-baseline"><span><b>This live presentation</b> · ${count(tokens.output_tokens)} output + ${count(tokens.input_tokens)} input text tokens</span><span class="local-proof">${state.telemetry.cloud_bytes===0?'0 bytes to cloud': 'Cloud bytes unavailable'} · ${state.telemetry.external_calls==null?'API counter unavailable':`${count(state.telemetry.external_calls)} external AI calls`}</span></div>
      <div class="projection-scale" aria-label="Workload scaling assumptions"><div><strong>1</strong><span>presentation per customer</span></div><b aria-hidden="true">×</b><div><strong>${count(p.customers)}</strong><span>customers / employee / day<small>${count(tokens.output_tokens*p.customers)} output tokens / employee / day</small></span></div><b aria-hidden="true">×</b><div><strong>${count(p.employees)}</strong><span>employees</span></div><b aria-hidden="true">×</b><div><strong>${count(p.days)}</strong><span>days / month</span></div><b aria-hidden="true">×</b><div><strong>${count(p.months)}</strong><span>months / year</span></div></div>
      <div class="projection-usage">${metric('Today / team',p.daily,p.dailyRuns)}${metric('One month / team',p.monthly,p.monthlyRuns)}${metric('One year / team',p.annual,p.annualRuns)}</div>
      <div class="cost-charts">${chart('Monthly cost','monthly',p)}${chart('Yearly cost','annual',p)}</div>
      <div class="economics-notes"><p>Cloud: text API fees at ${esc(config.checked)} rates, held constant. Images, vision, audio, tools and discounts excluded; model outputs differ. Gemini promo ends Nov 30; yearly view holds today’s rate.</p><p>Nano: ${count(p.electricity.devices)} devices × ${count(p.electricity.watts)} W × ${count(p.electricity.hours_per_day)} h/day × ${p.days} days × ${money(p.electricity.usd_per_kwh)}/kWh = ${count(p.kwh)} kWh/month. Assumed power; hardware and support excluded.</p></div>
      <div class="economics-bottom"><span>Local intelligence. No per-token bill.</span><div><button class="free-exit" data-economics-open>Assumptions & pricing sources</button>${exit}</div></div></div>`;
  }
  function settings(config,overrides){
    if(!config)return '<button data-economics-close>Close</button>';
    const values={...config.electricity,...overrides};
    const field=(key,label,min,max,step)=>`<label>${label}<input name="${key}" type="number" required min="${min}" max="${max}" step="${step}" value="${esc(values[key])}"></label>`;
    return `<div class="economics-dialog-heading"><h2 id="economics-title">Electricity & pricing assumptions</h2><button type="button" data-economics-close aria-label="Close assumptions">×</button></div><p>One presentation for each of 10 customers per employee per day × 200 employees × 30 days × 12 months. All yearly costs annualize the dated rates across 360 days.</p><form><div class="electricity-fields">${field('devices','Nano devices (default: one per employee)',1,200,1)}${field('watts','Average wall power per Nano (W)',1,1000,1)}${field('hours_per_day','Powered hours per day',0.1,24,0.1)}${field('usd_per_kwh','Electricity price (USD / kWh)',0,10,0.001)}</div><p>These are editable assumptions, not measured wall power. Fewer devices assume shared capacity; this calculation does not validate throughput. Power outside the selected hours is excluded.</p><button type="submit">Apply electricity assumptions</button></form><h3>Official standard API rates · checked ${esc(config.checked)}</h3><div class="pricing-table"><table><thead><tr><th>Model / source</th><th>Input / 1M</th><th>Output / 1M</th></tr></thead><tbody>${config.models.map(model=>`<tr><td><a href="${esc(model.source)}" target="_blank" rel="noopener noreferrer">${esc(model.name)} ↗</a><small>${esc(model.note)}</small></td><td>${money(model.input)}</td><td>${money(model.output)}</td></tr>`).join('')}</tbody></table></div><p>${esc(config.scope)}</p>`;
  }
  return {project,render,settings};
})();
