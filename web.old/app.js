/* Coroner UI. No framework, no build step — hash routing.
   app.js is the machinery; copy.js is the prose. Everything that came out of a
   trace or a model goes through esc() before it reaches the page. */
const $ = (s, r = document) => r.querySelector(s);
const view = $('#view');
const get = (p) => fetch(p).then(r => r.ok ? r.json() : Promise.reject(new Error(`${p} → ${r.status}`)));

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/* Backtick spans, for our own copy in copy.js only. Escapes first, so it is
   safe either way — but never point it at a trace or at model output. */
const mark = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>');
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const secs = (ms) => `${(ms / 1000).toFixed(1)}s`;
/* A missing field renders as an em dash, never as "undefined" or "NaN". */
const or = (v, fallback = '—') => (v === undefined || v === null || v === '' ||
  (typeof v === 'number' && !isFinite(v))) ? fallback : v;

let TAX = {}, STAGES = [], LIVE = null;

const ago = (t) => {
  if (!t) return 'never';
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
};

/* What the investigators did to the cause the run recorded for itself.
   Counted from the verdicts, never asserted. */
function standing(c) {
  const prior = c.prior_cause, cause = (c.certificate || {}).cause;
  if (!prior || !cause) return null;
  const lenses = Object.values(c.verdicts || {});
  return {
    prior, cause, overturned: prior !== cause, lenses: lenses.length,
    killed: lenses.filter(vs => (vs || []).some(v => v.cause === prior && !v.survives)).length,
    held: lenses.filter(vs => (vs || []).some(v => v.cause === cause && v.survives)).length,
  };
}

const overruledBanner = (o) => !o?.overturned ? '' : `
  <div class="overrule">
    <div class="tagline">THE RUN'S OWN CAUSE OF DEATH WAS OVERTURNED</div>
    <p>The run recorded that it died of <code>${esc(o.prior)}</code>.
       ${esc(o.killed)} of ${esc(o.lenses)} investigators refuted that, and
       ${esc(o.held)} of ${esc(o.lenses)} found <code>${esc(o.cause)}</code> survived their
       attempt to destroy it. The certificate follows the investigators, not the run.</p>
    <p class="corpus">8 of the 39 autopsied runs came out this way. It is the clearest evidence
       that the adversarial stage does work rather than agreeing with the first plausible story.</p>
  </div>`;

/* ======================= the front door ================================= */
async function home() {
  view.innerHTML = `
    <section class="hero">
      <h2>Six agents cut open one dead agent run and tell you what killed it.</h2>
      <p class="lede">${mark(PITCH.problem)}</p>
      <p>${mark(PITCH.what)}</p>
      <p class="unprompted"><span class="dot"></span>${mark(PITCH.unprompted)}</p>
    </section>

    <section class="launch">
      <h3>Pick a dead run. It is autopsied live, in about thirty seconds.</h3>
      <div class="samples" id="samples"><span class="loading">loading the samples…</span></div>
      <details class="own">
        <summary>…or post a trace of your own</summary>
        <textarea id="ta" placeholder='{ "runId": "...", "status": "held", "steps": [...] }'></textarea>
        <div class="ownrow">
          <button class="go ghost" id="run">Autopsy this trace</button>
          <p class="privacy">Before the first model call, Coroner pattern-masks POSIX, Windows and
            UNC paths; HTTP(S) and schemeless domain/path URLs; email and IPv4 addresses; JWTs, PEM
            private-key blocks, database connection strings, AWS access-key IDs and labelled AWS
            secret keys, bearer tokens, common prefixed tokens and long hexadecimal keys. Ordinary
            prose — including names, company names, business facts, phone numbers and unrecognized
            secret formats — still goes to Vertex AI unchanged; remove it before uploading.</p>
        </div>
      </details>
    </section>

    ${terminalShell()}

    <section class="evidence" id="evidence"></section>`;

  buildRows();
  $('#run').addEventListener('click', () => start(parseBox()));

  get('/api/samples').then(list => {
    $('#samples').innerHTML = list.map((s, i) => `
      <button class="sample" data-run="${esc(s.run_id)}">
        <span class="n">${i + 1}</span>
        <span class="lab">${esc(s.label)}</span>
        <span class="cta">autopsy it →</span>
      </button>`).join('');
    $('#samples').querySelectorAll('.sample').forEach(b =>
      b.addEventListener('click', () => runSample(b.dataset.run, b)));
  }).catch(e => { $('#samples').innerHTML = `<p class="err">${esc(e.message)}</p>`; });

  Promise.all([get('/api/fleet').catch(() => null), get('/api/cases').catch(() => null),
               get('/api/sweep').catch(() => null)]).then(([f, cases, sw]) => {
    const a = f?.aggregate;
    if (!a && !cases) return;
    const over = (cases || []).filter(c => c.overruled).length;
    $('#evidence').innerHTML = `
      <h3 class="sec">What ${esc((cases || []).length)} autopsies of my own dead runs found</h3>
      <div class="figures">
        <div class="fig bad"><strong>${esc(pct(a?.silent_rate))}</strong>
          <span>of ${esc(or(a?.runs, '?'))} runs stopped without reporting a failure</span></div>
        <div class="fig bad"><strong>${esc(or(a?.steps_abandoned, '?'))}</strong>
          <span>planned steps abandoned</span></div>
        <div class="fig cold"><strong>${esc(over)} of ${esc((cases || []).length)}</strong>
          <span>had the run's own recorded cause overturned</span></div>
      </div>
      <p class="more"><a href="#/graveyard">All ${esc((cases || []).length)} case files →</a>
        <a href="#/fleet">The six fixes they add up to →</a></p>
      ${sw ? `<p class="watchline"><span class="dot"></span>Sweeper: watching ${esc(or(sw.watched, 0))}
        run${sw.watched === 1 ? '' : 's'} · last swept ${esc(ago(sw.at))} ·
        ${esc((sw.autopsied || []).length)} autopsied unprompted</p>` : ''}`;
  });
}

function parseBox() {
  const raw = $('#ta')?.value || '';
  try { return JSON.parse(raw); }
  catch { termFail('That is not valid JSON.'); return null; }
}

async function runSample(runId, btn) {
  btn.disabled = true;
  try { start(await get(`/api/samples/${encodeURIComponent(runId)}`)); }
  catch (e) { termFail(e.message); }
  btn.disabled = false;
}

/* ======================= the live autopsy =============================== */
/* One terminal. Idle it is the map of the pipeline; running it is the log.
   Nothing in it moves that is not a real event off the wire — the only thing
   that ticks on its own is a clock, and a clock is a measurement. */
function terminalShell() {
  return `<section class="term" id="term">
    <div class="termbar">
      <span class="path">coroner://autopsy</span>
      <span class="state" id="tstate">idle — nothing running</span>
      <span class="clock" id="tclock"></span>
    </div>
    <div class="trows" id="trows"></div>
    <div id="tpayoff"></div>
  </section>`;
}

const ROW = new Map();
let ticker = null, t0 = 0;

function buildRows() {
  const rows = $('#trows');
  if (!rows) return;
  const cell = (s) => `<div class="srow" data-stage="${esc(s.agent)}">
      <div class="sline"><span class="glyph">·</span><b>${esc(s.label)}</b>
        <span class="does">${esc(s.does)}</span><span class="t"></span></div>
      <div class="res"></div>
    </div>`;
  const lens = STAGES.filter(s => s.agent.startsWith('investigator_'));
  const rest = STAGES.filter(s => !s.agent.startsWith('investigator_'));
  rows.innerHTML =
    cell(rest[0]) +
    `<div class="wave"><div class="whead">all three start at the same instant · each is told to
       <b>destroy</b> the hypotheses, not confirm them</div>${lens.map(cell).join('')}</div>` +
    rest.slice(1).map(cell).join('');
  ROW.clear();
  rows.querySelectorAll('.srow').forEach(el => ROW.set(el.dataset.stage, el));
}

function setRow(stage, state, startedAt) {
  const el = ROW.get(stage);
  if (!el) return;
  el.className = `srow ${state}`;
  el.dataset.at = startedAt ?? '';
  $('.glyph', el).textContent = { running: '▸', done: '✔', failed: '✕' }[state] || '·';
}

function tick() {
  const now = performance.now();
  const clock = $('#tclock');
  if (clock) clock.textContent = secs(now - t0);
  for (const el of ROW.values()) {
    if (el.classList.contains('running')) $('.t', el).textContent = secs(now - Number(el.dataset.at));
  }
}

function stopTicker() { clearInterval(ticker); ticker = null; }

function termFail(msg) {
  const p = $('#tpayoff');
  if (p) p.innerHTML = `<p class="err">${esc(msg)}</p>`;
  stopTicker();
  const st = $('#tstate'); if (st) st.textContent = 'stopped';
  for (const el of ROW.values()) if (el.classList.contains('running')) setRow(el.dataset.stage, 'failed');
}

async function start(body) {
  if (!body) return;
  ROW.forEach((el, stage) => { setRow(stage, ''); $('.t', el).textContent = ''; $('.res', el).innerHTML = ''; });
  $('#tpayoff').innerHTML = '';
  $('#term').classList.add('live');
  $('#tstate').textContent = 'posting the trace…';
  document.querySelectorAll('.sample').forEach(b => b.disabled = true);
  t0 = performance.now();
  stopTicker();
  ticker = setInterval(tick, 100);
  $('#term').scrollIntoView({ behavior: 'smooth', block: 'start' });

  let res;
  try {
    res = await fetch('/api/autopsy/stream', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    });
  } catch (e) { return finish(`Could not reach the service: ${e.message}`); }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON; keep the status */ }
    return finish(detail);
  }

  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        let name = 'message', data = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) name = line.slice(6).trim();
          else if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        if (data) onEvent(name, JSON.parse(data));
      }
    }
  } catch (e) { return finish(`The stream broke: ${e.message}`); }
  if (ticker) finish('The stream ended before the autopsy did.');
}

function onEvent(name, d) {
  if (!ROW.size) return;                       // the viewer navigated away mid-stream
  if (name === 'error') return finish(d.detail || 'the autopsy failed');
  if (name === 'done') return finish(null, d.case);
  if (name !== 'stage') return;

  if (d.state === 'start') {
    setRow(d.stage, 'running', performance.now());
    const running = [...ROW.values()].filter(el => el.classList.contains('running'));
    $('#tstate').textContent = running.length > 1
      ? `${running.length} agents running at once` : `${d.label} is running`;
    return;
  }
  const el = ROW.get(d.stage);
  if (!el) return;
  $('.t', el).textContent = secs(performance.now() - Number(el.dataset.at));
  setRow(d.stage, 'done', el.dataset.at);
  $('.res', el).innerHTML = stageResult(d.stage, d.result);
  const running = [...ROW.values()].filter(x => x.classList.contains('running'));
  $('#tstate').textContent = running.length
    ? (running.length > 1 ? `${running.length} agents running at once` : 'one agent running')
    : 'handing off…';
}

function finish(errorMsg, done) {
  stopTicker();
  document.querySelectorAll('.sample').forEach(b => b.disabled = false);
  if (errorMsg) return termFail(errorMsg);
  LIVE = done;
  const el = $('#tstate'); if (el) el.textContent = 'complete';
  const box = $('#tpayoff');
  if (!box) return;
  const o = standing(done || {});
  box.innerHTML = `
    ${overruledBanner(o)}
    <div class="closed">
      <div>
        <b>${esc(or(done?.title, 'this run'))}</b> — cause of death
        <code>${esc(or((done?.certificate || {}).cause, 'UNDETERMINED'))}</code>,
        confidence ${esc(or((done?.certificate || {}).confidence))}${o && !o.overturned ?
        `. It survived ${esc(o.held)} of ${esc(o.lenses)} investigators and matches the cause the
         run recorded for itself.` : '.'}
      </div>
      <a class="go" href="#/case/live">Read the death certificate →</a>
    </div>
    <p class="kept">Nothing you post here is stored. This case was streamed back to you and
      forgotten — it is not in the graveyard and nobody else can see it.</p>`;
}

/* Every result line is the same four cells — verdict, cause, confidence, prose —
   so five different shapes of model output land in one column grid. */
const rline = (tag, cls, cause, conf, why) => `<div class="rline">
  <span class="${cls}">${esc(tag)}</span><code class="cause">${esc(cause)}</code>
  <span class="conf">${esc(conf)}</span><span class="why">${esc(why)}</span></div>`;

function stageResult(stage, r) {
  if (!r) return '';
  const wrap = (rows, extra = '') => `<div class="rlist">${rows.join('')}${extra}</div>`;

  if (stage === 'triage')
    return wrap((r.hypotheses || []).map(h => rline('', '', h.cause, or(h.confidence, ''), h.reasoning)));

  if (stage.startsWith('investigator_'))
    return wrap((r.verdicts || []).map(v =>
      rline(v.survives ? 'SURVIVED' : 'REFUTED', v.survives ? 's' : 'k', v.cause, '', v.argument)));

  if (stage === 'certify') return wrap([
    rline('', '', or(r.cause, ''), or(r.confidence, ''), or(r.plain_english, '')),
    rline('DIED ON', 'k2', '', '', or(r.killing_step)),
    rline('FIX', 'k2', '', '', or(r.prevention)),
  ]);

  if (stage === 'revive') return wrap(
    [rline(r.revivable ? 'REVIVABLE' : 'NOT REVIVABLE', r.revivable ? 's' : 'k', '', '', or(r.unblock))],
    r.restart_prompt ? `<pre class="prompt">${esc(r.restart_prompt)}</pre>` : '');

  return '';
}

/* ======================= the graveyard ================================== */
async function graveyard() {
  const [cases, fleet] = await Promise.all([get('/api/cases'), get('/api/fleet').catch(() => null)]);
  const a = fleet?.aggregate;
  const groups = Object.create(null);
  for (const c of cases) (groups[String(c.cause ?? 'UNDETERMINED')] ||= []).push(c);
  const order = Object.keys(groups).sort((x, y) => groups[y].length - groups[x].length);

  view.innerHTML = `
    ${a ? `<div class="slab"><h2>${esc(fleet.headline || '')}</h2>
      <div class="figures">
        <div class="fig bad"><strong>${esc(pct(a.silent_rate))}</strong>
          <span>of ${esc(or(a.runs, '?'))} runs stopped without reporting a failure</span></div>
        <div class="fig bad"><strong>${esc(or(a.steps_abandoned, '?'))}</strong>
          <span>planned steps abandoned</span></div>
        <div class="fig cold"><strong>${esc(cases.filter(c => c.overruled).length)} of ${esc(cases.length)}</strong>
          <span>had the run's own recorded cause overturned</span></div>
      </div></div>` : ''}
    ${order.map(k => `<section class="cause-group">
        <div class="cause-head"><h3>${esc((TAX[k] || {}).label || k)}</h3>
          <code>${esc(k)}</code><span class="n">${esc(groups[k].length)}</span></div>
        <div class="tags">${groups[k].map(toe).join('')}</div>
      </section>`).join('')}`;
}

const toe = (c) => `
  <a class="toe" href="#/case/${esc(encodeURIComponent(c.run_id))}">
    <div class="t">${esc(or(c.title, c.run_id))}
      <span class="rid">${esc(String(c.run_id || '').slice(0, 8))}</span></div>
    <div class="meta">
      <span>${esc(pct(c.progress))}</span>
      <span class="bar"><i style="width:${esc(pct(c.progress))}"></i></span>
      ${c.overruled ? '<span class="pill overruled">OVERRULED</span>' : ''}
      ${c.silent ? '<span class="pill silent">SILENT</span>' : ''}
      ${c.revivable ? '<span class="pill revivable">REVIVABLE</span>' : ''}
    </div>
  </a>`;

/* ======================= one case file ================================== */
async function caseFile(id) {
  /* 'live' is an autopsy this visitor just ran. It was never stored, so it is
     rendered from what the stream handed back. */
  if (id === 'live' && !LIVE) {
    /* Reloading #/case/live loses it: a visitor's autopsy is streamed back and
       never stored, so there is nothing on the server to fetch. */
    view.innerHTML = `<p class="note">That autopsy was streamed to you and not stored, so a reload
      cannot get it back. <a href="#/">Run another one →</a></p>`;
    return;
  }
  const c = id === 'live' ? LIVE : await get(`/api/case/${encodeURIComponent(id)}`);
  const cert = c.certificate || {}, ev = c.evidence || {}, plan = c.resume_plan || {};
  const t = TAX[String(cert.cause ?? '')] || {};

  view.innerHTML = `
    <a class="back" href="#/${id === 'live' ? '' : 'graveyard'}">&larr; ${
      id === 'live' ? 'new autopsy' : 'graveyard'}</a>
    ${id === 'live' ? '<p class="note">You ran this one. It was streamed back to you and not stored — '
      + 'it is not in the graveyard and nobody else can see it.</p>' : ''}
    <div class="cert">
      <div class="who">Certificate of death · run ${esc(String(c.run_id || '').slice(0, 8))}</div>
      <h2>${esc(or(c.title, 'untitled run'))}</h2>
      <div class="cause">${esc(or(cert.cause, '?'))} — ${esc(t.label || '')}
        · confidence ${esc(or(cert.confidence, '?'))}</div>
      <p class="say">${esc(cert.plain_english || '')}</p>
      ${overruledBanner(standing(c))}
      <div class="rows">
        <div class="row"><b>Recorded reason</b><div>${esc(or(ev.stop_reason, '(none recorded)'))}</div></div>
        <div class="row"><b>Rules said</b><div>${esc(or(c.prior_cause))}${
          cert.cause && cert.cause !== c.prior_cause
            ? ` &nbsp;<span class="pill overruled">agents overruled it → ${esc(cert.cause)}</span>` : ''}</div></div>
        <div class="row"><b>Died on step</b><div>${esc(or(cert.killing_step || ev.killing_step))}</div></div>
        <div class="row"><b>Work thrown away</b><div>${esc(or(cert.wasted_effort))}</div></div>
        <div class="row"><b>Fix it by</b><div>${esc(or(cert.prevention))}</div></div>
      </div>
    </div>

    <h3 class="sec">What the trace showed, before anyone interpreted it</h3>
    <ul class="sig">${(ev.signals || []).map(s => `<li>${esc(s)}</li>`).join('')}</ul>

    <h3 class="sec">Hypotheses at triage</h3>
    ${(c.hypotheses || []).map(h => `<div class="hyp">
      <span class="c">${esc(h.cause)}</span><span class="conf">${esc(or(h.confidence))}</span>
      <span class="why">${esc(h.reasoning)}</span></div>`).join('')}

    <h3 class="sec">Three investigators, each told to destroy them</h3>
    <div class="lenses">${Object.entries(c.verdicts || {}).map(([lens, vs]) => {
      const s = STAGES.find(x => x.agent === `investigator_${lens}`) || {};
      return `<div class="lens">
        <h4>${esc(s.label || lens)}</h4>
        <p class="does">${esc(s.does || '')}</p>
        ${(vs || []).map(v => `<div class="verdict">
          <div class="h"><span class="${v.survives ? 's' : 'k'}">${v.survives ? 'SURVIVED' : 'REFUTED'}</span>
          <span>${esc(v.cause)}</span></div>
          <p>${esc(v.argument)}</p></div>`).join('')}
      </div>`;
    }).join('')}</div>

    <h3 class="sec">Revival kit</h3>
    <div class="kit ${plan.revivable ? '' : 'no'}">
      ${plan.revivable ? `
        <div class="rows" style="margin-top:0">
          <div class="row"><b>Restart at</b><div>${esc(or(plan.resume_at))}</div></div>
          <div class="row"><b>Do not redo</b><div>${esc((plan.skip || []).length)} step(s) already banked</div></div>
          <div class="row"><b>Proceed under</b><div>${esc(or(plan.unblock))}</div></div>
          <div class="row"><b>Still worth keeping</b><div>${esc(or(plan.salvage))}</div></div>
        </div>
        <div class="kithead">
          <b>HAND THIS TO THE ORCHESTRATOR</b>
          <span>
            <button class="copy" id="cp">copy</button>
            ${id === 'live' ? '' : '<button class="copy send" id="send">hand it back &rarr;</button>'}
          </span>
        </div>
        <pre class="prompt" id="rp">${esc(plan.restart_prompt || '')}</pre>
        <p class="sent" id="sent"></p>`
      : `<p style="margin:0;color:var(--dim)">Not revivable. ${esc(plan.unblock || '')}</p>
         <p style="margin:10px 0 0;color:var(--dim)"><b style="color:var(--ink)">Salvage:</b> ${esc(or(plan.salvage))}</p>`}
    </div>`;

  $('#send')?.addEventListener('click', async (e) => {
    e.target.disabled = true; e.target.textContent = 'handing back…';
    const out = $('#sent');
    try {
      const r = await fetch(`/api/case/${encodeURIComponent(id)}/resume`, { method: 'POST' });
      const d = await r.json();
      out.className = `sent ${d.delivered ? 'ok' : 'no'}`;
      out.textContent = d.delivered
        ? `Delivered — the orchestrator accepted it (HTTP ${d.status}). ${d.detail}`
        : `Not delivered: ${d.detail}`;
    } catch (err) {
      out.className = 'sent no';
      out.textContent = `Not delivered: ${err.message}`;
    }
    e.target.disabled = false; e.target.textContent = 'hand it back →';
  });

  $('#cp')?.addEventListener('click', async (e) => {
    await navigator.clipboard.writeText($('#rp').textContent);
    e.target.textContent = 'copied';
    setTimeout(() => (e.target.textContent = 'copy'), 1400);
  });
}

/* ======================= fleet report =================================== */
async function fleetReport() {
  const f = await get('/api/fleet'), a = f.aggregate || {};
  view.innerHTML = `
    <div class="slab">
      <h2>${esc(f.headline || '')}</h2>
      <p>Every certificate proposed a fix for its own run. The prescriber groups related proposals;
         Python validates the case IDs, counts them, and ranks the groups. The count is how many
         cases are in the group, not a measured counterfactual.</p>
    </div>
    ${(f.prescriptions || []).map(p => `<div class="rx">
      <div class="count"><strong>${esc(or(p.deaths_prevented, 0))}</strong><span>cases grouped</span></div>
      <div>
        <h4>${esc(p.change)}</h4>
        <p>${esc(p.rationale)}</p>
        <div class="ids">effort: ${esc(or(p.effort))} · ${(p.run_ids || []).map(esc).join(' ')}</div>
      </div>
    </div>`).join('')}`;
}

/* ======================= the six agents ================================= */
async function agentsView() {
  const agents = await get('/api/agents');
  view.innerHTML = `
    <div class="slab">
      <h2>The six prompts, as the server holds them</h2>
      <p>Each file below is read from <code>prompts/&lt;agent&gt;.md</code> at import and handed
         straight to Gemini. This page does not transcribe them: it renders the same
         <code>markdown</code> string that <a href="/api/agents">GET /api/agents</a> returns, which
         is the same object <code>app/autopsy.py</code> loaded into the agent. There is no second
         copy that could drift.</p>
    </div>
    ${agents.map((a, i) => `<section class="card">
      <div class="cardhead">
        <span class="ix">${i + 1}</span>
        <div>
          <h3>${esc(a.label)}</h3>
          <p>${esc(a.description)}</p>
        </div>
        <span class="modelchip">${esc(or(a.model, 'model?'))}</span>
      </div>
      <div class="filebar">prompts/${esc(a.id)}.md</div>
      <pre class="file">${esc(a.markdown)}</pre>
    </section>`).join('')}`;
}

/* ======================= the three categories =========================== */
function categoryView(key) {
  const c = CATEGORIES[key];
  if (!c) { view.innerHTML = `<p class="err">No such category.</p>`; return; }
  const VERDICT = { yes: 'MEETS', no: 'FAILS', partial: 'PARTIAL' };

  const block = (b) => {
    if (b.p) return `<p>${mark(b.p)}</p>`;
    if (b.ul) return `<ul class="plain">${b.ul.map(x => `<li>${mark(x)}</li>`).join('')}</ul>`;
    if (b.quote) return `<blockquote>${mark(b.quote).replace(/\n/g, '<br>')}
      <cite>${esc(b.from)}</cite></blockquote>`;
    if (b.table) return `<div class="rows">${b.table.map(([k, v]) =>
      `<div class="row"><b>${mark(k)}</b><div>${mark(v)}</div></div>`).join('')}</div>`;
    if (b.fleetFigures) return `<div class="figures" id="fleetfigs">
      <span class="loading">reading /api/fleet…</span></div>`;
    return '';
  };

  view.innerHTML = `
    <div class="slab ${c.entered ? 'entered' : 'notentered'}">
      <div class="who">${c.entered ? 'ENTERED IN THIS CATEGORY' : 'NOT ENTERED — HONEST NON-FIT'}</div>
      <h2>${esc(c.name)}</h2>
      <p>${mark(c.stance)}</p>
    </div>

    <h3 class="sec">What the rules say, verbatim</h3>
    ${c.quotes.map(q => `<blockquote>${mark(q.text)}<cite>${esc(q.from)}</cite></blockquote>`).join('')}
    <p class="src">Quoted from <a href="${RULES_URL}">${esc(RULES_URL)}</a>, read live 2026-08-21.
       Blockquotes are the sponsor's words, including their own capitalisation and typos. Everything
       outside a blockquote is ours.</p>

    <h3 class="sec">How this project measures up</h3>
    <p>${mark(c.lead)}</p>
    <div class="checks">${c.checks.map(k => `<div class="check ${esc(k.v)}">
      <span class="v">${esc(VERDICT[k.v] || '?')}</span>
      <div><b>${mark(k.need)}</b><p>${mark(k.note)}</p></div>
    </div>`).join('')}</div>

    ${c.sections.map(s => `<h3 class="sec">${esc(s.h)}</h3>
      <div class="prose ${s.weak ? 'weak' : ''}">${s.body.map(block).join('')}</div>`).join('')}`;

  if ($('#fleetfigs')) get('/api/fleet').then(f => {
    const a = f.aggregate || {};
    $('#fleetfigs').innerHTML = `
      <div class="fig bad"><strong>${esc(pct(a.silent_rate))}</strong>
        <span>of ${esc(or(a.runs, '?'))} runs stopped without reporting a failure</span></div>
      <div class="fig bad"><strong>${esc(or(a.steps_abandoned, '?'))}</strong>
        <span>planned steps abandoned, of ${esc(or(a.steps_planned, '?'))} planned
          and ${esc(or(a.steps_banked, '?'))} banked</span></div>
      <div class="fig good"><strong>${esc(or(a.revivable, '?'))}</strong>
        <span>still revivable</span></div>
      <div class="fig warn"><strong>${esc((f.prescriptions || []).length)}</strong>
        <span>ranked fixes they group into</span></div>`;
  }).catch(e => { $('#fleetfigs').innerHTML = `<p class="err">${esc(e.message)}</p>`; });
}

/* ======================= routing ======================================== */
const NAV = { '': 'home', autopsy: 'home', case: 'graveyard' };

async function route() {
  const h = location.hash.slice(2);
  const page = h.split('/')[0];
  const arg = decodeURIComponent(h.split('/').slice(1).join('/'));
  const on = page === 'rules' ? `rules/${arg}`
    : page === 'case' && arg === 'live' ? 'home'          // ran from the front door
    : (NAV[page] ?? page);
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === on));
  stopTicker();
  ROW.clear();
  view.innerHTML = '<p class="loading">…</p>';
  try {
    if (page === 'case') await caseFile(arg);
    else if (page === 'fleet') await fleetReport();
    else if (page === 'graveyard') await graveyard();
    else if (page === 'agents') await agentsView();
    else if (page === 'rules') categoryView(arg);
    else await home();
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
