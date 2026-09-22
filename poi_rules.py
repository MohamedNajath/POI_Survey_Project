"""
POI rule engine – the ONLY place height / lens logic lives on the server.
static/rules.js is a line-for-line port used for instant feedback in the browser; tools/parity_test.py keeps them identical.
Everything is driven by the reference dict (reference.json): nothing about heights, lenses or ranges is hard-coded here.
"""
import math

EPS = 1e-9
MODES = ('ceil', 'floor', 'nearest')

def _num(x):
    try: v = float(str(x).strip().replace(',', '.'))
    except (TypeError, ValueError): return None
    return v if math.isfinite(v) else None

def round_distance(d, mode):
    if mode == 'floor': return math.floor(d + EPS)
    if mode == 'nearest': return math.floor(d + 0.5 + EPS)
    return math.ceil(d - EPS)                       # 'ceil' (default): never under-estimate the mounting height

def sorted_ranges(ref): return sorted(ref['lens_ranges'], key=lambda r: r['min'])

def supported_span(ref):
    rs = ref['lens_ranges']; return min(r['min'] for r in rs), max(r['max'] for r in rs)

def find_lens(ref, d):
    """Exactly one lens range must contain d. Returns (lens, error)."""
    hits = [r for r in ref['lens_ranges'] if r['min'] - EPS <= d <= r['max'] + EPS]
    if len(hits) == 1: return hits[0]['lens'], None
    if len(hits) > 1: return None, 'Reference table error: lens ranges overlap at %g m. Ask the administrator to fix the table.' % d
    lo, hi = supported_span(ref)
    if d < lo - EPS or d > hi + EPS:
        return None, 'Distance is outside the supported POI reference range (%g–%g m).' % (lo, hi)
    rs = sorted_ranges(ref)                          # inside the span but in no range => gap between two ranges
    for a, b in zip(rs, rs[1:]):
        if a['max'] < d < b['min']:
            return None, 'Distance %g m falls between two lens ranges (%g m and %g m). Use a distance inside a supported range.' % (d, a['max'], b['min'])
    return None, 'Distance %g m is not covered by any lens range.' % d

def calc(ref, distance, angle):
    """-> {ok, height, lens, table_distance, error}. Never guesses: any doubt returns ok=False with a message."""
    out = {'ok': False, 'height': None, 'lens': None, 'table_distance': None, 'error': None}
    d = _num(distance)
    if d is None or d <= 0: out['error'] = 'Please enter a valid distance.'; return out
    a = _num(angle)
    if a is None or a not in [float(x) for x in ref['angles']]: out['error'] = 'Please select a viewing angle.'; return out
    lens, err = find_lens(ref, d)
    if err: out['error'] = err; return out
    td = round_distance(d, ref.get('rules', {}).get('fractional_distance', 'ceil'))
    row = next((r for r in ref['height_table'] if abs(r['distance'] - td) < EPS), None)
    if row is None: out['error'] = 'The POI table has no height for %g m.' % td; return out
    key = next((k for k in row['height'] if abs(float(k) - a) < EPS), None)
    h = row['height'].get(key) if key is not None else None
    if h is None: out['error'] = 'The POI table has no %g° height for %g m.' % (a, td); return out
    out.update(ok=True, height=float(h), lens=lens, table_distance=td); return out

def validate_reference(ref):
    """Checked on every admin save. Returns (errors, warnings). Errors block saving."""
    E, Wn = [], []
    try:
        angles = ref['angles']
        if not angles or len(set(map(float, angles))) != len(angles): E.append('Viewing angles must be a non-empty list without duplicates.')
        if ref.get('default_angle') not in angles: E.append('The default viewing angle must be one of the angles.')
        ht = ref['height_table']
        if not ht: E.append('The height table is empty.')
        ds = [r['distance'] for r in ht]
        if len(set(ds)) != len(ds): E.append('The height table has duplicate distances.')
        if ds != sorted(ds): Wn.append('Height table rows are not in ascending distance order.')
        for r in ht:
            for a in angles:
                v = r['height'].get(str(a))
                if not isinstance(v, (int, float)) or v <= 0: E.append('Height missing or invalid: %g m at %g°.' % (r['distance'], a))
        for a in angles:                              # sanity: taller mounting for a longer distance
            col = [(r['distance'], r['height'].get(str(a))) for r in sorted(ht, key=lambda r: r['distance'])]
            for (d1, h1), (d2, h2) in zip(col, col[1:]):
                if isinstance(h1, (int, float)) and isinstance(h2, (int, float)) and h2 < h1: Wn.append('%g° height drops from %g m (%s) to %g m (%s) – check for a typing error.' % (a, d1, h1, d2, h2))
        rs = ref['lens_ranges']
        if not rs: E.append('Add at least one lens range.')
        for r in rs:
            if not str(r.get('lens', '')).strip(): E.append('A lens range has no lens model.')
            if not (isinstance(r.get('min'), (int, float)) and isinstance(r.get('max'), (int, float))) or r['min'] > r['max']: E.append('Lens range %s–%s is invalid (min must not exceed max).' % (r.get('min'), r.get('max')))
        if not E:
            s = sorted_ranges(ref)
            for a, b in zip(s, s[1:]):
                if b['min'] <= a['max'] + EPS: E.append('Lens ranges overlap: %g–%g m (%s) and %g–%g m (%s).' % (a['min'], a['max'], a['lens'], b['min'], b['max'], b['lens']))
                elif b['min'] - a['max'] > EPS: Wn.append('Gap between %g m and %g m: distances inside the gap are rejected with a message.' % (a['max'], b['min']))
            mode = ref.get('rules', {}).get('fractional_distance', 'ceil')
            if mode not in MODES: E.append('Fractional distance rule must be one of: %s.' % ', '.join(MODES))
            else:
                have = {r['distance'] for r in ht}
                for r in s:
                    for t in range(int(math.floor(r['min'])), int(math.ceil(r['max'])) + 1):
                        if t not in have: Wn.append('No height row for %d m, inside range %g–%g m (%s).' % (t, r['min'], r['max'], r['lens'])); break
        for key, label in (('camera_models', 'camera model'), ('install_types', 'installation type'), ('environments', 'installation environment'), ('vendors', 'camera vendor')):
            if not ref.get(key) or any(not str(x).strip() for x in ref[key]): E.append('Add at least one %s (no blank entries).' % label)
        if ref.get('vendors') and ref.get('default_vendor') not in ref['vendors']: E.append('The default vendor must be in the vendor list.')
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        E.append('The reference data is malformed (%s).' % e)
    return E, Wn
