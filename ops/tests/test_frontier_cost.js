/* Independent arithmetic cases for the public monthly comparison. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {calculate,electricity}=require('../../showcase_app/assets/frontier-cost.js');
const pricing=require('../../config/event-pricing.json');
const counts={prompts:10000,images:1000,video:1000,vision:5000,pages:1000};
const power={watts:1200,hours:40,tariff:.25};
test('same monthly workload is priced for every model, with one shared media charge',()=>{
 const c=calculate(pricing,counts,power);
 assert.equal(c.input,25900000);assert.equal(c.output,8900000);
 assert.equal(c.image,40);assert.equal(c.video,100);
 assert.equal(c.kwh,48);assert.equal(c.local,12);
 assert.equal(c.cloud.find(m=>m.id==='gpt-6-astra').total,844);
 assert.equal(c.cloud.find(m=>m.id==='claude-fable-5-1').total,844);
 assert.equal(c.cloud.find(m=>m.id==='claude-opus-5-5').total,421.6);
 assert.equal(c.cloud.find(m=>m.id==='gemini-4-argon').total,280.8);
});
test('free tariff and zero workload are real zeros',()=>{
 assert.equal(calculate(pricing,counts,{...power,tariff:0}).local,0);
 const c=calculate(pricing,{}, {...power,hours:0});
 assert.equal(c.local,0);assert.ok(c.cloud.every(m=>m.total===0));
});
test('missing or invalid power assumptions are unavailable, not zero or a fabricated saving',()=>{
 for(const value of ['',undefined,null,-1,'bad',Infinity]){
  assert.equal(calculate(pricing,counts,{...power,tariff:value}).local,null);
  assert.equal(calculate(pricing,counts,{...power,hours:value}).local,null);
  assert.equal(calculate(pricing,counts,{...power,watts:value}).local,null);
 }
});
test('expired promotional prices supplied by server change text only; no provider energy double count',()=>{
 const expired={...pricing,models:pricing.models.map(m=>m.id==='gemini-4-argon'?{...m,input:4,output:20}:m)};
 const c=calculate(expired,counts,power);
 assert.equal(c.cloud.find(m=>m.id==='gemini-4-argon').total,421.6);
 assert.equal(c.local,12);
});
test('overflow never appears as a numeric cost or a zero-cost claim',()=>{
 assert.equal(calculate(pricing,{...counts,prompts:1e308},power).invalid,true);
 assert.equal(calculate(pricing,{...counts,prompts:1e304},power).invalid,true);
 assert.equal(calculate(pricing,counts,{...power,watts:1e308,hours:1e308}).local,null);
});
test('electricity compares explicit same-workload kWh, independent of API prices',()=>{
 assert.deepEqual(electricity(1200,40,240),{local:48,cloud:240,ratio:5,difference:192});
 assert.deepEqual(electricity(1200,40,2.4),{local:48,cloud:2.4,ratio:.049999999999999996,difference:-45.6});
});
test('unknown electricity is never a zero or an invented efficiency ratio',()=>{
 for(const v of ['',null,undefined,-1,Infinity,'bad'])assert.equal(electricity(1200,40,v).ratio,null);
 assert.equal(electricity(0,40,12).ratio,null);
 assert.deepEqual(electricity(1200,40,0),{local:48,cloud:0,ratio:0,difference:-48});
 assert.equal(electricity(1e308,1e308,1).local,null);
});
