/* Coroner UI. No framework, no build step — one file, hash routing. */
const $ = (s, r = document) => r.querySelector(s);
const view = $('#view');
const get = (p) => fetch(p).then(r => r.ok ? r.json() : Promise.reject(new Error(r.status)));

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x) => `${Math.round((x || 0) * 100)}%`;

let TAX = {}, STAGES = [];

/* --- graveyard --------------------------------------------------------- */
async function graveyard() {
  const [cases, fleet] = await Promise.all([get('/api/cases'), get('/api/fleet').catch(() => null)]);
  const a = fleet?.aggregate;

  const groups = {};
  for (const c of cases) (groups[c.cause] ||= []).push(c);
  const order = Object.keys(groups).sort((x, y) => groups[y].length - groups[x].length);

  view.innerHTML = `
    ${a ? `<div class="slab">
      <h2>${esc(fleet.headline || '')}</h2>
      <div class="figures">
        <div class="fig warn"><strong>${a.runs}</strong><span>runs autopsied</span></div>
        <div class="fig bad"><strong>${pct(a.silent_rate)}</strong><span>died without a word</span></div>
        <div class="fig bad"><strong>${a.steps_abandoned}</strong><span>steps abandoned</span></div>
        <div class="fig"><strong>${pct(a.mean_progress)}</strong><span>work banked before death</span></div>
        <div class="fig good"><strong>${a.revivable}</strong><span>still revivable</span></div>
      </div>
    </div>` : ''}
    ${order.map(k => {
      const t = TAX[k] || {};
      return `<section class="cause-group">
        <div class="cause-head">
          <div class="line">
            <h3>${esc(t.label || k)}</h3><code>${esc(k)}</code>
            <span class="n">${groups[k].length}</span>
          </div>
          <p>${esc(t.meaning || '')}</p>
        </div>
        <div class="tags">${groups[k].map(toe).join('')}</div>
      </section>`;
    }).join('')}`;
}

const toe = (c) => `
  <a class="toe" href="#/case/${encodeURIComponent(c.run_id)}">
    <div class="t">${esc(c.title || c.run_id)}</div>
    <div class="meta">
      <span>${pct(c.progress)}</span>
      <span class="bar"><i style="width:${pct(c.progress)}"></i></span>
      ${c.overruled ? '<span class="pill overruled">OVERRULED</span>' : ''}
      ${c.silent ? '<span class="pill silent">SILENT</span>' : ''}
      ${c.revivable ? '<span class="pill revivable">REVIVABLE</span>' : ''}
    </div>
  </a>`;

/* --- one case file ----------------------------------------------------- */
async function caseFile(id) {
  const c = await get(`/api/case/${encodeURIComponent(id)}`);
  const cert = c.certificate || {}, ev = c.evidence || {}, plan = c.resume_plan || {};
  const t = TAX[cert.cause] || {};

  view.innerHTML = `
    <a class="back" href="#/graveyard">&larr; graveyard</a>
    <div class="cert">
      <div class="who">Certificate of death · run ${esc((c.run_id || '').slice(0, 8))}</div>
      <h2>${esc(c.title || 'untitled run')}</h2>
      <div class="cause">${esc(cert.cause || '?')} — ${esc(t.label || '')}
        · confidence ${cert.confidence ?? '?'}</div>
      <p class="say">${esc(cert.plain_english || '')}</p>
      <div class="rows">
        <div class="row"><b>Recorded reason</b><div>${esc(ev.stop_reason || '(none recorded)')}</div></div>
        <div class="row"><b>Rules said</b><div>${esc(c.prior_cause)}${
          cert.cause && cert.cause !== c.prior_cause
            ? ` &nbsp;<span class="pill overruled">agents overruled it → ${esc(cert.cause)}</span>` : ''}</div></div>
        <div class="row"><b>Died on step</b><div>${esc(cert.killing_step || ev.killing_step || '—')}</div></div>
        <div class="row"><b>Work thrown away</b><div>${esc(cert.wasted_effort || '—')}</div></div>
        <div class="row"><b>Fix it by</b><div>${esc(cert.prevention || '—')}</div></div>
      </div>
    </div>

    <h3 class="sec">What the trace showed, before anyone interpreted it</h3>
    <ul class="sig">${(ev.signals || []).map(s => `<li>${esc(s)}</li>`).join('')}</ul>

    <h3 class="sec">Hypotheses at triage</h3>
    ${(c.hypotheses || []).map(h => `<div class="hyp">
      <span class="c">${esc(h.cause)}</span><span class="conf">${h.confidence}</span>
      <span class="why">${esc(h.reasoning)}</span></div>`).join('')}

    <h3 class="sec">Three investigators, each told to destroy them</h3>
    <div class="lenses">${Object.entries(c.verdicts || {}).map(([lens, vs]) => {
      const s = STAGES.find(x => x.agent === `investigator_${lens}`) || {};
      return `<div class="lens">
        <h4>${esc(s.label || lens)}</h4>
        <p class="does">${esc(s.does || '')}</p>
        ${vs.map(v => `<div class="verdict">
          <div class="h"><span class="${v.survives ? 's' : 'k'}">${v.survives ? 'SURVIVED' : 'REFUTED'}</span>
          <span>${esc(v.cause)}</span></div>
          <p>${esc(v.argument)}</p></div>`).join('')}
      </div>`;
    }).join('')}</div>

    <h3 class="sec">Revival kit</h3>
    <div class="kit ${plan.revivable ? '' : 'no'}">
      ${plan.revivable ? `
        <div class="rows" style="margin-top:0">
          <div class="row"><b>Restart at</b><div>${esc(plan.resume_at || '—')}</div></div>
          <div class="row"><b>Do not redo</b><div>${(plan.skip || []).length} step(s) already banked</div></div>
          <div class="row"><b>Proceed under</b><div>${esc(plan.unblock || '—')}</div></div>
          <div class="row"><b>Still worth keeping</b><div>${esc(plan.salvage || '—')}</div></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px">
          <b style="font-size:12px;color:var(--dimmer);font-family:var(--mono);letter-spacing:.6px">HAND THIS TO THE ORCHESTRATOR</b>
          <button class="copy" id="cp">copy</button>
        </div>
        <pre class="prompt" id="rp">${esc(plan.restart_prompt || '')}</pre>`
      : `<p style="margin:0;color:var(--dim)">Not revivable. ${esc(plan.unblock || '')}</p>
         <p style="margin:10px 0 0;color:var(--dim)"><b style="color:var(--ink)">Salvage:</b> ${esc(plan.salvage || '—')}</p>`}
    </div>`;

  $('#cp')?.addEventListener('click', async (e) => {
    await navigator.clipboard.writeText($('#rp').textContent);
    e.target.textContent = 'copied';
    setTimeout(() => (e.target.textContent = 'copy'), 1400);
  });
}

/* --- fleet report ------------------------------------------------------ */
async function fleetReport() {
  const f = await get('/api/fleet'), a = f.aggregate;
  view.innerHTML = `
    <div class="slab">
      <h2>${esc(f.headline || '')}</h2>
      <p>Every certificate proposed a fix for its own run. Collapsed and ranked by how many
         deaths each one would actually have prevented.</p>
      <div class="figures">
        <div class="fig warn"><strong>${a.runs}</strong><span>runs</span></div>
        <div class="fig"><strong>${a.steps_planned}</strong><span>steps planned</span></div>
        <div class="fig good"><strong>${a.steps_banked}</strong><span>banked</span></div>
        <div class="fig bad"><strong>${a.steps_abandoned}</strong><span>abandoned</span></div>
      </div>
    </div>
    ${(f.prescriptions || []).map(p => `<div class="rx">
      <div class="count"><strong>${p.deaths_prevented}</strong><span>runs saved</span></div>
      <div>
        <h4>${esc(p.change)}</h4>
        <p>${esc(p.rationale)}</p>
        <div class="ids">effort: ${esc(p.effort)} · ${(p.run_ids || []).join(' ')}</div>
      </div>
    </div>`).join('')}`;
}

/* --- live autopsy ------------------------------------------------------ */
function autopsyView() {
  view.innerHTML = `
    <div class="slab"><h2>Autopsy a run</h2>
      <p>Drop the JSON a dead run left behind. Six agents examine it: one triages, three try to
         destroy the theories, one certifies, one writes the restart. Nothing that identifies your
         project reaches the model — paths, URLs and keys are replaced before the first call.</p></div>
    <div class="drop" id="drop">
      Drop a trace file here, or paste it below.
      <textarea id="ta" placeholder='{ "runId": "...", "status": "held", "steps": [...] }'></textarea>
      <div class="actions">
        <button class="go" id="run">Begin autopsy</button>
        <button class="go ghost" id="sample">Load a real dead run</button>
      </div>
    </div>
    <div class="pipe" id="pipe"></div>
    <div id="out"></div>`;

  drawPipe();
  const ta = $('#ta'), drop = $('#drop');
  ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('hot'); }));
  ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, () => drop.classList.remove('hot')));
  drop.addEventListener('drop', async ev => {
    ev.preventDefault();
    const f = ev.dataTransfer.files[0];
    if (f) ta.value = await f.text();
  });
  $('#sample').addEventListener('click', async () => {
    ta.value = JSON.stringify(await get('/api/sample'), null, 2);
  });
  $('#run').addEventListener('click', () => start(ta.value));
}

function drawPipe(state = {}) {
  const node = (s) => `<div class="node ${state[s.agent] || ''}"><span class="dot"></span>
    <div><b>${esc(s.label)}</b><small>${esc(s.does)}</small></div></div>`;
  const mid = STAGES.filter(s => s.agent.startsWith('investigator_'));
  const rest = STAGES.filter(s => !s.agent.startsWith('investigator_'));
  $('#pipe').innerHTML =
    node(rest[0]) +
    `<div class="parallel">${mid.map(node).join('')}</div>` +
    rest.slice(1).map(node).join('');
}

async function start(text) {
  let body;
  try { body = JSON.parse(text); }
  catch { $('#out').innerHTML = `<p class="err">That is not valid JSON.</p>`; return; }

  const btn = $('#run'); btn.disabled = true; btn.textContent = 'examining…';
  const state = {}; STAGES.forEach(s => state[s.agent] = '');
  state[STAGES[0].agent] = 'running'; drawPipe(state);
  $('#out').innerHTML = '';

  const res = await fetch('/api/autopsy', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    $('#out').innerHTML = `<p class="err">${esc(await res.text())}</p>`;
    btn.disabled = false; btn.textContent = 'Begin autopsy'; return;
  }

  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n\n'); buf = parts.pop();
    for (const p of parts) {
      if (!p.startsWith('data: ')) continue;
      const e = JSON.parse(p.slice(6));
      if (e.error) { $('#out').innerHTML = `<p class="err">${esc(e.error)}</p>`; continue; }
      if (e.agent) {
        state[e.agent] = 'done';
        const i = STAGES.findIndex(s => s.agent === e.agent);
        for (let k = 0; k <= i; k++) state[STAGES[k].agent] ||= 'done';
        const next = STAGES[i + 1]; if (next && !state[next.agent]) state[next.agent] = 'running';
        drawPipe(state);
      }
      if (e.done) {
        STAGES.forEach(s => state[s.agent] = 'done'); drawPipe(state);
        location.hash = `#/case/${encodeURIComponent(e.report.run_id)}`;
      }
    }
  }
  btn.disabled = false; btn.textContent = 'Begin autopsy';
}

/* --- routing ----------------------------------------------------------- */
async function route() {
  const h = location.hash.slice(2) || 'graveyard';
  const [page, arg] = [h.split('/')[0], decodeURIComponent(h.split('/').slice(1).join('/'))];
  document.querySelectorAll('nav a').forEach(a =>
    a.classList.toggle('on', a.dataset.nav === (page === 'case' ? 'graveyard' : page)));
  view.innerHTML = '<p class="loading">…</p>';
  try {
    if (page === 'case') await caseFile(arg);
    else if (page === 'fleet') await fleetReport();
    else if (page === 'autopsy') autopsyView();
    else await graveyard();
  } catch (e) {
    view.innerHTML = `<p class="err">${esc(e.message || e)}</p>`;
  }
}

addEventListener('hashchange', route);
(async () => {
  [TAX, STAGES] = await Promise.all([get('/api/taxonomy'), get('/api/stages')]);
  get('/api/health').then(h => $('#health').textContent = `model: ${h.model}`).catch(() => {});
  route();
})();
