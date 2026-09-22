"""POI survey web app – run:  python app.py   (opens http://localhost:5000)"""
import base64, io, json, os, re, shutil, socket, subprocess, tempfile, threading, webbrowser
from flask import Flask, request, send_file, send_from_directory, jsonify
from generate_report import generate, load_reference
from poi_rules import calc as poi_calc, validate_reference

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'template.docx')
REF_PATH = os.path.join(HERE, 'reference.json')
REF_DEFAULT = os.path.join(HERE, 'reference.default.json')
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 400 * 1024 * 1024
SOFFICE = shutil.which('soffice') or shutil.which('libreoffice')

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
    cams = []
    for i, c in enumerate(cams_in, 1):
        tag = 'Camera %02d' % i
        for key, label in (('location_name', 'location name'), ('distance_m', 'distance'), ('target_area_m', 'target area')):
            if not str(c.get(key, '')).strip(): errors.append('%s: %s is missing.' % (tag, label))
        angle = c.get('viewing_angle', ref.get('default_angle'))
        calc = poi_calc(ref, c.get('distance_m'), angle)
        if not calc['ok']: errors.append('%s: %s' % (tag, calc['error']))
        photos = c.get('photos') or {}; paths = {}
        for kind, label in (('target', 'target area photo'), ('camera', 'camera position photo')):
            ph = photos.get(kind)
            if not ph or not ph.get('flat'): errors.append('%s: %s is missing.' % (tag, label)); continue
            p = os.path.join(tmp, 'cam%d_%s.jpg' % (i, kind)); data_url_to_file(ph['flat'], p); paths[kind] = p
        try: qty = max(1, int(c.get('qty') or 1))
        except ValueError: qty = 1
        # height_m / lens_model are NOT taken from the browser – generate() recalculates them from distance + angle
        cams.append({'location_name': c.get('location_name', '').strip(), 'distance_m': str(c.get('distance_m', '')).strip(),
                     'target_area_m': str(c.get('target_area_m', '')).strip(), 'viewing_angle': angle,
                     'camera_model': c.get('camera_model', ''), 'install_type': c.get('install_type', ''), 'environment': c.get('environment', ''),
                     'qty': qty, 'photo_target': paths.get('target', ''), 'photo_camera': paths.get('camera', '')})
    cfg_in = survey.get('config', {})
    try:
        cfg = {'encoding': cfg_in['encoding'], 'resolution': cfg_in['resolution'], 'fps': int(cfg_in['fps']),
               'bitrate_kbps': int(cfg_in['bitrate_kbps']), 'wdr_day': cfg_in['wdr_day'], 'wdr_night': cfg_in['wdr_night']}
        events_per_day = int(cfg_in.get('events_per_day', 1000))
        if events_per_day <= 0: raise ValueError()
    except (KeyError, ValueError, TypeError): errors.append('Setup: camera settings are incomplete (fps, bitrate, and events per day must be valid positive numbers).')
    if errors: return None, errors
    fp = survey.get('floor_plan'); fpp = None
    if fp and fp.get('flat'): fpp = os.path.join(tmp, 'floorplan.jpg'); data_url_to_file(fp['flat'], fpp)
    g = lambda d, k: (survey.get(d) or {}).get(k, '')
    return {
        'report': {'date': rep['date'], 'revision': rep.get('revision', '0'), 'number': rep.get('number', '')},
        'facility': {'name': fac['name'], 'location': fac['location'], 'category': fac.get('category', ''), 'type': fac.get('type', 'as_build')},
        'client': {k: g('client', k) for k in ('name', 'mobile', 'designation', 'email')},
        'contractor': {k: g('contractor', k) for k in ('company', 'name', 'mobile', 'designation', 'email', 'certified_engineer', 'certified_technician')},
        'config': cfg, 'storage_constants': {'events_per_day': events_per_day},
        'vendor': survey.get('vendor', 'DAHUA'), 'cameras': cams, 'author': survey.get('author', ''),
        'nvr': [{'device_type': d.get('device_type', ''), 'model': d.get('model', ''), 'description': d.get('description', ''), 'qty': d.get('qty', 1)}
                for d in survey.get('nvr', [])],
        'verification': {'items': ['pending'] * 6, 'stamp_image': None}, 'floor_plan': fpp,
    }, []

def make_docx(survey, tmp):
    ref = current_reference()
    data, errors = build(survey, tmp, ref)
    if errors: return None, errors
    out = os.path.join(tmp, 'report.docx'); generate(TEMPLATE, data, out, tmp, ref=ref)
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', 'POI_Survey_%s_REV%s' % (data['facility']['name'], data['report']['revision'])).strip('_')
    return (out, name), []

@app.get('/')
def index(): return send_from_directory(app.static_folder, 'index.html')

def current_reference():
    return load_reference(HERE)  # reference.json if an admin has saved one, else the shipped default

@app.get('/api/catalog')
def catalog(): return jsonify(current_reference())

ADMIN_PIN = os.environ.get('ADMIN_PIN', '').strip()

def admin_ok():
    return not ADMIN_PIN or request.headers.get('X-Admin-Pin', '') == ADMIN_PIN

@app.get('/api/reference')
def get_reference(): return jsonify(current_reference())

@app.get('/api/admin/needs-pin')
def needs_pin(): return jsonify(needs_pin=bool(ADMIN_PIN))

@app.post('/api/reference')
def save_reference():
    if not admin_ok(): return jsonify(errors=['Wrong admin PIN.']), 401
    ref = request.get_json(force=True); errs, warnings = validate_reference(ref)
    if errs: return jsonify(errors=errs, warnings=warnings), 400
    ref['updated'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    json.dump(ref, open(REF_PATH, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return jsonify(ok=True, warnings=warnings)

@app.post('/api/reference/reset')
def reset_reference():
    if not admin_ok(): return jsonify(errors=['Wrong admin PIN.']), 401
    if os.path.exists(REF_PATH): os.remove(REF_PATH)
    return jsonify(ok=True)

@app.post('/api/calc')
def api_calc():
    body = request.get_json(force=True); ref = current_reference()
    return jsonify(poi_calc(ref, body.get('distance_m'), body.get('viewing_angle', ref.get('default_angle'))))

@app.get('/api/capabilities')
def caps(): return jsonify(preview=bool(SOFFICE))

@app.post('/api/report')
def report():
    tmp = tempfile.mkdtemp()
    try:
        res, errors = make_docx(request.get_json(force=True), tmp)
        if errors: return jsonify(errors=errors), 400
        out, name = res; buf = io.BytesIO(open(out, 'rb').read())
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
        res, errors = make_docx(request.get_json(force=True), tmp)
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
