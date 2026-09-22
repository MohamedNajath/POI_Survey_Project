'use strict';
/* ============ helpers ============ */
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const today = () => { const d = new Date(); return `${String(d.getDate()).padStart(2,'0')} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
const clone = o => JSON.parse(JSON.stringify(o));
const get = (o, path) => path.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
function set(o, path, v) { const ks = path.split('.'); const last = ks.pop(); const t = ks.reduce((a, k) => a[k], o); t[last] = v; }

/* ============ drafts in IndexedDB (photos included) ============ */
const idb = {
  db: null,
  open() { return new Promise((res, rej) => { const r = indexedDB.open('poi-survey', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('surveys', { keyPath: 'id' });
    r.onsuccess = () => { this.db = r.result; res(); }; r.onerror = () => rej(r.error); }); },
  tx(mode) { return this.db.transaction('surveys', mode).objectStore('surveys'); },
  put(s) { return new Promise((res, rej) => { const q = this.tx('readwrite').put(s); q.onsuccess = res; q.onerror = () => rej(q.error); }); },
  all() { return new Promise((res, rej) => { const q = this.tx('readonly').getAll(); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); }); },
  del(id) { return new Promise((res, rej) => { const q = this.tx('readwrite').delete(id); q.onsuccess = res; q.onerror = () => rej(q.error); }); },
};

/* ============ state ============ */
let CAT = {}, CAPS = {}, S = null, view = 'home', step = 0, saveTimer = null;
const STEPS = ['Site', 'Cameras', 'Setup', 'Review'];

const newCamera = () => ({ id: uid(), location_name: '', distance_m: '', target_area_m: '', viewing_angle: CAT.default_angle ?? (CAT.angles || [6])[0],
  camera_model: (CAT.camera_models || [])[0] || '', install_type: (CAT.install_types || ['Wall Mount'])[0], environment: (CAT.environments || ['Indoor'])[0], qty: 1, remarks: '',
  photos: { target: null, camera: null } });
/* Height / lens are never stored on the camera – they're derived live from distance + angle via the POI reference table (rules.js),
   and recomputed again on the server from the same table when the report is generated. */
const poiResult = c => POI.calc(CAT, c.distance_m, c.viewing_angle);
const newSurvey = () => ({ id: uid(), created: Date.now(), updated: Date.now(), report: { date: today(), revision: '0', number: '' },
  facility: { name: '', location: '', category: (CAT.categories || ['Other'])[0], type: 'as_build' },
  client: { name: '', mobile: '', designation: '', email: '' },
  contractor: { company: '', name: '', mobile: '', designation: '', email: '', certified_engineer: '', certified_technician: '' },
  config: { encoding: 'H.264', resolution: '2560x1440p', fps: 25, bitrate_kbps: 4096, wdr_day: 'ON', wdr_night: 'OFF', events_per_day: 1000 },
  vendor: 'DAHUA', author: '', cameras: [newCamera()], nvr: clone(CAT.nvr_defaults || []), floor_plan: null });

function scheduleSave() {
  if (!S) return; $('#saved') && ($('#saved').textContent = 'Saving…');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => { S.updated = Date.now(); try { await idb.put(S); $('#saved') && ($('#saved').textContent = 'Saved'); }
    catch (e) { $('#saved') && ($('#saved').textContent = 'Not saved – storage full?'); } }, 400);
}
const totalCams = () => S.cameras.reduce((n, c) => n + Math.max(1, parseInt(c.qty) || 1), 0);

function storageEstimate() {
  const n = totalCams(), events = Math.max(1, parseInt(S.config.events_per_day) || 1000), s = (parseInt(S.config.bitrate_kbps) || 4096) / 4096;
  const day = 21.2 * s * events / 1024, ev = day * 90 * n / 1024, img = (events / 1024) * 90 * n, total = ev + img / 1024;
  return { total: total.toFixed(2), extra: (total * 1.1).toFixed(2) };
}

function issues() {
  const out = [], f = S.facility;
  if (!f.name.trim()) out.push({ t: 'Add the facility name', s: 0 });
  if (!f.location.trim()) out.push({ t: 'Add the location', s: 0 });
  if (!S.cameras.length) out.push({ t: 'Add at least one camera', s: 1 });
  S.cameras.forEach((c, i) => {
    const n = `Camera ${String(i + 1).padStart(2, '0')}`;
    if (!c.location_name.trim() || !String(c.distance_m).trim() || !String(c.target_area_m).trim())
      out.push({ t: `${n}: fill in name, distance and target area`, s: 1 });
    else { const r = poiResult(c); if (!r.ok) out.push({ t: `${n}: ${r.error}`, s: 1 }); }
    if (!c.photos.target) out.push({ t: `${n}: add the target area photo`, s: 2 });
    if (!c.photos.camera) out.push({ t: `${n}: add the camera position photo`, s: 2 });
  });
  return out;
}
/* ============ rendering ============ */
const fld = (label, path, o = {}) => `<label class="f ${o.wide ? 'wide' : ''}"><span>${label}</span>
  ${o.area ? `<textarea data-bind="${path}" ${o.ph ? `placeholder="${o.ph}"` : ''}>${esc(get(S, path))}</textarea>`
  : `<input data-bind="${path}" value="${esc(get(S, path))}" ${o.type ? `type="${o.type}"` : ''} ${o.mode ? `inputmode="${o.mode}"` : ''} ${o.list ? `list="${o.list}"` : ''} ${o.ph ? `placeholder="${o.ph}"` : ''} autocomplete="off">`}</label>`;
const sel = (label, path, opts, o = {}) => `<label class="f ${o.wide ? 'wide' : ''}"><span>${label}</span><select data-bind="${path}">
  ${opts.map(x => `<option ${x === get(S, path) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>`;

function render() { view === 'home' ? renderHome() : renderSurvey(); }

async function renderHome() {
  const list = (await idb.all()).sort((a, b) => b.updated - a.updated);
  $('#app').innerHTML = `<div class="top"><h1>POI surveys</h1></div><main>
    <button class="btn primary" style="width:100%" data-act="new">New survey</button>
    <button class="btn" style="width:100%;margin-top:8px" data-act="openAdmin">POI reference table (admin)</button>
    <h2>Drafts</h2>
    ${list.length ? `<div class="card">${list.map(s => `<div class="list-item"><div class="grow" data-act="open" data-id="${s.id}" style="cursor:pointer">
      <div class="t">${esc(s.facility.name || 'Untitled survey')}</div>
      <div class="s">${s.cameras.length} camera${s.cameras.length === 1 ? '' : 's'} · edited ${new Date(s.updated).toLocaleString()}</div></div>
      <button class="btn small" data-act="open" data-id="${s.id}">Open</button>
      <button class="btn small danger" data-act="delete" data-id="${s.id}" aria-label="Delete draft">Delete</button></div>`).join('')}</div>`
      : `<div class="empty">No surveys yet. Start one and it saves automatically on this device.</div>`}
  </main>`;
}

function renderSurvey() {
  const iss = issues();
  const done = i => i === 0 ? !iss.some(x => x.s === 0) : i === 1 ? !iss.some(x => x.s === 1) : true;
  const body = [siteStep, camerasStep, setupStep, reviewStep][step]();
  $('#app').innerHTML = `<div class="top"><button data-act="home" aria-label="Back to drafts">‹</button>
    <h1>${esc(S.facility.name || 'New survey')}</h1><span class="saved" id="saved">Saved</span></div>
    <main>${body}</main>
    <nav class="tabs">${STEPS.map((n, i) => `<button class="${i === step ? 'on' : ''} ${i !== step && done(i) && i < 4 ? 'done' : ''}" data-act="step" data-n="${i}"><b>${i + 1}</b>${n}</button>`).join('')}</nav>`;
}

function siteStep() {
  return `<h2>Site</h2>
  <div class="card"><div class="grid">
    ${fld('Facility name', 'facility.name', { wide: true, ph: 'e.g. Eatalian Pizza Pasta Panini_ SF_140' })}
    ${fld('Location', 'facility.location', { wide: true, ph: 'e.g. Vendome Palace Mall Food Court' })}
    ${sel('Category', 'facility.category', CAT.categories || [])}
    <div class="f"><span>Type</span><div class="seg"><button data-act="setType" data-v="as_build" class="${S.facility.type === 'as_build' ? 'on' : ''}">As-build</button>
      <button data-act="setType" data-v="new" class="${S.facility.type === 'new' ? 'on' : ''}">New</button></div></div>
    ${fld('Report #', 'report.number')}${fld('Report date', 'report.date')}${fld('Revision', 'report.revision')}${fld('Surveyed by', 'author')}
  </div></div>
  <details class="card"><summary>Client details</summary><div class="grid">
    ${fld('Name', 'client.name')}${fld('Mobile', 'client.mobile', { type: 'tel' })}${fld('Designation', 'client.designation')}${fld('Email', 'client.email', { type: 'email' })}</div></details>
  <details class="card"><summary>Contractor details</summary><div class="grid">
    ${fld('Contractor', 'contractor.company', { wide: true })}${fld('Name', 'contractor.name')}${fld('Mobile', 'contractor.mobile', { type: 'tel' })}
    ${fld('Designation', 'contractor.designation')}${fld('Email', 'contractor.email', { type: 'email' })}
    ${fld('Certified engineer', 'contractor.certified_engineer')}${fld('Certified technician', 'contractor.certified_technician')}</div></details>
  <div class="row end"><button class="btn primary" data-act="step" data-n="1">Next: cameras</button></div>`;
}

function autoPanel(c) {
  const r = poiResult(c);
  if (!String(c.distance_m).trim()) return `<div class="auto-panel"><span class="auto-tag">AUTO</span> Enter a distance to calculate height and lens from the POI reference table.</div>`;
  if (!r.ok) return `<div class="auto-panel bad"><span class="auto-tag bad">AUTO</span> ${esc(r.error)}</div>`;
  return `<div class="auto-panel ok"><span class="auto-tag">AUTO</span>
    <span><b>Height</b> ${r.height} m</span><span><b>Lens</b> ${esc(r.lens)}</span>
    <span class="mute">from the POI table at ${r.table_distance} m, ${esc(String(c.viewing_angle))}\u00b0</span></div>`;
}
function camerasStep() {
  return `<div class="total"><span>Total cameras</span><span id="totalCams">${totalCams()}</span></div>
  <p style="color:var(--mute);font-size:.86rem;margin:0 4px 12px">Height and lens are calculated automatically from Distance and Viewing angle, using the POI Camera Installation Table.</p>
  ${S.cameras.map((c, i) => `<div class="card"><div class="spread"><h3>Camera ${String(i + 1).padStart(2, '0')}${c.location_name ? ' – ' + esc(c.location_name) : ''}</h3>
    <div class="row"><button class="btn small" data-act="dupCam" data-i="${i}">Copy</button><button class="btn small danger" data-act="delCam" data-i="${i}">Remove</button></div></div>
    <div class="grid">
    ${fld('Location name', `cameras.${i}.location_name`, { wide: true, ph: 'e.g. Front Counter' })}
    ${fld('Distance to target (m)', `cameras.${i}.distance_m`, { mode: 'decimal', calc: true })}${fld('Target area (m)', `cameras.${i}.target_area_m`, { mode: 'decimal' })}
    ${sel('Viewing angle', `cameras.${i}.viewing_angle`, (CAT.angles || [6, 7, 8]).map(String), { calc: true })}${fld('Quantity', `cameras.${i}.qty`, { type: 'number', mode: 'numeric' })}
    </div>
    <div class="wide" id="auto-${i}">${autoPanel(c)}</div>
    <div class="grid" style="margin-top:10px">
    ${sel('Camera model', `cameras.${i}.camera_model`, CAT.camera_models || [])}${sel('Installation type', `cameras.${i}.install_type`, CAT.install_types || [])}
    ${sel('Environment', `cameras.${i}.environment`, CAT.environments || [])}
    ${fld('Remarks', `cameras.${i}.remarks`, { wide: true, area: true, ph: 'Optional – not printed in the report' })}
    </div>
    <h3 style="margin:14px 0 8px">Photos</h3>
    <div class="grid">${slot(i, 'target', 'Target area photo', 'Photo of the area to monitor')}${slot(i, 'camera', 'Proposed camera position photo', 'Photo of where the camera goes')}</div>
    </div>`).join('') || '<div class="empty">No cameras yet.</div>'}
  <button class="btn olive" style="width:100%" data-act="addCam">Add camera</button>
  <div class="row end" style="margin-top:12px"><button class="btn primary" data-act="step" data-n="2">Next: setup</button></div>`;
}

function slot(i, kind, label, ph) {
  const p = S.cameras[i].photos[kind];
  return `<div class="slot ${p ? 'filled' : ''}"><div class="lbl">${label}</div>
    ${p ? `<img src="${p.flat}" alt="${label}">` : `<div class="ph">${ph}</div>`}
    <div class="row">
      ${p ? `<button class="btn small primary" data-act="editPhoto" data-i="${i}" data-k="${kind}">Edit marks</button><button class="btn small" data-act="addSticker" data-i="${i}" data-k="${kind}">Add sticker</button>` : ''}
      <label class="btn small ${p ? '' : 'primary'}"><input type="file" accept="image/*" capture="environment" hidden data-photo="${i}:${kind}">${p ? 'Retake' : 'Take photo'}</label>
      <label class="btn small"><input type="file" accept="image/*" hidden data-photo="${i}:${kind}">Gallery</label></div></div>`;
}
function setupStep() {
  return `<h2>Camera settings</h2><div class="card"><div class="grid">
    ${fld('Encoding', 'config.encoding')}${fld('Resolution', 'config.resolution')}${fld('FPS', 'config.fps', { mode: 'numeric' })}${fld('Bit rate (kbps)', 'config.bitrate_kbps', { mode: 'numeric' })}
    ${fld('Events per day per camera', 'config.events_per_day', { type: 'number', mode: 'numeric' })}
    ${sel('WDR – day', 'config.wdr_day', ['ON', 'OFF'])}${sel('WDR – night', 'config.wdr_night', ['ON', 'OFF'])}${fld('Camera vendor', 'vendor', { wide: true })}</div></div>
  <h2>NVR / recorder</h2>
  ${S.nvr.map((d, i) => `<div class="card"><div class="spread"><h3>Item ${i + 1}</h3><button class="btn small danger" data-act="delNvr" data-i="${i}">Remove</button></div><div class="grid">
    ${fld('Device type', `nvr.${i}.device_type`)}${fld('Quantity', `nvr.${i}.qty`, { mode: 'numeric' })}${fld('Model', `nvr.${i}.model`, { wide: true })}${fld('Description', `nvr.${i}.description`, { wide: true })}</div></div>`).join('')}
  <button class="btn olive" style="width:100%" data-act="addNvr">Add device</button>
  <h2>Floor key plan</h2>
  <div class="card">${S.floor_plan ? `<img src="${S.floor_plan.flat}" alt="Floor plan" style="width:100%;border-radius:6px;margin-bottom:8px">` : '<div class="empty" style="padding:12px">Optional. Add a photo or scan of the floor plan and mark each camera on it.</div>'}
    <div class="row">${S.floor_plan ? '<button class="btn small primary" data-act="editFloor">Edit marks</button><button class="btn small danger" data-act="delFloor">Remove</button>' : ''}
    <label class="btn small ${S.floor_plan ? '' : 'primary'}"><input type="file" accept="image/*" hidden data-photo="floor">${S.floor_plan ? 'Replace' : 'Add floor plan'}</label></div></div>
  <div class="row end"><button class="btn primary" data-act="step" data-n="3">Next: review</button></div>`;
}

function reviewStep() {
  const iss = issues(), st = storageEstimate(), f = S.facility;
  return `<h2>Review</h2>
  ${iss.length ? `<div class="card"><h3>Fix before generating</h3><ul class="issues">${iss.map(x => `<li>${esc(x.t)} <a data-act="step" data-n="${x.s}">Fix</a></li>`).join('')}</ul></div>`
    : `<div class="card"><span class="badge">Ready to generate</span></div>`}
  <div class="card"><div class="spread"><h3>Site</h3><button class="btn small" data-act="step" data-n="0">Edit</button></div>
    <dl class="kv"><dt>Facility</dt><dd>${esc(f.name)}</dd><dt>Location</dt><dd>${esc(f.location)}</dd><dt>Category</dt><dd>${esc(f.category)}</dd>
    <dt>Type</dt><dd>${f.type === 'as_build' ? 'As-build' : 'New'}</dd><dt>Report</dt><dd>${esc(S.report.number || '—')} · REV ${esc(S.report.revision)} · ${esc(S.report.date)}</dd></dl></div>
  <div class="card"><div class="spread"><h3>Cameras · ${totalCams()} total</h3><button class="btn small" data-act="step" data-n="1">Edit</button></div>
    ${S.cameras.map((c, i) => { const r = poiResult(c); return `<div class="list-item"><div class="grow"><div class="t">${String(i + 1).padStart(2, '0')} · ${esc(c.location_name || 'unnamed')}${(parseInt(c.qty) || 1) > 1 ? ' ×' + parseInt(c.qty) : ''}</div>
      <div class="s">${r.ok ? `${r.height} m high (AUTO) · ${esc(c.distance_m)} m away · ${esc(r.lens)} · ${esc(c.install_type)} · ${esc(c.environment)}` : `<span style="color:var(--err)">${esc(r.error)}</span>`}</div></div>
      ${c.photos.target && c.photos.camera ? '<span class="badge">Photos ✓</span>' : '<span class="badge bad">Photos missing</span>'}</div>`; }).join('')}</div>
  <div class="card"><div class="spread"><h3>Storage estimate</h3><button class="btn small" data-act="step" data-n="2">Edit</button></div>
    <dl class="kv"><dt>Required</dt><dd>${st.total} TB</dd><dt>With 10% extra</dt><dd><b>${st.extra} TB</b></dd><dt>Recorder items</dt><dd>${S.nvr.length}</dd></dl></div>
  <button class="btn primary" style="width:100%" data-act="generate" ${iss.length ? 'disabled' : ''}>Generate Word report</button>`;
}

/* ============ overlay (progress / result) ============ */
function overlay(html) { closeOverlay(); const o = document.createElement('div'); o.className = 'overlay'; o.id = 'ov'; o.innerHTML = `<div class="card">${html}</div>`; document.body.appendChild(o); }
function closeOverlay() { $('#ov')?.remove(); }
let lastUrl = null;

async function callApi(path) {
  const payload = clone({ ...S, cameras: S.cameras.map(c => ({ ...c, photos: { target: c.photos.target && { flat: c.photos.target.flat }, camera: c.photos.camera && { flat: c.photos.camera.flat } } })),
    floor_plan: S.floor_plan && { flat: S.floor_plan.flat } });
  return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
}
async function generate() {
  overlay('<div class="spin"></div><p style="text-align:center;margin:0">Generating your Word report…</p>');
  try {
    const r = await callApi('/api/report');
    if (!r.ok) { const j = await r.json().catch(() => ({})); return overlay(`<h3>Report not generated</h3><ul class="issues">${(j.errors || ['Something went wrong.']).map(e => `<li>${esc(e)}</li>`).join('')}</ul>
      <div class="row end" style="margin-top:12px"><button class="btn primary" data-act="closeOv">Back to survey</button></div>`); }
    const blob = await r.blob(); if (lastUrl) URL.revokeObjectURL(lastUrl); lastUrl = URL.createObjectURL(blob);
    const name = (r.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/)?.[1] || 'POI_Survey_Report.docx';
    overlay(`<h3>Report generated successfully</h3><p style="margin:0 0 12px;color:var(--mute)">${esc(name)}</p>
      <div class="row" style="flex-direction:column;align-items:stretch">
      <a class="btn primary" href="${lastUrl}" download="${esc(decodeURIComponent(name))}">Download Word report</a>
      ${CAPS.preview ? '<button class="btn" data-act="preview">Preview report</button>' : ''}
      <button class="btn" data-act="generate">Generate again</button>
      <button class="btn" data-act="closeOv">Edit survey</button></div>`);
  } catch (e) { overlay(`<h3>Report not generated</h3><p>Could not reach the app server. Check that it is still running.</p><div class="row end"><button class="btn primary" data-act="closeOv">Close</button></div>`); }
}
async function preview() {
  overlay('<div class="spin"></div><p style="text-align:center;margin:0">Preparing preview…</p>');
  const r = await callApi('/api/preview');
  if (!r.ok) { const j = await r.json().catch(() => ({})); return overlay(`<h3>Preview failed</h3><p>${esc((j.errors || [''])[0])}</p><div class="row end"><button class="btn primary" data-act="closeOv">Close</button></div>`); }
  const url = URL.createObjectURL(await r.blob());
  overlay(`<h3>Preview ready</h3><div class="row" style="flex-direction:column;align-items:stretch"><a class="btn primary" href="${url}" target="_blank" rel="noopener">Open preview</a>
    ${lastUrl ? `<a class="btn" href="${lastUrl}" download="POI_Survey_Report.docx">Download Word report</a>` : ''}<button class="btn" data-act="closeOv">Close</button></div>`);
}

/* ============ photo handling ============ */
function fileToDataURL(file, max = 2000) {
  return new Promise((res, rej) => { const reader = new FileReader(), im = new Image();
    im.onload = () => { const k = Math.min(1, max / Math.max(im.width, im.height)), c = document.createElement('canvas');
      c.width = Math.round(im.width * k); c.height = Math.round(im.height * k); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
      res(c.toDataURL('image/jpeg', 0.86)); };
    im.onerror = () => rej(new Error('Could not read that image')); reader.onerror = () => rej(new Error('Could not read that photo file'));
    reader.onload = () => { im.src = reader.result; }; reader.readAsDataURL(file); });
}
async function addPhoto(target, file) {
  const orig = await fileToDataURL(file); const isFloor = target === 'floor';
  const [i, kind] = isFloor ? [null, null] : target.split(':');
  const r = await openEditor({ title: isFloor ? 'Floor key plan' : `Camera ${String(+i + 1).padStart(2, '0')} – ${kind === 'target' ? 'target area' : 'camera position'}`,
    hint: isFloor ? 'Add a camera symbol for each camera and label it.' : kind === 'target' ? 'Drag a box over the area the camera must see.' : 'Tap where the camera will be mounted, then rotate it to face the target.',
    src: orig, ann: { fit: isFloor ? 'contain' : 'cover', objs: [] }, tool: isFloor ? 'camera' : kind === 'target' ? 'target' : 'camera' });
  if (!r) return;
  const photo = { orig, ann: r.ann, flat: r.flat };
  if (isFloor) S.floor_plan = photo; else S.cameras[i].photos[kind] = photo;
  scheduleSave(); render();
}
async function editPhoto(p, title, hint, assign) {
  const r = await openEditor({ title, hint: `${hint} Pinch with two fingers to zoom the selected sticker.`, src: p.orig, ann: p.ann, tool: 'select' });
  if (r) { assign({ orig: p.orig, ann: r.ann, flat: r.flat }); scheduleSave(); render(); }
}

/* ============ annotation editor ============ */
const CW = 1600, CH = 1200;
const STICKERS = {
  wall_mount: { label: 'Wall Mount', file: 'Wall Mount.png' },
  thin_pole: { label: 'Thin Pole', file: 'Thin Pole.png' },
  thick_pole: { label: 'Thick Pole', file: 'Thick Pole.png' },
  target_area: { label: 'Target Area', file: 'Target Area.png' },
  rhs_wall_mount: { label: 'RHS Wall Mount', file: 'RHS Wall Mount.png' },
  pm: { label: 'PM', file: 'PM.png' },
  pendant: { label: 'Pendant', file: 'Pendant.png' },
  outline: { label: 'Outline', file: 'Outline.png' },
  lhs_wall_mount: { label: 'LHS Wall Mount', file: 'LHS Wall Mount.png' },
  hanging_camera: { label: 'Hanging Camera', file: 'Hanging Camera.png' },
  ceiling_mount: { label: 'Ceiling Mount', file: 'Ceiling Mount.png' }
};
function paintScene(ctx, img, fit, objs, selId, stickerImages) {
  ctx.clearRect(0, 0, CW, CH); ctx.fillStyle = fit === 'contain' ? '#1a1a1a' : '#000'; ctx.fillRect(0, 0, CW, CH);
  if (img && img.width) { const k = (fit === 'contain' ? Math.min : Math.max)(CW / img.width, CH / img.height), w = img.width * k, h = img.height * k;
    ctx.drawImage(img, (CW - w) / 2, (CH - h) / 2, w, h); }
  objs.forEach(o => drawObj(ctx, o, stickerImages)); const so = objs.find(o => o.id === selId);
  if (so) { const b = bbox(ctx, so); ctx.save(); ctx.setLineDash([14, 10]); ctx.lineWidth = 4; ctx.strokeStyle = '#1a73e8'; ctx.strokeRect(b.x - 8, b.y - 8, b.w + 16, b.h + 16);
    if (so.type === 'sticker') { ctx.setLineDash([]); ctx.fillStyle = '#1a73e8'; [[b.x, b.y], [b.x + b.w, b.y + b.h]].forEach(([x, y]) => ctx.fillRect(x - 14, y - 14, 28, 28)); }
    ctx.restore(); }
}
function drawObj(ctx, o, stickerImages = {}) {
  ctx.save(); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  if (o.type === 'target') {
    ctx.fillStyle = 'rgba(255,230,0,.28)'; ctx.fillRect(o.x, o.y, o.w, o.h); ctx.strokeStyle = 'rgba(225,60,90,.9)'; ctx.lineWidth = 8; ctx.strokeRect(o.x, o.y, o.w, o.h);
    const fs = Math.max(20, Math.min(58, o.w / 7)); ctx.font = `600 ${fs}px Calibri, Arial, sans-serif`; const tw = ctx.measureText('TARGET AREA').width;
    const cx = o.x + o.w / 2, cy = o.y + o.h / 2; ctx.fillStyle = '#ffff00'; ctx.fillRect(cx - tw / 2 - 14, cy - fs * .75, tw + 28, fs * 1.5);
    ctx.fillStyle = '#e8590c'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('TARGET AREA', cx, cy + 2);
  } else if (o.type === 'box') { ctx.strokeStyle = '#e53935'; ctx.lineWidth = 8; ctx.strokeRect(o.x, o.y, o.w, o.h);
  } else if (o.type === 'circle') { ctx.strokeStyle = '#e53935'; ctx.lineWidth = 8; ctx.beginPath(); ctx.ellipse(o.x + o.w / 2, o.y + o.h / 2, Math.max(1, o.w / 2), Math.max(1, o.h / 2), 0, 0, 7); ctx.stroke();
  } else if (o.type === 'arrow') {
    const a = Math.atan2(o.y2 - o.y1, o.x2 - o.x1); ctx.strokeStyle = ctx.fillStyle = '#e53935'; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.moveTo(o.x1, o.y1); ctx.lineTo(o.x2 - Math.cos(a) * 30, o.y2 - Math.sin(a) * 30); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(o.x2, o.y2); ctx.lineTo(o.x2 - 46 * Math.cos(a - .42), o.y2 - 46 * Math.sin(a - .42)); ctx.lineTo(o.x2 - 46 * Math.cos(a + .42), o.y2 - 46 * Math.sin(a + .42)); ctx.closePath(); ctx.fill();
  } else if (o.type === 'camera') {
    const s = o.s; ctx.translate(o.x, o.y); ctx.rotate((o.a || 0) * Math.PI / 180);
    ctx.fillStyle = '#fff'; ctx.strokeStyle = '#e53935'; ctx.lineWidth = 6; ctx.beginPath(); ctx.roundRect(-s / 2, -s / 2, s, s, 10); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(0, 0, s * .3, 0, 7); ctx.fill(); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(0, 0, s * .16, 0, 7); ctx.fill();
    ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(-s * .04, -s * .05, s * .06, 0, 7); ctx.fill();
    ctx.fillStyle = '#e53935'; ctx.beginPath(); ctx.moveTo(s / 2 + 4, -s * .18); ctx.lineTo(s / 2 + s * .34, 0); ctx.lineTo(s / 2 + 4, s * .18); ctx.closePath(); ctx.fill();
  } else if (o.type === 'text') {
    ctx.font = 'bold 44px Calibri, Arial, sans-serif'; ctx.textBaseline = 'top'; const w = ctx.measureText(o.text).width;
    ctx.fillStyle = '#ffff00'; ctx.fillRect(o.x - 10, o.y - 6, w + 20, 62); ctx.fillStyle = '#d00000'; ctx.fillText(o.text, o.x, o.y);
  } else if (o.type === 'sticker') {
    const sticker = STICKERS[o.sticker] || STICKERS.target_area;
    ctx.translate(o.x + o.w / 2, o.y + o.h / 2); ctx.rotate((o.a || 0) * Math.PI / 180);
    const image = stickerImages[o.sticker];
    if (image && image.complete && image.naturalWidth) ctx.drawImage(image, -o.w / 2, -o.h / 2, o.w, o.h);
    else {
      ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#d00000'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.roundRect(-o.w / 2, -o.h / 2, o.w, o.h, 18); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#d00000'; ctx.font = 'bold 34px Calibri, Arial, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(sticker.label, 0, 2);
    }
  }
  ctx.restore();
}
function bbox(ctx, o) {
  if (o.type === 'arrow') return { x: Math.min(o.x1, o.x2), y: Math.min(o.y1, o.y2), w: Math.abs(o.x2 - o.x1), h: Math.abs(o.y2 - o.y1) };
  if (o.type === 'camera') { const r = o.s * .75; return { x: o.x - r, y: o.y - r, w: r * 2, h: r * 2 }; }
  if (o.type === 'text') { ctx.save(); ctx.font = 'bold 44px Calibri, Arial, sans-serif'; const w = ctx.measureText(o.text).width; ctx.restore(); return { x: o.x - 10, y: o.y - 6, w: w + 20, h: 62 }; }
  if (o.type === 'sticker') return { x: o.x, y: o.y, w: o.w, h: o.h };
  return { x: o.x, y: o.y, w: o.w, h: o.h };
}
function distSeg(p, a, b) { const dx = b.x - a.x, dy = b.y - a.y, l = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l)); return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy); }
function hit(ctx, objs, p) {
  for (let i = objs.length - 1; i >= 0; i--) { const o = objs[i];
    if (o.type === 'arrow') { if (distSeg(p, { x: o.x1, y: o.y1 }, { x: o.x2, y: o.y2 }) < 28) return o; continue; }
    const b = bbox(ctx, o), pad = (o.type === 'box' || o.type === 'circle') ? 0 : 0;
    if (p.x >= b.x - pad && p.x <= b.x + b.w + pad && p.y >= b.y - pad && p.y <= b.y + b.h + pad) return o; }
  return null;
}
function stickerHandle(ctx, o, p) {
  if (!o || o.type !== 'sticker') return false;
  const b = bbox(ctx, o); return Math.hypot(p.x - (b.x + b.w), p.y - (b.y + b.h)) <= 34;
}
function moveObj(o, dx, dy) { if (o.type === 'arrow') { o.x1 += dx; o.y1 += dy; o.x2 += dx; o.y2 += dy; } else { o.x += dx; o.y += dy; } }

function openEditor({ title, hint, src, ann, tool = 'select' }) {
  return new Promise(resolve => {
    const ov = document.createElement('div'); ov.className = 'editor';
    ov.innerHTML = `<header><button class="btn small" id="ed-cancel">Cancel</button><h3>${esc(title)}</h3><button class="btn small primary" id="ed-done">Done</button></header>
      <div class="hint">${esc(hint)}</div><div class="stage"><canvas width="${CW}" height="${CH}"></canvas></div>
      <div class="bar">
        <span class="tool-label">Stickers</span>
        ${Object.entries(STICKERS).map(([k, s]) => `<button class="sticker-tool" data-tool="sticker:${k}" title="${esc(s.label)}"><img src="stickers/${encodeURIComponent(s.file)}" alt=""><span>${esc(s.label)}</span></button>`).join('')}
        <div class="sep"></div><button id="ed-rot">Rotate</button><button id="ed-width-minus">W -</button><button id="ed-width-plus">W +</button><button id="ed-height-minus">H -</button><button id="ed-height-plus">H +</button><button id="ed-del">Delete</button><button id="ed-undo">Undo</button><button id="ed-redo">Redo</button>
        <div class="sep"></div><button id="ed-fit"></button></div>`;
    document.body.appendChild(ov); document.body.style.overflow = 'hidden';
    const cv = $('canvas', ov), ctx = cv.getContext('2d'); const img = new Image();
    const stickerImages = {};
    let objs = clone(ann?.objs || []), fit = ann?.fit || 'cover', sel = null, cur = tool, drag = null, hist = [JSON.stringify(objs)], hi = 0;
    const pointers = new Map(); let pinch = null;
    const redraw = () => { paintScene(ctx, img, fit, objs, sel, stickerImages);
      ov.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === cur));
      $('#ed-undo', ov).disabled = hi === 0; $('#ed-redo', ov).disabled = hi === hist.length - 1;
      const so = objs.find(o => o.id === sel); $('#ed-rot', ov).disabled = !(so && (so.type === 'camera' || so.type === 'sticker'));
      ['#ed-width-minus', '#ed-width-plus', '#ed-height-minus', '#ed-height-plus'].forEach(id => $(id, ov).disabled = !(so && so.type === 'sticker'));
      $('#ed-del', ov).disabled = !so;
      $('#ed-fit', ov).textContent = fit === 'cover' ? 'Fill frame' : 'Whole photo'; };
    Object.entries(STICKERS).forEach(([key, sticker]) => {
      const image = new Image(); image.onload = redraw; image.src = `stickers/${encodeURIComponent(sticker.file)}`; stickerImages[key] = image;
    });
    const stickersReady = () => Promise.all(Object.values(stickerImages).map(image => image.complete ? Promise.resolve() : new Promise(resolve => {
      image.onload = resolve; image.onerror = resolve;
    })));
    const commit = () => { hist = hist.slice(0, hi + 1); hist.push(JSON.stringify(objs)); hi = hist.length - 1; };
    const photoReady = new Promise(resolve => { img.onload = () => { redraw(); resolve(); }; img.onerror = resolve; });
    const pt = e => { const r = cv.getBoundingClientRect(); return { x: (e.clientX - r.left) * CW / r.width, y: (e.clientY - r.top) * CH / r.height }; };
    img.src = src;
    cv.addEventListener('pointerdown', e => {
      cv.setPointerCapture(e.pointerId); pointers.set(e.pointerId, pt(e));
      if (pointers.size === 2 && sel) {
        const sticker = objs.find(o => o.id === sel);
        if (sticker?.type === 'sticker') {
          const values = [...pointers.values()];
          pinch = { start: Math.max(1, Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y)), w: sticker.w, h: sticker.h, x: sticker.x, y: sticker.y };
          drag = null; e.preventDefault(); return;
        }
      }
      const p = pt(e);
      if (cur === 'select') {
        const selected = objs.find(o => o.id === sel);
        if (stickerHandle(ctx, selected, p)) drag = { mode: 'resize', o: selected };
        else { const o = hit(ctx, objs, p); sel = o ? o.id : null; drag = o ? { mode: 'move', last: p, moved: false, o } : null; }
      }
      else if (cur === 'camera') { const o = { id: uid(), type: 'camera', x: p.x, y: p.y, s: 120, a: 0 }; objs.push(o); sel = o.id; commit(); cur = 'select'; drag = null; }
      else if (cur.startsWith('sticker:')) { const o = { id: uid(), type: 'sticker', sticker: cur.slice(8), x: p.x - 130, y: p.y - 45, w: 260, h: 90, a: 0 }; objs.push(o); sel = o.id; commit(); cur = 'select'; drag = null; }
      else if (cur === 'text') { const t = prompt('Label text'); if (t && t.trim()) { const o = { id: uid(), type: 'text', x: p.x, y: p.y, text: t.trim() }; objs.push(o); sel = o.id; commit(); } cur = 'select'; }
      else { const o = cur === 'arrow' ? { id: uid(), type: 'arrow', x1: p.x, y1: p.y, x2: p.x, y2: p.y } : { id: uid(), type: cur, x: p.x, y: p.y, w: 0, h: 0 };
        objs.push(o); sel = null; drag = { mode: 'draw', o, s: p }; }
      redraw(); });
    cv.addEventListener('pointermove', e => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, pt(e));
      if (pinch && sel && pointers.size >= 2) {
        const values = [...pointers.values()]; const distance = Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
        const o = objs.find(x => x.id === sel); if (o?.type === 'sticker' && pinch.start) { const scale = Math.max(.25, Math.min(4, distance / pinch.start));
          const nw = Math.max(40, pinch.w * scale), nh = Math.max(30, pinch.h * scale); o.x = pinch.x - (nw - pinch.w) / 2; o.y = pinch.y - (nh - pinch.h) / 2; o.w = nw; o.h = nh; redraw(); e.preventDefault(); }
        return;
      }
      if (!drag) return; const p = pt(e);
      if (drag.mode === 'resize') { const o = drag.o; const nw = Math.max(40, p.x - o.x), nh = Math.max(30, p.y - o.y); o.w = nw; o.h = nh; redraw(); return; }
      if (drag.mode === 'move') { moveObj(drag.o, p.x - drag.last.x, p.y - drag.last.y); drag.last = p; drag.moved = true; }
      else { const o = drag.o; if (o.type === 'arrow') { o.x2 = p.x; o.y2 = p.y; } else { o.x = Math.min(drag.s.x, p.x); o.y = Math.min(drag.s.y, p.y); o.w = Math.abs(p.x - drag.s.x); o.h = Math.abs(p.y - drag.s.y); } }
      redraw(); });
    const end = () => { if (!drag) return;
      if (drag.mode === 'move') { if (drag.moved) commit(); }
      else if (drag.mode === 'resize') commit();
      else { const o = drag.o, tiny = o.type === 'arrow' ? Math.hypot(o.x2 - o.x1, o.y2 - o.y1) < 30 : (o.w < 30 || o.h < 30);
        if (tiny) objs.pop(); else { sel = o.id; commit(); } cur = 'select'; }
      drag = null; redraw(); };
    cv.addEventListener('pointerup', e => { pointers.delete(e.pointerId); if (pointers.size < 2 && pinch) { commit(); pinch = null; } end(); });
    cv.addEventListener('pointercancel', e => { pointers.delete(e.pointerId); pinch = null; end(); });
    ov.querySelectorAll('[data-tool]').forEach(b => b.onclick = () => { cur = b.dataset.tool; redraw(); });
    $('#ed-rot', ov).onclick = () => { const o = objs.find(x => x.id === sel); if (o) { o.a = ((o.a || 0) + 30) % 360; commit(); redraw(); } };
    const resizeSticker = (dw, dh) => {
      const o = objs.find(x => x.id === sel); if (!o || o.type !== 'sticker') return;
      const nw = Math.max(40, o.w + dw), nh = Math.max(30, o.h + dh);
      o.x -= (nw - o.w) / 2; o.y -= (nh - o.h) / 2; o.w = nw; o.h = nh; commit(); redraw();
    };
    $('#ed-width-minus', ov).onclick = () => resizeSticker(-20, 0);
    $('#ed-width-plus', ov).onclick = () => resizeSticker(20, 0);
    $('#ed-height-minus', ov).onclick = () => resizeSticker(0, -20);
    $('#ed-height-plus', ov).onclick = () => resizeSticker(0, 20);
    $('#ed-del', ov).onclick = () => { objs = objs.filter(o => o.id !== sel); sel = null; commit(); redraw(); };
    $('#ed-undo', ov).onclick = () => { if (hi > 0) { objs = JSON.parse(hist[--hi]); sel = null; redraw(); } };
    $('#ed-redo', ov).onclick = () => { if (hi < hist.length - 1) { objs = JSON.parse(hist[++hi]); sel = null; redraw(); } };
    $('#ed-fit', ov).onclick = () => { fit = fit === 'cover' ? 'contain' : 'cover'; redraw(); };
    const close = v => { ov.remove(); document.body.style.overflow = ''; resolve(v); };
    $('#ed-cancel', ov).onclick = () => close(null);
    $('#ed-done', ov).onclick = async () => { const done = $('#ed-done', ov); done.disabled = true; await Promise.all([photoReady, stickersReady()]);
      const c = document.createElement('canvas'); c.width = CW; c.height = CH;
      paintScene(c.getContext('2d'), img, fit, objs, null, stickerImages); close({ ann: { fit, objs }, flat: c.toDataURL('image/jpeg', 0.92) }); };
  });
}

/* ============ events ============ */
function refreshAuto(bindPath) {
  const m = bindPath.match(/^cameras\.(\d+)\./); if (!m) return false;
  const i = +m[1]; const panel = document.getElementById('auto-' + i); if (!panel) return false;
  panel.innerHTML = autoPanel(S.cameras[i]); return true;
}
document.addEventListener('input', e => {
  const b = e.target.dataset?.bind; if (!b || !S) return; set(S, b, e.target.value); scheduleSave();
  if (b.endsWith('.qty') && $('#totalCams')) $('#totalCams').textContent = totalCams();
  if (b.endsWith('.distance_m')) refreshAuto(b);
});
document.addEventListener('change', async e => {
  const t = e.target;
  if (t.dataset?.bind && t.tagName === 'SELECT') { set(S, t.dataset.bind, t.value); scheduleSave(); refreshAuto(t.dataset.bind); return; }
  if (t.dataset?.photo && t.files?.[0]) { const f = t.files[0], target = t.dataset.photo; t.value = ''; try { await addPhoto(target, f); } catch (err) { alert(err.message); } }
});
document.addEventListener('click', async e => {
  const el = e.target.closest('[data-act]'); if (!el) return; const a = el.dataset.act, i = +el.dataset.i;
  if (a === 'new') { S = newSurvey(); await idb.put(S); view = 'survey'; step = 0; render(); }
  else if (a === 'open') { S = (await idb.all()).find(s => s.id === el.dataset.id); S.config.events_per_day ??= 1000; view = 'survey'; step = 0; render(); }
  else if (a === 'delete') { if (confirm('Delete this draft and its photos?')) { await idb.del(el.dataset.id); render(); } }
  else if (a === 'home') { clearTimeout(saveTimer); if (S) { S.updated = Date.now(); await idb.put(S); } S = null; view = 'home'; render(); }
  else if (a === 'step') { step = +el.dataset.n; closeOverlay(); render(); window.scrollTo(0, 0); }
  else if (a === 'setType') { S.facility.type = el.dataset.v; scheduleSave(); render(); }
  else if (a === 'addCam') { S.cameras.push(newCamera()); scheduleSave(); render(); }
  else if (a === 'dupCam') { const c = clone(S.cameras[i]); c.id = uid(); c.location_name += ' (copy)'; c.photos = { target: null, camera: null }; S.cameras.splice(i + 1, 0, c); scheduleSave(); render(); }
  else if (a === 'delCam') { if (confirm(`Remove camera ${String(i + 1).padStart(2, '0')} and its photos?`)) { S.cameras.splice(i, 1); scheduleSave(); render(); } }
  else if (a === 'addNvr') { S.nvr.push({ device_type: '', model: '', description: '', qty: 1 }); scheduleSave(); render(); }
  else if (a === 'delNvr') { S.nvr.splice(i, 1); scheduleSave(); render(); }
  else if (a === 'editPhoto') { const k = el.dataset.k, c = S.cameras[i]; editPhoto(c.photos[k], `Camera ${String(i + 1).padStart(2, '0')} – ${k === 'target' ? 'target area' : 'camera position'}`,
      k === 'target' ? 'Drag a box over the area the camera must see.' : 'Tap where the camera will be mounted, then rotate it to face the target.', p => { c.photos[k] = p; }); }
    else if (a === 'addSticker') { closeOverlay(); const k = el.dataset.k, c = S.cameras[i]; editPhoto(c.photos[k], `Camera ${String(i + 1).padStart(2, '0')} – add sticker`,
      'Choose a sticker, tap the photo to place it, then resize or rotate it.', p => { c.photos[k] = p; }); }
  else if (a === 'editFloor') editPhoto(S.floor_plan, 'Floor key plan', 'Add a camera symbol for each camera and label it.', p => { S.floor_plan = p; });
  else if (a === 'delFloor') { S.floor_plan = null; scheduleSave(); render(); }
  else if (a === 'generate') generate();
  else if (a === 'preview') preview();
  else if (a === 'closeOv') closeOverlay();
});
window.addEventListener('beforeunload', () => { if (S) idb.put(S); });

/* ============ admin: edit the POI reference table (heights, lens ranges, models) ============ */
let ADM = null, admPin = '';
async function api(path, opts) { const h = { 'Content-Type': 'application/json' }; if (admPin) h['X-Admin-Pin'] = admPin;
  return fetch(path, { ...opts, headers: h }).then(async r => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) })); }
async function openAdmin() {
  const need = (await api('/api/admin/needs-pin')).body.needs_pin;
  if (need) { const p = prompt('Admin PIN'); if (p === null) return; admPin = p; }
  const r = await api('/api/reference'); if (!r.ok) return alert('Could not load the reference table.');
  ADM = r.body; view = 'admin'; renderAdmin();
}
function renderAdmin(msg) {
  $('#app').innerHTML = `<div class="top"><button data-act="closeAdmin" aria-label="Back">‹</button><h1>POI reference table</h1></div>
  <main>
  <p style="color:var(--mute);font-size:.88rem">This table drives every survey's automatic height and lens calculation. Changes apply to reports generated after saving; surveys already generated keep the numbers they were generated with.</p>
  ${msg ? `<div class="card" style="border-color:${msg.bad ? 'var(--err)' : 'var(--olive)'}"><b style="color:${msg.bad ? 'var(--err)' : 'var(--olive)'}">${msg.bad ? 'Not saved' : 'Saved'}</b>
    ${msg.list?.length ? `<ul class="issues" style="color:${msg.bad ? 'var(--err)' : '#7a6f1f'}">${msg.list.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div>` : ''}
  <div class="card"><h3>Raw configuration (JSON)</h3>
    <textarea id="ref-json" style="width:100%;min-height:46vh;font-family:ui-monospace,Consolas,monospace;font-size:.82rem;border:1px solid #bdbbbb;border-radius:8px;padding:10px">${esc(JSON.stringify(ADM, null, 1))}</textarea>
    <p style="color:var(--mute);font-size:.82rem">Keys: <code>height_table</code> (one row per distance, one value per angle in <code>angles</code>), <code>lens_ranges</code> (non-overlapping min/max → lens), <code>rules.fractional_distance</code> (ceil / floor / nearest), plus the model, install-type, environment and vendor lists used in the app's dropdowns.</p>
    <div class="row"><button class="btn primary" data-act="saveRef">Save</button><button class="btn danger" data-act="resetRef">Reset to shipped default</button></div>
  </div></main>`;
}
async function saveRef() {
  let parsed; try { parsed = JSON.parse($('#ref-json').value); } catch (e) { return renderAdmin({ bad: true, list: ['Not valid JSON: ' + e.message] }); }
  const r = await api('/api/reference', { method: 'POST', body: JSON.stringify(parsed) });
  if (r.status === 401) return renderAdmin({ bad: true, list: ['Wrong admin PIN.'] });
  if (!r.ok) return renderAdmin({ bad: true, list: r.body.errors || ['Could not save.'] });
  ADM = parsed; renderAdmin({ bad: false, list: r.body.warnings || [] });
  CAT = await fetch('/api/catalog').then(x => x.json());
}
document.addEventListener('click', async e => {
  const el = e.target.closest('[data-act]'); if (!el) return; const a = el.dataset.act;
  if (a === 'openAdmin') openAdmin();
  else if (a === 'closeAdmin') { view = 'home'; render(); }
  else if (a === 'saveRef') saveRef();
  else if (a === 'resetRef') { if (confirm('Discard custom changes and restore the shipped POI table?')) { const r = await api('/api/reference/reset', { method: 'POST' });
      if (r.status === 401) return renderAdmin({ bad: true, list: ['Wrong admin PIN.'] });
      ADM = (await api('/api/reference')).body; CAT = await fetch('/api/catalog').then(x => x.json()); renderAdmin({ bad: false, list: ['Restored the shipped default table.'] }); } }
});

(async function init() {
  await idb.open();
  [CAT, CAPS] = await Promise.all([fetch('/api/catalog').then(r => r.json()), fetch('/api/capabilities').then(r => r.json()).catch(() => ({}))]);
  render();
})();
