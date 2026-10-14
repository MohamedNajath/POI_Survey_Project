"""POI survey web app – run:  python app.py   (opens http://localhost:5000)"""
import base64, hashlib, io, os, re, secrets, shutil, socket, sqlite3, subprocess, tempfile, threading, webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from flask import Flask, request, send_file, send_from_directory, jsonify
from generate_report import generate, load_reference
from poi_rules import calc as poi_calc, calc_height

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'template.docx')
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 400 * 1024 * 1024
SOFFICE = shutil.which('soffice') or shutil.which('libreoffice')
DB_PATH = os.path.abspath(os.path.expanduser(os.environ.get(
    'POI_DB_PATH', os.environ.get('POI_AUTH_DB', os.path.join('~', '.poi-survey', 'users.sqlite3')))))

@contextmanager
def database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init_database():
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("""CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            facility TEXT NOT NULL,
            report_number TEXT NOT NULL,
            filename TEXT NOT NULL
        )""")
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(reports)')}
        if 'created_by' in columns:
            conn.execute("""CREATE TABLE reports_unscoped (
                id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                facility TEXT NOT NULL,
                report_number TEXT NOT NULL,
                filename TEXT NOT NULL
            )""")
            conn.execute("""INSERT INTO reports_unscoped
                (id, generated_at, facility, report_number, filename)
                SELECT id, generated_at, facility, report_number, filename FROM reports""")
            conn.execute('DROP TABLE reports')
            conn.execute('ALTER TABLE reports_unscoped RENAME TO reports')

init_database()

def data_url_to_file(url, path):
    head, b64 = url.split(',', 1)
    with open(path, 'wb') as f: f.write(base64.b64decode(b64))

def build(survey, tmp, ref):
    """Validate the survey coming from the browser and turn it into the generator's input."""
    errors = []; fac = survey.get('facility', {}); rep = survey.get('report', {})
    if not fac.get('name', '').strip(): errors.append('Site: facility name is required.')
    if not fac.get('location', '').strip(): errors.append('Site: location is required.')
    if not rep.get('date', '').strip(): errors.append('Site: report date is required.')
    cams_in = survey.get('cameras', [])
    if not cams_in: errors.append('Cameras: add at least one camera.')
    cams = []; built_paths = {}
    by_id = {c.get('id'): c for c in cams_in if isinstance(c, dict) and c.get('id')}
    for i, c in enumerate(cams_in, 1):
        tag = 'Camera %02d' % i
        for key, label in (('location_name', 'location name'), ('distance_m', 'distance'), ('target_area_m', 'target area')):
            if not str(c.get(key, '')).strip(): errors.append('%s: %s is missing.' % (tag, label))
        height = c.get('height_m')
        calc = calc_height(ref, c.get('distance_m'), height)
        if not calc['ok']: errors.append('%s: %s' % (tag, calc['error']))
        source = by_id.get(c.get('photo_source')) if c.get('photo_source') else None
        photos = c.get('photos') or {}
        source_paths = built_paths.get(c.get('photo_source')) if source else None
        if source_paths:
            paths = source_paths
        else:
            paths = {}
        if source and not source_paths:
            photos = {**(source.get('photos') or {}), **photos}
        for kind, label in (('target', 'target area photo'), ('camera', 'camera position photo')):
            if kind in paths:
                continue
            ph = photos.get(kind)
            if not ph or not ph.get('flat'): errors.append('%s: %s is missing.' % (tag, label)); continue
            p = os.path.join(tmp, 'cam%d_%s.jpg' % (i, kind)); data_url_to_file(ph['flat'], p); paths[kind] = p
        try: qty = max(1, int(c.get('qty') or 1))
        except ValueError: qty = 1
        # height_m / lens_model are NOT taken from the browser – generate() recalculates them from distance + angle
        built_paths[c.get('id')] = paths
        cams.append({'location_name': c.get('location_name', '').strip(), 'distance_m': str(c.get('distance_m', '')).strip(),
                     'target_area_m': str(c.get('target_area_m', '')).strip(), 'height_m': height,
                     'camera_model': c.get('camera_model', ''), 'install_type': c.get('install_type', ''), 'environment': c.get('environment', ''),
                     'qty': qty, 'photo_target': paths.get('target', ''), 'photo_camera': paths.get('camera', ''),
                     'photo_page': not bool(source)})
    cfg_in = survey.get('config', {})
    try:
        cfg = {'encoding': cfg_in['encoding'], 'resolution': cfg_in['resolution'], 'fps': int(cfg_in['fps']),
               'bitrate_kbps': int(cfg_in['bitrate_kbps']), 'wdr_day': cfg_in['wdr_day'], 'wdr_night': cfg_in['wdr_night']}
        events_per_day = int(cfg_in.get('events_per_day', 1000))
        event_days = int(cfg_in.get('event_days', 90))
        extra_pct = int(cfg_in.get('extra_storage_pct', 10))
        if events_per_day <= 0 or event_days not in (30, 60, 90) or extra_pct not in (10, 20): raise ValueError()
    except (KeyError, ValueError, TypeError): errors.append('Setup: camera settings are incomplete or contain an invalid storage period/extra percentage.')
    if errors: return None, errors
    fp = survey.get('floor_plan'); fpp = None
    if fp and fp.get('flat'): fpp = os.path.join(tmp, 'floorplan.jpg'); data_url_to_file(fp['flat'], fpp)
    g = lambda d, k: (survey.get(d) or {}).get(k, '')
    return {
        'report': {'date': rep['date'], 'revision': rep.get('revision', '0'), 'number': rep.get('number', '')},
        'facility': {'name': fac['name'], 'location': fac['location'], 'category': fac.get('category', ''), 'type': fac.get('type', 'as_build')},
        'client': {k: g('client', k) for k in ('name', 'mobile', 'designation', 'email')},
        'contractor': {k: g('contractor', k) for k in ('company', 'name', 'mobile', 'designation', 'email', 'certified_engineer', 'certified_technician')},
        'config': cfg, 'storage_constants': {'events_per_day': events_per_day, 'event_days': event_days, 'extra_pct': extra_pct},
        'vendor': survey.get('vendor', 'DAHUA'), 'cameras': cams, 'author': survey.get('author', ''),
        'nvr': [{'device_type': d.get('device_type', ''), 'model': d.get('model', ''), 'description': d.get('description', ''), 'qty': d.get('qty', 1)}
                for d in survey.get('nvr', [])],
        'verification': {'items': ['verified'] * 4 + ['pending'] * 2, 'stamp_image': None}, 'floor_plan': fpp,
    }, []

def make_docx(survey, tmp, include_letterhead=True):
    ref = current_reference()
    data, errors = build(survey, tmp, ref)
    if errors: return None, errors
    out = os.path.join(tmp, 'report.docx'); generate(TEMPLATE, data, out, tmp, ref=ref, include_letterhead=include_letterhead)
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', 'POI_Survey_%s_REV%s' % (data['facility']['name'], data['report']['revision'])).strip('_')
    if not include_letterhead: name += '_No_Letterhead'
    return (out, name), []

@app.get('/')
def index(): return send_from_directory(app.static_folder, 'index.html')

def current_reference():
    return load_reference(HERE)  # Use the local override when present, otherwise the shipped default.

@app.get('/api/catalog')
def catalog(): return jsonify(current_reference())

@app.post('/api/calc')
def api_calc():
    body = request.get_json(force=True); ref = current_reference()
    return jsonify(poi_calc(ref, body.get('distance_m'), body.get('viewing_angle', ref.get('default_angle'))))

@app.get('/api/capabilities')
def caps(): return jsonify(preview=bool(SOFFICE))

@app.get('/api/reports')
def list_reports():
    with database() as conn:
        rows = conn.execute("""SELECT id, generated_at, facility, report_number, filename
                               FROM reports ORDER BY generated_at DESC""").fetchall()
    return jsonify(reports=[dict(row) for row in rows])

@app.post('/api/reports/import')
def import_legacy_reports():
    body = request.get_json(silent=True) or {}
    reports = body.get('reports')
    if not isinstance(reports, list) or len(reports) > 1000:
        return jsonify(error='Report history must be a list of no more than 1000 entries.'), 400
    imported_at = datetime.now(timezone.utc)
    inserted = 0
    with database() as conn:
        for index, report in enumerate(reports):
            if not isinstance(report, dict):
                continue
            try:
                generated_at = datetime.fromtimestamp(int(report.get('generatedAt')) / 1000, timezone.utc)
            except (TypeError, ValueError, OSError, OverflowError):
                generated_at = imported_at
            legacy_id = str(report.get('id') or index)
            report_id = 'legacy-' + hashlib.sha256(legacy_id.encode('utf-8')).hexdigest()
            cursor = conn.execute("""INSERT OR IGNORE INTO reports
                (id, generated_at, facility, report_number, filename)
                VALUES (?, ?, ?, ?, '')""",
                (report_id, generated_at.isoformat(),
                 str(report.get('facility') or 'Untitled survey')[:200],
                 str(report.get('reportNumber') or '')[:100]))
            inserted += cursor.rowcount
    return jsonify(ok=True, imported=inserted)

@app.post('/api/reports/delete')
def delete_reports():
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
        return jsonify(error='Select at least one report to delete.'), 400
    ids = list(set(ids))
    if len(ids) > 500:
        return jsonify(error='Select no more than 500 reports at a time.'), 400
    with database() as conn:
        placeholders = ','.join('?' for _ in ids)
        cursor = conn.execute(f"DELETE FROM reports WHERE id IN ({placeholders})", ids)
    return jsonify(ok=True, deleted=cursor.rowcount)

@app.post('/api/report')
def report():
    tmp = tempfile.mkdtemp()
    try:
        include_letterhead = request.args.get('letterhead', '1') != '0'
        res, errors = make_docx(request.get_json(force=True), tmp, include_letterhead)
        if errors: return jsonify(errors=errors), 400
        out, name = res; buf = io.BytesIO(open(out, 'rb').read())
        survey = request.get_json(silent=True) or {}
        facility = str((survey.get('facility') or {}).get('name', '')).strip()
        report_info = survey.get('report') or {}
        with database() as conn:
            conn.execute("INSERT INTO reports (id, generated_at, facility, report_number, filename) VALUES (?, ?, ?, ?, ?)",
                         (secrets.token_urlsafe(18), datetime.now(timezone.utc).isoformat(), facility,
                          str(report_info.get('number', '')), name + '.docx'))
    except Exception as e:
        app.logger.exception('report failed'); return jsonify(errors=['Report generation failed: %s' % e]), 500
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return send_file(buf, as_attachment=True, download_name=name + '.docx',
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

@app.post('/api/preview')
def preview():
    if not SOFFICE: return jsonify(errors=['Preview needs LibreOffice installed on this computer.']), 501
    tmp = tempfile.mkdtemp()
    try:
        include_letterhead = request.args.get('letterhead', '1') != '0'
        res, errors = make_docx(request.get_json(force=True), tmp, include_letterhead)
        if errors: return jsonify(errors=errors), 400
        subprocess.run([SOFFICE, '--headless', '--convert-to', 'pdf', '--outdir', tmp, res[0]], check=True, capture_output=True, timeout=120)
        buf = io.BytesIO(open(os.path.join(tmp, 'report.pdf'), 'rb').read())
    except Exception as e:
        app.logger.exception('preview failed'); return jsonify(errors=['Preview failed: %s' % e]), 500
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return send_file(buf, mimetype='application/pdf')

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1)); ip = s.getsockname()[0]; s.close(); return ip
    except OSError: return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000)); ip = lan_ip()
    print('\n  POI survey app is running.\n  On this computer:  http://localhost:%d' % port)
    if ip: print('  On your phone (same Wi-Fi):  http://%s:%d' % (ip, port))
    print('  Press Ctrl+C to stop.\n')
    if not os.environ.get('NO_BROWSER'): threading.Timer(1.0, lambda: webbrowser.open('http://localhost:%d' % port)).start()
    app.run(host='0.0.0.0', port=port, threaded=True)
