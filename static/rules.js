'use strict';
/* Browser port of poi_rules.py – same logic, same messages. tools/parity_test.py proves they agree. */
const POI = (() => {
  const EPS = 1e-9;
  const g = x => String(+x.toFixed(6));                       // like Python %g for our values
  const num = x => { const v = parseFloat(String(x ?? '').trim().replace(',', '.')); return Number.isFinite(v) && String(x).trim() !== '' && !/[^0-9.,\-+eE\s]/.test(String(x)) ? v : null; };
  const roundDistance = (d, mode) => mode === 'floor' ? Math.floor(d + EPS) : mode === 'nearest' ? Math.floor(d + 0.5 + EPS) : Math.ceil(d - EPS);
  const sorted = ref => [...ref.lens_ranges].sort((a, b) => a.min - b.min);
  const span = ref => [Math.min(...ref.lens_ranges.map(r => r.min)), Math.max(...ref.lens_ranges.map(r => r.max))];
  function findLens(ref, d) {
    const hits = ref.lens_ranges.filter(r => r.min - EPS <= d && d <= r.max + EPS);
    if (hits.length === 1) return [hits[0].lens, null];
    if (hits.length > 1) return [null, `Reference table error: lens ranges overlap at ${g(d)} m. Ask the administrator to fix the table.`];
    const [lo, hi] = span(ref);
    if (d < lo - EPS || d > hi + EPS) return [null, `Distance is outside the supported POI reference range (${g(lo)}–${g(hi)} m).`];
    const rs = sorted(ref);
    for (let i = 0; i < rs.length - 1; i++) if (rs[i].max < d && d < rs[i + 1].min)
      return [null, `Distance ${g(d)} m falls between two lens ranges (${g(rs[i].max)} m and ${g(rs[i + 1].min)} m). Use a distance inside a supported range.`];
    return [null, `Distance ${g(d)} m is not covered by any lens range.`];
  }
  function calc(ref, distance, angle) {
    const out = { ok: false, height: null, lens: null, table_distance: null, error: null };
    const d = num(distance);
    if (d === null || d <= 0) { out.error = 'Please enter a valid distance.'; return out; }
    const a = num(angle);
    if (a === null || !ref.angles.some(x => Math.abs(x - a) < EPS)) { out.error = 'Please select a viewing angle.'; return out; }
    const [lens, err] = findLens(ref, d); if (err) { out.error = err; return out; }
    const td = roundDistance(d, (ref.rules || {}).fractional_distance || 'ceil');
    const row = ref.height_table.find(r => Math.abs(r.distance - td) < EPS);
    if (!row) { out.error = `The POI table has no height for ${g(td)} m.`; return out; }
    const key = Object.keys(row.height).find(k => Math.abs(parseFloat(k) - a) < EPS);
    const h = key === undefined ? null : row.height[key];
    if (h === null || h === undefined) { out.error = `The POI table has no ${g(a)}° height for ${g(td)} m.`; return out; }
    return { ok: true, height: +h, lens, table_distance: td, error: null };
  }
  return { calc, num, g };
})();
if (typeof module !== 'undefined') module.exports = POI;
