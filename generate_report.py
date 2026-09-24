"""
Fill template.docx with survey data -> editable .docx.
Usage: python generate_report.py template.docx survey.json out.docx
"""
import sys, os, io, json, copy, zipfile, tempfile, shutil, datetime
from lxml import etree
from PIL import Image
from docx_xml import *
from poi_rules import calc as poi_calc, calc_height, validate_reference

def load_reference(base_dir='.'):
    for p in (os.path.join(base_dir, 'reference.json'), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reference.default.json')):
        if os.path.exists(p):
            ref = json.load(open(p, encoding='utf-8'))
            errs, _ = validate_reference(ref)
            if errs: raise ValueError('POI reference table is invalid: ' + '; '.join(errs))
            return ref
    raise FileNotFoundError('No reference.json / reference.default.json found.')

BOX_W, BOX_H = 4909385, 3682038          # photo box used by the sample (4:3, ~13.6 cm wide)
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

# ---------------------------------------------------------------- storage maths (constants are configurable)
STORAGE_DEFAULTS = dict(
    event_mb_at_4096=21.20,        # MB per 40 s event at 4096 kbps  (source: Dahua calculator - CONFIRM)
    cont_120d_tb_at_4096=5.24,     # TB per camera, 120 days continuous at 4096 kbps (CONFIRM)
    events_per_day=1000, image_mb=1.0, event_days=90, extra_pct=10)

def storage(cfg, n, k=None):
    k = {**STORAGE_DEFAULTS, **(k or {})}; s = cfg['bitrate_kbps'] / 4096.0
    ev_mb = k['event_mb_at_4096'] * s
    day_gb = ev_mb * k['events_per_day'] / 1024
    ev_tb = day_gb * k['event_days'] * n / 1024
    img_day_gb = k['events_per_day'] * k['image_mb'] / 1024
    img_90_gb = img_day_gb * k['event_days'] * n
    total = ev_tb + img_90_gb / 1024
    f = lambda x: '%.2f' % x
    return {'STG_ENCODING': cfg['encoding'], 'STG_BITRATE_TYPE': 'CBR', 'STG_RESOLUTION': cfg['resolution'],
            'STG_FPS': str(cfg['fps']), 'STG_BITRATE_MBPS': '%g' % round(cfg['bitrate_kbps'] / 1024, 2), 'STG_CAMERAS': str(n),
            'STG_120D_PER_CAM_TB': f(k['cont_120d_tb_at_4096'] * s), 'STG_EVENT_MB': f(ev_mb),
            'STG_EVENTS_PER_DAY': str(k['events_per_day']), 'STG_DAY_EVENT_GB': f(day_gb), 'STG_90D_EVENT_TB': f(ev_tb),
            'STG_IMG_MB': '%g' % k['image_mb'], 'STG_IMG_GB_DAY': f(img_day_gb), 'STG_90D_IMG_GB': '%d' % round(img_90_gb),
            'STG_TOTAL_TB': f(total), 'STG_EXTRA_PCT': str(k['extra_pct']),
            'STG_TOTAL_EXTRA_TB': f(total * (1 + k['extra_pct'] / 100))}

# ---------------------------------------------------------------- helpers

def build_poi_table(ref):
    """Colour-coded POI Camera Installation Table (SN, Distance, Height per angle, Lens), matching the source image."""
    ANGLE_FILL = {'6': '70AD47', '7': 'FFC000', '8': 'FF0000'}
    def tc(text, w, bold=False, fill=None, span=1, rspan=False, vmerge=None, sz=18, color='000000', align='center'):
        shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill if fill else ''
        sp = '<w:gridSpan w:val="%d"/>' % span if span > 1 else ''
        vm = '<w:vMerge w:val="restart"/>' if vmerge == 'restart' else '<w:vMerge/>' if vmerge == 'continue' else ''
        rp = '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>' + ('<w:b/>' if bold else '') + '<w:color w:val="%s"/><w:sz w:val="%d"/>' % (color, sz)
        para = '<w:p/>' if vmerge == 'continue' else ('<w:p><w:pPr><w:spacing w:before="20" w:after="20"/><w:jc w:val="%s"/></w:pPr>'
               '<w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:p>') % (align, rp, text)
        return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s%s<w:tcBorders><w:top w:val="single" w:sz="4" w:color="808080"/><w:left w:val="single" w:sz="4" w:color="808080"/>'
                '<w:bottom w:val="single" w:sz="4" w:color="808080"/><w:right w:val="single" w:sz="4" w:color="808080"/></w:tcBorders>%s<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>'
                ) % (w, sp, vm, shd, para)
    SN, DIST, HGT, LENS = 700, 1400, 1300, 3200
    grid = '<w:tblGrid><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/></w:tblGrid>' % (SN, DIST, HGT, HGT, HGT, LENS)
    xml = '<w:tbl xmlns:w="%s"><w:tblPr><w:tblW w:w="9700" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>' \
          '<w:top w:val="single" w:sz="4" w:color="808080"/><w:left w:val="single" w:sz="4" w:color="808080"/><w:bottom w:val="single" w:sz="4" w:color="808080"/>' \
          '<w:right w:val="single" w:sz="4" w:color="808080"/><w:insideH w:val="single" w:sz="4" w:color="808080"/><w:insideV w:val="single" w:sz="4" w:color="808080"/></w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>' % NS['w']
    xml += grid
    xml += '<w:tr>%s%s%s' % (tc('SN', SN, True, 'D9D9D9', 1, vmerge='restart'), tc('Distance (m)', DIST, True, 'D9D9D9', 1, vmerge='restart'), tc('Height (m)', HGT * 3, True, 'D9D9D9', 3))
    xml += tc('Lens', LENS, True, 'D9D9D9', 1, vmerge='restart') + '</w:tr>'
    xml += '<w:tr>%s%s' % (tc('', SN, vmerge='continue'), tc('', DIST, vmerge='continue'))
    xml += ''.join(tc('%g\u00b0' % a, HGT, True, ANGLE_FILL.get(str(int(a)), 'D9D9D9')) for a in ref['angles'])
    xml += tc('', LENS, vmerge='continue') + '</w:tr>'
    rows = sorted(ref['height_table'], key=lambda r: r['distance']); ranges = sorted(ref['lens_ranges'], key=lambda r: r['min'])
    def lens_span(d):
        for r in ranges:
            if r['min'] - 1e-9 <= d <= r['max'] + 1e-9: return '%g M to %g M\n%s' % (r['min'], r['max'], r['lens'])
        return ''
    lens_start = {}
    for r in rows:
        hit = next((rg for rg in ranges if rg['min'] - 1e-9 <= r['distance'] <= rg['max'] + 1e-9), None)
        if hit and id(hit) not in lens_start: lens_start[id(hit)] = r['distance']
    for r in rows:
        i = int(r['distance'])
        hit = next((rg for rg in ranges if rg['min'] - 1e-9 <= r['distance'] <= rg['max'] + 1e-9), None)
        xml += '<w:tr>%s%s' % (tc(str(i) if r['distance'] > 0 else '', SN), tc('%g' % r['distance'], DIST, True))
        for a in ref['angles']:
            v = r['height'].get(str(int(a)) if float(a).is_integer() else str(a))
            xml += tc(('%g' % v) if v is not None else '', HGT, True, ANGLE_FILL.get(str(int(a)), None), color='000000' if ANGLE_FILL.get(str(int(a))) in ('FFC000',) else 'FFFFFF' if ANGLE_FILL.get(str(int(a))) else '000000')
        if hit and lens_start.get(id(hit)) == r['distance']:
            span_rows = sum(1 for rr in rows if hit['min'] - 1e-9 <= rr['distance'] <= hit['max'] + 1e-9)
            xml += tc('(%g M to %g M)\n%s' % (hit['min'], hit['max'], hit['lens']), LENS, True, vmerge='restart')
        elif hit: xml += tc('', LENS, vmerge='continue')
        else: xml += tc('', LENS)
        xml += '</w:tr>'
    foot = ref.get('poi_table_footnote', '')
    if foot: xml += '<w:tr>%s</w:tr>' % tc(foot, SN + DIST + HGT * 3 + LENS, True, 'F2F2F2', span=6, align='center')
    xml += '</w:tbl>'
    fixed = xml.replace('\\n', '</w:t></w:r></w:p><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:b/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">')
    return etree.fromstring(fixed)

def fill(el, m):
    for t in el.iter(W('t')):
        if t.text and '{{' in t.text:
            s = t.text
            for k, v in m.items(): s = s.replace('{{%s}}' % k, str(v))
            set_t(t, s)

class Media:
    def __init__(self, root, rels_tree):
        self.root, self.rels, self.n = root, rels_tree, 0
    def add(self, path_or_bytes, max_px=1800):
        im = Image.open(path_or_bytes if isinstance(path_or_bytes, str) else io.BytesIO(path_or_bytes)).convert('RGB')
        im.thumbnail((max_px, max_px)); self.n += 1
        name = 'gen_img%d.jpeg' % self.n
        im.save(os.path.join(self.root, 'word/media', name), 'JPEG', quality=90)
        rid = 'rIdGen%d' % self.n
        etree.SubElement(self.rels.getroot(), '{%s}Relationship' % REL, Id=rid,
                         Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', Target='media/' + name)
        return rid, im.size

def swap_picture(docpr, media, src, alt):
    """Point the inline picture that owns `docpr` at a new image, keep it inside the 4:3 photo box."""
    inline = docpr.getparent(); rid, (w, h) = media.add(src)
    sc = min(BOX_W / w, BOX_H / h); cx, cy = int(w * sc), int(h * sc)
    inline.find(q('wp:extent')).set('cx', str(cx)); inline.find(q('wp:extent')).set('cy', str(cy))
    for ext in inline.iterfind('.//' + q('a:xfrm') + '/' + q('a:ext')): ext.set('cx', str(cx)); ext.set('cy', str(cy))
    inline.find('.//' + q('a:blip')).set(q('r:embed'), rid); docpr.set('descr', alt)

def find_docpr(root, token):
    return next((d for d in root.iter(q('wp:docPr')) if d.get('descr') == token), None)

def loop_row(tbl_root, token):
    for tr in tbl_root.iter(W('tr')):
        if token in ''.join(tr.itertext()): return tr

# ---------------------------------------------------------------- main
def generate(template, data, out, base_dir='.', ref=None):
    ref = ref or load_reference(base_dir)
    calc_errors = []
    for i, c in enumerate(data['cameras'], 1):
        r = calc_height(ref, c.get('distance_m'), c.get('height_m'))
        if not r['ok']: calc_errors.append('Camera %02d (%s): %s' % (i, c.get('location_name', '?'), r['error'])); continue
        c['height_m'] = ('%g' % r['height']); c['lens_model'] = r['lens']; c['_table_distance'] = r['table_distance']
    if calc_errors: raise ValueError('POI reference calculation failed:\n' + '\n'.join(calc_errors))

    tmp = tempfile.mkdtemp(); zipfile.ZipFile(template).extractall(tmp)
    dp = os.path.join(tmp, 'word/document.xml'); hp = os.path.join(tmp, 'word/header1.xml')
    rp = os.path.join(tmp, 'word/_rels/document.xml.rels')
    doc, hdr, rels = etree.parse(dp), etree.parse(hp), etree.parse(rp); root = doc.getroot(); body = root.find(W('body'))
    media = Media(tmp, rels); P = lambda s: os.path.join(base_dir, s)
    cams, fac, cl, co, cfg = data['cameras'], data['facility'], data['client'], data['contractor'], data['config']
    n = sum(int(c.get('qty', 1)) for c in cams)          # total = sum of quantities, never typed by hand

    # -- header
    fill(hdr.getroot(), {'REPORT_DATE': data['report']['date'], 'REVISION': data['report']['revision']})

    # -- type checkboxes -> Wingdings symbols
    for t in list(root.iter(W('t'))):
        if t.text in ('{{TYPE_ASBUILT}}', '{{TYPE_NEW}}'):
            checked = (fac['type'] == 'as_build') == (t.text == '{{TYPE_ASBUILT}}')
            r = t.getparent(); r.remove(t)
            if checked:
                rpr = r.find(W('rPr'));  c = etree.SubElement(rpr, W('color')); c.set(W('val'), 'FF0000')
            sym = etree.SubElement(r, W('sym')); sym.set(W('font'), 'Wingdings'); sym.set(W('char'), 'F0FE' if checked else 'F0A8')

    # -- camera table + NVR table loop rows
    row = loop_row(root, '{{LOCATION_NAME}}'); prev = row
    for i, c in enumerate(cams, 1):
        nr = copy.deepcopy(row)
        fill(nr, {'SN': i, 'LOCATION_NAME': c['location_name'] + (' (×%d)' % int(c['qty']) if int(c.get('qty', 1)) > 1 else ''), 'HEIGHT': c['height_m'], 'DISTANCE': c['distance_m'],
                  'TARGET_AREA': c['target_area_m'], 'CAMERA_MODEL': c['camera_model'], 'LENS_MODEL': c['lens_model'],
                  'INSTALL_TYPE': c['install_type'], 'INSTALL_ENV': c['environment']})
        prev.addnext(nr); prev = nr
    row.getparent().remove(row)
    row = loop_row(root, '{{DEVICE_TYPE}}'); prev = row
    for i, d in enumerate(data['nvr'], 1):
        nr = copy.deepcopy(row)
        fill(nr, {'SN': i, 'DEVICE_TYPE': d['device_type'], 'MODEL': d['model'], 'DESCRIPTION': d['description'], 'QTY': d['qty']})
        prev.addnext(nr); prev = nr
    row.getparent().remove(row)

    # -- verification block: ticks/crosses by status, stamp only if an issued stamp image is supplied
    tick = cross = None
    for r in rels.getroot():
        if r.get('Target') == 'media/image2.png': tick = r.get('Id')
        if r.get('Target') == 'media/image4.png': cross = r.get('Id')
    for i, st in enumerate(data['verification']['items'], 1):
        dpr = find_docpr(root, '{{V%d}}' % i)
        dpr.getparent().find('.//' + q('a:blip')).set(q('r:embed'), tick if st == 'verified' else cross); dpr.set('descr', 'verified' if st == 'verified' else 'pending')
    sp = find_docpr(root, '{{VERIFICATION_STAMP}}'); vs = data['verification'].get('stamp_image')
    if vs: swap_picture(sp, media, P(vs), 'Verification stamp'); 
    else:
        run = next(a for a in sp.iterancestors(W('r'))); par = run.getparent(); par.remove(run)
        r = etree.SubElement(par, W('r')); rpr = etree.SubElement(r, W('rPr')); etree.SubElement(rpr, W('b'))
        set_t(etree.SubElement(r, W('t')), 'Pending verification by Dahua POI Team')

    # -- floor plan
    fp = next(p for p in body.iter(W('p')) if ptext(p) == '{{FLOOR_PLAN}}')
    if data.get('floor_plan'):
        run = fp[0]; run.remove(run.find(W('t')))
        rid, (w, h) = media.add(P(data['floor_plan']), 2400); mw, mh = 6300000, 8200000; sc = min(mw / w, mh / h); cx, cy = int(w * sc), int(h * sc)
        run.append(etree.fromstring(
          '<w:drawing xmlns:w="%s" xmlns:wp="%s" xmlns:a="%s" xmlns:pic="%s" xmlns:r="%s"><wp:inline distT="0" distB="0" distL="0" distR="0">'
          '<wp:extent cx="%d" cy="%d"/><wp:docPr id="900" name="Floor plan" descr="Floor key plan"/><a:graphic><a:graphicData uri="%s">'
          '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="floorplan"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
          '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>'
          % (NS['w'], NS['wp'], NS['a'], NS['pic'], NS['r'], cx, cy, NS['pic'], rid, cx, cy)))
        pp = fp.find(W('pPr')) or etree.Element(W('pPr')); fp.insert(0, pp); etree.SubElement(pp, W('jc')).set(W('val'), 'center')
    else: body.remove(fp)

    # -- per-camera photo pages
    ms = next(p for p in body.iter(W('p')) if ptext(p) == '{{#CAMERA_PAGES}}'); me = next(p for p in body.iter(W('p')) if ptext(p) == '{{/CAMERA_PAGES}}')
    block, e = [], ms.getnext()
    while e is not me: block.append(e); e = e.getnext()
    anchor = me
    for i, c in enumerate(cams):
        if not c.get('photo_page', True):
            continue
        m = {'SEC_PREFIX': '05: ' if i == 0 else '', 'LOCATION_NAME': c['location_name'], 'HEIGHT': c['height_m'],
             'DISTANCE': c['distance_m'], 'INSTALL_TYPE': c['install_type']}
        for b in block:
            nb = copy.deepcopy(b); fill(nb, m)
            for tok, key, alt in (('{{IMG_TARGET}}', 'photo_target', 'Target area'), ('{{IMG_CAMERA}}', 'photo_camera', 'Camera location')):
                d = find_docpr(nb, tok)
                if d is not None: swap_picture(d, media, P(c[key]), '%s – %s' % (alt, c['location_name']))
            anchor.addprevious(nb)
    for b in block: body.remove(b)
    body.remove(ms); body.remove(me)

    # -- POI Camera Installation Table (reference section)
    poi_marker = next((p for p in body.iter(W('t')) if p.text == '{{POI_TABLE}}'), None)
    if poi_marker is not None:
        holder = next(a for a in poi_marker.iterancestors(W('p')))
        if ref.get('report_options', {}).get('include_poi_table', True):
            holder.addprevious(build_poi_table(ref)); holder.getparent().remove(holder)
        else:
            note = holder.getprevious(); head = note.getprevious() if note is not None else None
            for e in (holder, note, head if head is not None and 'POI Camera Installation Table' in ptext(head) else None):
                if e is not None and e.getparent() is not None: e.getparent().remove(e)

    # -- remaining scalar tokens (page 1, config table, totals, storage table)
    m = {'FACILITY_NAME': fac['name'], 'LOCATION': fac['location'], 'CATEGORY': fac['category'], 'REPORT_NO': data['report']['number'],
         'CLIENT_NAME': cl['name'], 'CLIENT_MOBILE': cl['mobile'], 'CLIENT_DESIGNATION': cl['designation'], 'CLIENT_EMAIL': cl['email'],
         'CONTRACTOR': co['company'], 'CONTRACTOR_NAME': co['name'], 'CONTRACTOR_MOBILE': co['mobile'],
         'CONTRACTOR_DESIGNATION': co['designation'], 'CONTRACTOR_EMAIL': co['email'],
         'CERTIFIED_ENGINEER': co['certified_engineer'], 'CERTIFIED_TECHNICIAN': co['certified_technician'],
         'ENCODING': cfg['encoding'], 'RESOLUTION': cfg['resolution'], 'FPS': cfg['fps'], 'BITRATE_KBPS': cfg['bitrate_kbps'],
         'WDR_DAY': cfg['wdr_day'], 'WDR_NIGHT': cfg['wdr_night'], 'TOTAL_CAMERAS': n, 'CAMERA_VENDOR': data['vendor']}
    m.update(storage(cfg, n, data.get('storage_constants')))
    fill(root, m)
    left = [t.text for t in root.iter(W('t')) if t.text and '{{' in t.text]; assert not left, left

    # unique drawing ids, core properties
    for i, d in enumerate(root.iter(q('wp:docPr')), 1): d.set('id', str(i))
    doc.write(dp, xml_declaration=True, encoding='UTF-8', standalone=True)
    hdr.write(hp, xml_declaration=True, encoding='UTF-8', standalone=True); rels.write(rp, xml_declaration=True, encoding='UTF-8', standalone=True)
    cp = os.path.join(tmp, 'docProps/core.xml'); core = etree.parse(cp); now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    C = {'dc': 'http://purl.org/dc/elements/1.1/', 'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties', 'dcterms': 'http://purl.org/dc/terms/'}
    for path, val in (('dc:title', 'POI Survey Report – %s' % fac['name']), ('dc:creator', data.get('author', '')), ('cp:lastModifiedBy', data.get('author', '')), ('dcterms:modified', now), ('dcterms:created', now)):
        for el in core.xpath('//' + path, namespaces=C): el.text = val
    for el in core.xpath('//cp:lastPrinted', namespaces=C): el.getparent().remove(el)
    core.write(cp, xml_declaration=True, encoding='UTF-8', standalone=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(tmp, '[Content_Types].xml'), '[Content_Types].xml')
        for r_, _, fs in os.walk(tmp):
            for f in fs:
                full = os.path.join(r_, f); arc = os.path.relpath(full, tmp)
                if arc != '[Content_Types].xml': z.write(full, arc)
    shutil.rmtree(tmp); return n

if __name__ == '__main__':
    tpl, js, out = sys.argv[1:4]
    print('cameras:', generate(tpl, json.load(open(js)), out, os.path.dirname(os.path.abspath(js))), '->', out)
