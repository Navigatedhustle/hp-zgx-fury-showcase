'use strict';
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const active = job => ['queued', 'running', 'cancelling'].includes(job.status);
  const labels = {atlas:'Ask Atlas', slides:'Create presentation', factory:'Build application', images:'Generate artwork', vision:'Analyze image', translate:'Translate document', voice:'Generate narration'};
  let state, view = location.pathname.split('/')[2] || 'home', polling = false, toastTimer;
  const latest = {}, rendered = {}, histories = {}, slideIndices = {}, uploads = {};
  const file = (job, name, download = false) => `/free/files/${encodeURIComponent(job.id)}/${encodeURIComponent(name)}${download ? '?download=true' : ''}`;
  function toast(message) {
    const element = $('#toast'); element.textContent = message; element.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => {element.hidden = true;}, 8500);
  }
  async function api(path, options = {}) {
    const response = await fetch('/free/api/' + path, {...options, headers: {'Content-Type':'application/json', ...options.headers}});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.[0]?.msg || data.error || 'The Nano could not complete the request.');
    return data;
  }
  function field(id, title, input) {return `<label for="${id}">${title}${input}</label>`;}
  function select(id, title, values) {return field(id, title, `<select id="${id}">${values.map(item => `<option>${esc(item)}</option>`).join('')}</select>`);}
  function controls(item) {
    const id = item.id;
    let content = field(`${id}-prompt`, ({atlas:'Your question', slides:'Presentation brief', factory:'What would you like to build?', images:'Describe the image', vision:'What should Qwen look for?', translate:'Source text', voice:'English narration'})[id], `<textarea id="${id}-prompt" maxlength="${id === 'voice' ? 900 : id === 'images' ? 1500 : 9000}" rows="${id === 'translate' ? 10 : 6}" required>${esc(item.prompt)}</textarea>`);
    if (id === 'atlas') content += '<p class="help">Grounded in four fictional Northwind account files. Follow-up questions retain this conversation. General answers use model knowledge without web verification.</p><button class="quiet new-chat" type="button">New conversation</button>';
    if (id === 'slides') content += select('slides-count', 'Number of slides', [3,4,5,6,7,8]) + '<p class="help">Use a short brief with the facts you want included. Editable text and shapes in PowerPoint; local SVG previews.</p>';
    if (id === 'factory') content += '<p class="help">Nano builds self-contained HTML, CSS and JavaScript apps. Live browser smoke checks cover loading, controls, script errors and network isolation. Review calculations and behavior before use. Backend services and packages are unavailable.</p>';
    if (id === 'images') content += select('images-style', 'Art direction', ['Studio','Photographic','Architectural','Illustration','Cinematic']) + '<div class="field-row">' + select('images-size','Image size',['1024 × 576','1344 × 768']) + select('images-batch','Images',[1,2,4]) + '</div>' + field('images-seed','Seed','<input id="images-seed" type="number" min="0" max="4294967295" value="42" required>') + '<p class="help">Wordless artwork. Your subject and style guide the render; every image passes local lettering review before display. Exact reproducibility can vary.</p>';
    if (id === 'vision') content += select('vision-sample','Image source',['Sample whiteboard','Sample chart','Public demonstration image']) + field('vision-file','Public / fictional image only','<input id="vision-file" type="file" accept="image/png,image/jpeg,image/webp">') + '<p class="help">Use fictional or public demonstration material. Visitor photos belong only in the consented Action Trailer flow, which is unavailable in this profile. Large images are resized locally.</p>';
    if (id === 'translate') content += select('translate-language','Target language',state.languages) + field('translate-file','Or load a document','<input id="translate-file" type="file" accept=".txt,.docx,.pdf">') + '<p class="help">UTF-8 TXT, DOCX or text PDF · 500 KB · up to 4 PDF pages / 9,000 characters. Clean text reflow with page boundaries. Scanned PDFs require OCR. Language quality needs human review.</p>';
    if (id === 'voice') content += select('voice-name','Voice',['Michael · American English','Heart · American English']) + '<p class="help">Up to 900 characters. Synthesized with local Kokoro on CPU. Playback starts only when you press Play.</p>';
    return content + `<div class="form-actions"><button type="submit" class="primary">${labels[id]} ↗</button></div>`;
  }
  const paths = {
    atlas:'M8 10h8M8 14h5M5 4h14v14H9l-4 3V4Z',
    slides:'M3 5h18v13H3Zm5 17 4-4 4 4M8 9h8M8 13h5',
    factory:'m8 7-5 5 5 5m8-10 5 5-5 5m-3-14-2 18',
    images:'M3 4h18v16H3Zm0 12 6-6 5 5 3-3 4 4M17 8h.01',
    vision:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm7 0a3 3 0 1 0 6 0 3 3 0 0 0-6 0',
    translate:'M3 5h12M9 2v3M5 5c0 7 7 10 7 10M13 5c0 7-7 10-7 10m8 6 4-11 4 11m-6-4h4',
    voice:'M8 6a4 4 0 0 1 8 0v6a4 4 0 0 1-8 0Zm-4 5a8 8 0 0 0 16 0m-8 8v4m-4 0h8'
  };
  function glyph(id) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[id] || paths.atlas}"/></svg>`; }
  function agentVisual(id) {return `<div class="agent-visual agent-${id}" aria-hidden="true"><svg viewBox="0 0 220 150" fill="none"><ellipse class="agent-ring" cx="110" cy="89" rx="82" ry="44"/><ellipse class="agent-ring inner" cx="110" cy="89" rx="64" ry="34"/><path class="agent-circuit" d="M10 90h30m140 0h30M110 6v20M48 37l18 14m88 0 18-14"/><path class="agent-shell" d="M76 52 91 36h38l15 16 5 40-16 22H87L71 92Z"/><path class="agent-face" d="M82 58h56l3 29-13 14H92L79 87Z"/><path class="agent-eyes" d="M91 73h12m14 0h12M104 90h12"/><path class="agent-circuit" d="M91 117h38m-44 6h50m-57 8h64"/><circle class="agent-node" cx="39" cy="90" r="4"/><circle class="agent-node" cx="181" cy="90" r="4"/></svg><span class="agent-capability">${glyph(id)}</span></div>`;}
  function initialize() {
    $('#navigation').insertAdjacentHTML('beforeend', state.catalog.map(item => `<a href="/free/${item.id}" data-view="${item.id}" aria-label="${esc(item.name)}"><span class="nav-icon">${glyph(item.id)}</span><span>${item.name}</span></a>`).join(''));
    $('#home-view').innerHTML = `<div class="hero"><div class="hero-copy"><div class="eyebrow"><span class="signal-dot"></span> THE NEXT ERA IS LOCAL</div><h1>Small machine.<br><span>Extraordinary minds.</span></h1><p>Meet your team of AI agents. Think bigger, build faster, and create something remarkable. All on your HP ZGX Nano.</p><div class="hero-cta"><button class="primary" id="open-rush">Launch Nano Rush <span>↗</span></button><a href="/free/factory" data-view="factory" class="hero-secondary">Meet your agents ${glyph('factory')}</a></div><div class="hero-proof"><span><i></i> Four local models</span><span>One powerful workspace</span></div></div><div class="hero-art"><div class="hero-grid"></div><img src="/stage/agent-art" class="hero-robot" alt="Original futuristic robot companion artwork" fetchpriority="high"><div class="agent-id"><span class="signal-dot"></span> NANO AGENT <b>01</b></div><div class="art-caption"><span class="caption-cross">+</span><div>Intelligence. In your hands.<small>HP ZGX NANO G1n / NVIDIA GB10</small></div><span class="art-label">AI ARTWORK</span></div></div></div><div class="metrics"><div class="metric"><span class="metric-index">01 / EXPLORE</span><b>${state.catalog.length}<em> experiences</em></b><span>ONE CONNECTED WORKSPACE</span></div><div class="metric"><span class="metric-index">02 / COMPUTE</span><b id="home-resident">—</b><span>RESIDENT AI MODELS</span></div><div class="metric"><span class="metric-index">03 / CAPACITY</span><b id="home-memory">—</b><span>UNIFIED MEMORY USED / TOTAL</span></div><div class="metric"><span class="metric-index">04 / SYSTEM</span><b id="home-ready">—</b><span>LIVE MODEL READINESS</span></div></div><div class="section-heading"><div><div class="eyebrow">YOUR AI COLLECTIVE</div><h2>What will you create?</h2></div><small>Seven specialities. Infinite possibilities.</small></div><div class="cards">${state.catalog.map((item,index) => `<a class="card accent-${item.id}" href="/free/${item.id}" data-view="${item.id}"><div class="card-head"><span class="card-type">${esc(item.tag.toUpperCase())}</span><span class="card-number">0${index+1}</span></div>${agentVisual(item.id)}<div class="card-title"><h3>${item.name}</h3><span class="card-arrow">↗</span></div><p>${esc(item.description)}</p><div class="card-foot"><span>${esc(item.model)}</span><span class="card-ready">● LOCAL</span></div></a>`).join('')}</div><div class="local-manifest"><div class="manifest-symbol">◎</div><div><h3>Big ideas. Local intelligence.</h3><p>Your prompts and model inference stay on this Nano. Supplied business examples are fictional; review generated work before use.</p></div><a href="/free/models" data-view="models">Explore the models ↗</a></div>`;
    $('#workspaces').innerHTML = state.catalog.map(item => `<section class="workspace accent-${item.id}" id="workspace-${item.id}" hidden><div class="workspace-heading"><div><div class="eyebrow">NANO AGENT / ${esc(item.tag.toUpperCase())}</div><h1>${item.name}</h1><p>${esc(item.description)}</p></div><span class="model-pill">${esc(item.model)} / LOCAL</span></div><div class="workspace-grid"><section class="control-panel"><div class="panel-title"><span>Your workspace</span><small>LIVE GENERATION</small></div><form class="controls" id="form-${item.id}" data-demo="${item.id}">${controls(item)}</form></section><section class="output-panel"><div class="panel-title"><span>${item.id === 'atlas' ? 'Conversation' : 'Output'}</span><small id="output-state-${item.id}">READY WHEN YOU ARE</small></div><div class="output-content" id="output-${item.id}"><div class="empty-output"><div class="workspace-agent">${agentVisual(item.id)}</div><h3>Your agent is ready.</h3><p>${esc(item.description)}</p></div></div></section></div></section>`).join('');
    $('#open-rush').addEventListener('click', openRush);
    for (const form of document.querySelectorAll('form[data-demo]')) form.addEventListener('submit', submit);
    $('.new-chat').addEventListener('click', () => {histories.atlas = []; latest.atlas = ''; rendered.atlas = ''; $('#output-atlas').replaceChildren(); toast('New Atlas conversation started. Previous outputs remain in Jobs & outputs.');});
    $('#translate-file').addEventListener('change', readDocument);
    $('#vision-file').addEventListener('change', readImage);
    showView(view, false);
  }
  function showView(next, push = true) {
    if (!['home','jobs','models',...state.catalog.map(item => item.id)].includes(next)) next = 'home';
    view = next;
    for (const id of ['home','jobs','models']) $(`#${id}-view`).hidden = next !== id;
    for (const workspace of document.querySelectorAll('.workspace')) workspace.hidden = workspace.id !== 'workspace-' + next;
    for (const link of document.querySelectorAll('[data-view]')) {link.classList.toggle('active', link.dataset.view === next);if(link.dataset.view===next)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
    $('#page-name').textContent = state.catalog.find(item => item.id === next)?.name || ({home:'Mission Control',jobs:'Jobs & outputs',models:'Model Hub'})[next];
    if (push) history.pushState({},'', '/free' + (next === 'home' ? '' : '/' + next));
    if (next === 'jobs') renderJobs();
    if (next === 'models') renderModels();
    window.scrollTo(0,0);
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-view]');
    if (link && state && !event.metaKey && !event.ctrlKey) {event.preventDefault();showView(link.dataset.view);}
  });
  window.addEventListener('popstate', () => {if (state) showView(location.pathname.split('/')[2] || 'home', false);});
  function specification(demo) {
    const spec = {demo, prompt:$(`#${demo}-prompt`).value.trim()};
    if (!spec.prompt || spec.prompt.length < 3) throw new Error(`Enter at least three characters for ${demo}.`);
    if (demo === 'atlas') spec.history = (histories.atlas || []).slice(-8).map(({role,content})=>({role,content}));
    if (demo === 'slides') spec.slide_count = Number($('#slides-count').value);
    if (demo === 'images') {
      spec.style = $('#images-style').value; spec.seed = Number($('#images-seed').value); spec.batch = Number($('#images-batch').value);
      [spec.width,spec.height] = $('#images-size').value.split(' × ').map(Number);
    }
    if (demo === 'vision') {
      const source = $('#vision-sample').selectedIndex;
      spec.sample = source === 0 ? 'whiteboard.png' : source === 1 ? 'chart.png' : '';
      if (!spec.sample) {if (!uploads.vision) throw new Error('Choose a public demonstration image first.'); spec.image_base64 = uploads.vision;}
    }
    if (demo === 'translate') spec.language = $('#translate-language').value;
    if (demo === 'voice') spec.voice = $('#voice-name').selectedIndex ? 'af_heart' : 'am_michael';
    return spec;
  }
  async function submit(event) {
    event.preventDefault(); const form = event.currentTarget, demo = form.dataset.demo, button = $('button[type=submit]',form);
    button.disabled = true;
    try {
      const job = await api('jobs',{method:'POST',body:JSON.stringify(specification(demo))});
      latest[demo] = job.id; rendered[demo] = ''; state.jobs.unshift(job); renderOutput(job); toast('Job queued on the Nano. You can explore another workspace while it runs.');
    } catch (error) {toast(error.message);} finally {button.disabled = false;}
  }
  function downloadLinks(job) {
    const files = (job.result?.files || []).filter(name => !name.endsWith('.svg') && name !== 'app.html');
    return files.length ? `<div class="downloads">${files.map(name => `<a href="${file(job,name,true)}" download>${esc(name)} ↓</a>`).join('')}</div>` : '';
  }
  function provenance(job) {
    const calls = job.calls || [];
    const tokens = calls.reduce((sum,row) => sum + (row.usage?.completion_tokens || 0),0);
    const models = [...new Set(calls.map(row => row.model))];
    if (job.result?.model) models.push(job.result.model);
    return `<p class="provenance">${esc([...new Set(models)].join(' + ') || 'Local Nano models')}${job.ended && job.started ? ` · ${(job.ended-job.started).toFixed(1)} s` : ''}${tokens ? ` · ${tokens.toLocaleString()} measured output tokens` : ''}${calls.filter(row=>row.routing).map(row=>'<br>' + esc(row.routing)).join('')}</p>`;
  }
  function renderOutput(job, force = false) {
    const demo = job.demo, target = $(`#output-${demo}`);
    if (!target) return;
    const signature = [job.id,job.status,job.phase,job.partial?.length,job.images_done,job.revision].join('/');
    if (!force && rendered[demo] === signature) return;
    rendered[demo] = signature;
    $(`#output-state-${demo}`).textContent = job.status.toUpperCase();
    const button = $(`#form-${demo} button[type=submit]`);
    button.disabled = state.mode !== 'free' || state.jobs.some(row=>row.demo===demo && active(row));
    if (active(job)) {
      target.innerHTML = `<div class="live-state"><span class="working-agent" aria-hidden="true">${glyph(demo)}</span><span class="spinner"></span><span>${esc(job.phase)}${job.images_done ? ` / ${job.images_done} image(s) reviewed` : ''}</span><button class="quiet cancel-job">Cancel</button></div>${job.plan ? `<p class="provenance">${esc(job.plan)}</p>` : ''}<pre class="text-output">${esc(job.partial || 'The Nano is working. This output updates as the model responds.')}</pre>`;
      $('.cancel-job',target).addEventListener('click',()=>cancelJob(job.id));
      return;
    }
    if (job.status !== 'complete') {target.innerHTML=`<p class="error">${esc(job.error || 'This job was cancelled.')}</p><p class="help">Your inputs are retained. Adjust the brief and run it again.</p>`;return;}
    const result = job.result || {};
    let html = '';
    if (demo === 'atlas') {
      if (!histories.atlas) histories.atlas = [];
      if (histories.atlas.at(-1)?.job !== job.id) histories.atlas.push({role:'user',content:job.prompt}, {role:'assistant',content:result.text,job:job.id});
      html = histories.atlas.map(row=>`<div class="chat-turn ${row.role}"><div class="who">${row.role==='user'?'YOU':'ATLAS'}</div><pre class="text-output">${esc(row.content)}</pre></div>`).join('');
      html += '<p class="provenance">Grounding: ' + result.sources.map(esc).join(' · ') + '</p>';
    } else if (demo === 'slides') {
      const index = Math.min(slideIndices[job.id] || 0,result.previews.length-1);
      html = `<img class="slide-preview" alt="Slide ${index+1}: ${esc(result.deck.slides[index].title)}" src="${file(job,result.previews[index])}?v=${job.revision || 0}"><div class="slide-controls"><button class="quiet slide-prev" aria-label="Previous slide">←</button><span>${index+1} / ${result.previews.length}</span><button class="quiet slide-next" aria-label="Next slide">→</button></div><details class="editor"><summary>Edit this slide</summary><form class="slide-edit">${field('edit-title','Title',`<input id="edit-title" value="${esc(result.deck.slides[index].title)}" maxlength="65" required>`)}${field('edit-subtitle','Subtitle',`<input id="edit-subtitle" value="${esc(result.deck.slides[index].subtitle)}" maxlength="110">`)}${field('edit-points','Points · one per line',`<textarea id="edit-points" required>${esc(result.deck.slides[index].points.join('\n'))}</textarea>`)}${field('edit-notes','Speaker notes',`<textarea id="edit-notes" maxlength="700">${esc(result.deck.slides[index].notes)}</textarea>`)}<button class="primary" type="submit">Save slide & rebuild PowerPoint</button></form></details>`;
    } else if (demo === 'factory') html = `<iframe class="app-frame" title="Generated browser application" sandbox="allow-scripts" src="${file(job,result.preview)}"></iframe><p class="provenance">${esc(result.checks)}</p><details class="editor"><summary>View the agent plan</summary><pre class="text-output">${esc(result.plan)}</pre></details>`;
    else if (demo === 'images') html = `<div class="gallery">${result.images.map((name,index)=>`<a href="${file(job,name,true)}" download><img src="${file(job,name)}" alt="Locally generated artwork ${index+1}"></a>`).join('')}</div><p class="provenance">Seed ${esc(result.seed)} · local lettering review passed for every displayed image</p>`;
    else if (demo === 'voice') html = `<div class="empty-output"><div class="orb"></div><h3>Your voice, ready.</h3><audio controls src="${file(job,result.audio)}"></audio><p>Kokoro · 24 kHz · American English</p></div>`;
    else html = `${result.input ? `<img class="vision-input" src="${file(job,result.input)}" alt="Analyzed demonstration input">` : ''}<pre class="text-output">${esc(result.text)}</pre>`;
    target.innerHTML = html + provenance(job) + downloadLinks(job);
    if (demo === 'slides') {
      $('.slide-prev',target).addEventListener('click',()=>{slideIndices[job.id]=Math.max(0,(slideIndices[job.id]||0)-1);renderOutput(job,true);});
      $('.slide-next',target).addEventListener('click',()=>{slideIndices[job.id]=Math.min(result.previews.length-1,(slideIndices[job.id]||0)+1);renderOutput(job,true);});
      $('.slide-edit',target).addEventListener('submit',async event=>{
        event.preventDefault(); const form=event.currentTarget, save=$('button',form); save.disabled=true;
        try {
          const deck=structuredClone(result.deck), slide=deck.slides[slideIndices[job.id]||0];
          slide.title=$('#edit-title',form).value; slide.subtitle=$('#edit-subtitle',form).value;
          slide.points=$('#edit-points',form).value.split('\n').map(row=>row.trim()).filter(Boolean); slide.notes=$('#edit-notes',form).value;
          const updated=await api(`jobs/${job.id}/deck`,{method:'PUT',body:JSON.stringify(deck)});
          state.jobs=state.jobs.map(row=>row.id===job.id?updated:row);renderOutput(updated,true);toast('Slide and editable PowerPoint updated.');
        } catch(error) {toast(error.message);save.disabled=false;}
      });
    }
  }
  function renderJobs() {
    $('#jobs-view').innerHTML = `<div class="workspace-heading"><div><div class="eyebrow">MEASURED WORK / RETAINED OUTPUTS</div><h1>Jobs & outputs</h1><p>Follow the queue, reopen a workspace, or download the result. The latest 50 jobs are retained on this Nano.</p></div></div><div class="jobs-list">${state.jobs.map(job=>`<div class="job-row"><div>${esc(state.catalog.find(item=>item.id===job.demo)?.name)}<small>${new Date(job.created*1000).toLocaleString()}</small></div><div class="job-prompt">${esc(job.prompt)}<small>${esc(job.phase)}</small></div><span class="badge ${job.status}">${esc(job.status)}</span><div class="job-buttons"><button data-open="${job.id}">Open ↗</button>${active(job)?`<button data-cancel="${job.id}">Cancel</button>`:`<button data-delete="${job.id}" aria-label="Delete ${esc(job.demo)} output">Delete</button>`}</div></div>`).join('') || '<p>No jobs yet. Choose an experience to begin.</p>'}</div>`;
    for(const button of document.querySelectorAll('[data-open]'))button.addEventListener('click',()=>{const job=state.jobs.find(row=>row.id===button.dataset.open);latest[job.demo]=job.id;renderOutput(job,true);showView(job.demo);});
    for(const button of document.querySelectorAll('[data-cancel]'))button.addEventListener('click',()=>cancelJob(button.dataset.cancel));
    for(const button of document.querySelectorAll('[data-delete]'))button.addEventListener('click',async()=>{try{await api('jobs/'+button.dataset.delete,{method:'DELETE'});for(const demo of Object.keys(latest))if(latest[demo]===button.dataset.delete){latest[demo]=null;rendered[demo]='';$(`#output-${demo}`).textContent='Output deleted. Run this experience to create another.';}await poll();toast('Output deleted from this Nano.');}catch(error){toast(error.message);}});
  }
  function renderModels() {
    const definitions = [{id:'lead',name:'gpt-oss-120b',role:'Executive reasoning and app planning',detail:'MXFP4 · 2 serving slots · 16K context per slot'}, {id:'text',name:'Qwen3.6-35B-A3B',role:'Writing, code, vision and translation',detail:'UD-Q4_K_XL · F16 vision projector · 3 serving slots'}, {id:'image',name:'FLUX.2 klein 4B',role:'Local image generation',detail:'BF16 image model · FP8 text encoder · sequential image queue'}, {id:'tts',name:'Kokoro 82M',role:'English voice synthesis',detail:'CPU resident · Michael / Heart · 24 kHz'}];
    $('#models-view').innerHTML = `<div class="workspace-heading"><div><div class="eyebrow">ONE SYSTEM / FOUR LOCAL MODELS</div><h1>Model Hub</h1><p>Both demo modes share the same resident stack. No second copy of the models is loaded.</p></div></div><div class="models">${definitions.map(item=>`<article class="model-card"><div class="eyebrow">${esc(item.role.toUpperCase())}</div><h3>${item.name}</h3><p>${item.detail}</p><span class="${state.health[item.id]?.ready?'ready':'offline'}">${state.health[item.id]?.ready?'● Resident and responding':'○ Starting or unavailable'}</span></article>`).join('')}</div><p class="exclusions">Language calls, routing reasons and measured token counts use the existing local gateway. Busy lead-lane requests may visibly route to Qwen under the Nano admission policy. Image generation is bounded to one active job. External inference calls: ${state.telemetry.external_calls ?? 'unknown'}.</p>`;
  }
  async function cancelJob(id) {try {await api(`jobs/${id}/cancel`,{method:'POST',body:'{}'});await poll();toast('Cancellation completed.');}catch(error){toast(error.message);}}
  function openRush() {
    try {const specs=state.catalog.filter(item=>item.id!=='voice').map(item=>specification(item.id));$('#rush-summary').innerHTML=specs.map(spec=>`<div class="rush-line"><strong>${esc(state.catalog.find(item=>item.id===spec.demo).name)}</strong><span>${esc(spec.prompt)}</span></div>`).join('');$('#rush-dialog').showModal();}catch(error){toast(error.message);}
  }
  $('#confirm-rush').addEventListener('click',async event=>{
    const button=event.currentTarget;button.disabled=true;
    try {const result=await api('rush',{method:'POST',body:JSON.stringify(state.catalog.filter(item=>item.id!=='voice').map(item=>specification(item.id)))});for(const job of result.jobs){latest[job.demo]=job.id;rendered[job.demo]='';}$('#rush-dialog').close();await poll();showView('jobs');toast('Six real jobs queued. Open any workspace to follow its output.');}catch(error){toast(error.message);}finally{button.disabled=false;}
  });
  async function readDocument(event) {
    const selected=event.target.files[0];if(!selected)return;
    if(selected.size>500000){toast('Choose a document below 500 KB.');return;}
    try {const data=await asBase64(selected);const result=await api('document',{method:'POST',body:JSON.stringify({filename:selected.name,content_base64:data})});$('#translate-prompt').value=result.text;toast('Document loaded. Choose the target language and translate.');}catch(error){toast(error.message);}finally{event.target.value='';}
  }
  function asBase64(blob) {return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the selected file.'));reader.readAsDataURL(blob);});}
  async function readImage(event) {
    const selected=event.target.files[0];if(!selected)return;
    if(selected.size>12000000){toast('Choose an image below 12 MB.');return;}
    try {
      const bitmap=await createImageBitmap(selected), scale=Math.min(1,1024/Math.max(bitmap.width,bitmap.height));
      const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.82));uploads.vision=await asBase64(blob);$('#vision-sample').selectedIndex=2;toast('Image prepared locally. Press Analyze image to run Qwen.');
    }catch(error){toast('This image could not be read. Choose a PNG, JPEG or WebP.');}
  }
  async function switchMode(free) {
    const button=$('#stage-mode');button.disabled=true;
    try {await api('mode',{method:'POST',body:JSON.stringify({mode:free?'free':'presenter'})});if(free)await poll();else location.href='/stage';}catch(error){toast(error.message);}finally{button.disabled=false;}
  }
  $('#stage-mode').addEventListener('click',()=>switchMode(false));
  $('#fullscreen').addEventListener('click',()=>{(document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()).catch(()=>toast('Full screen is unavailable in this browser.'));});
  async function poll() {
    if(polling)return;polling=true;
    try {
      const first=!state;state=await api('state');if(first)initialize();
      const ready=['lead','text','image','tts'].filter(key=>state.health[key]?.ready).length;
      $('#home-resident').textContent=ready;
      const total=Number(state.telemetry.total),available=Number(state.telemetry.available);
      $('#home-memory').textContent=total>0?`${((total-available)/2**30).toFixed(1)} / ${(total/2**30).toFixed(1)} GiB`:'Unavailable';
      $('#home-ready').textContent=`${ready} / 4 ready`;$('#connection').textContent=`${ready===4?'●':'○'} ${state.mode==='free'?'Free Mode':'Presenter Mode'} · ${ready}/4 models ready`;
      const gpu=state.telemetry.gpu;$('#hardware').textContent=[gpu?.utilization!=null?`GPU ${gpu.utilization}%`:null,gpu?.power!=null?`${gpu.power.toFixed(0)} W`:null,gpu?.temperature!=null?`${gpu.temperature}°C`:null].filter(Boolean).join(' · ');
      $('#usage').textContent=`${(state.totals.output_tokens||0).toLocaleString()} output tokens · ${state.totals.images||0} renders · ${state.totals.pages||0} translated pages`;
      $('#queue-count').textContent=state.jobs.filter(active).length;
      $('#mode-banner').hidden=state.mode==='free';
      if(state.mode!=='free') {$('#mode-banner').replaceChildren(document.createTextNode(state.warming?'Presenter warm-up is running. Free Mode becomes available when it finishes.':'Presenter Mode owns the models. Reset the show to its Ready screen before entering Free Mode.'));const enter=document.createElement('button');enter.textContent='Enter Free Mode';enter.disabled=state.warming;enter.addEventListener('click',()=>switchMode(true));$('#mode-banner').append(enter);}
      for(const item of state.catalog) {
        if(!(item.id in latest))latest[item.id]=state.jobs.find(row=>row.demo===item.id)?.id;
        const job=state.jobs.find(row=>row.id===latest[item.id]);if(job)renderOutput(job);
        $(`#form-${item.id} button[type=submit]`).disabled=state.mode!=='free'||state.jobs.some(row=>row.demo===item.id&&active(row));
      }
      if(view==='jobs')renderJobs();if(view==='models')renderModels();
      $('#open-rush').disabled=state.mode!=='free'||state.jobs.some(active);
    }catch(error){$('#connection').textContent='○ Nano connection unavailable';if(!state)toast(error.message);}finally{polling=false;}
  }
  poll();setInterval(()=>{if(!document.hidden)poll();},1300);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
})();
