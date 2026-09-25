"""
One-off script: turns the MOI sample report (.docx) into a placeholder template.
Everything the app fills is a {{TOKEN}}; everything else stays byte-for-byte from the original.
Usage: python build_template.py sample.docx template.docx
"""
import sys, zipfile, shutil, tempfile, os, copy, subprocess
from lxml import etree
from docx_xml import *

src, dst = sys.argv[1], sys.argv[2]
tmp = tempfile.mkdtemp(); zipfile.ZipFile(src).extractall(tmp)
# strip symlink entries from untrusted input, coalesce fragmented runs
for root, dirs, files in os.walk(tmp):
    for f in files:
        pth = os.path.join(root, f)
        if os.path.islink(pth): os.unlink(pth)
subprocess.run(['python3', '/mnt/skills/public/docx/scripts/merge_runs.py', tmp], check=True, capture_output=True)

doc_path = os.path.join(tmp, 'word/document.xml'); hdr_path = os.path.join(tmp, 'word/header1.xml')
doc = etree.parse(doc_path); body = doc.getroot().find(W('body'))
T = body.findall(W('tbl'))

# ---- Page 1: facility / client / contractor tables ------------------------------------------------
t0 = T[0]
for (r, c, tok) in [(0,1,'FACILITY_NAME'),(0,3,'REPORT_NO'),(1,1,'LOCATION'),(1,3,'CATEGORY'),
                    (3,2,'CLIENT_NAME'),(3,4,'CLIENT_MOBILE'),(4,2,'CLIENT_DESIGNATION'),(4,4,'CLIENT_EMAIL'),
                    (6,1,'CONTRACTOR'),(7,2,'CONTRACTOR_NAME'),(7,4,'CONTRACTOR_MOBILE'),
                    (8,2,'CONTRACTOR_DESIGNATION'),(8,4,'CONTRACTOR_EMAIL'),
                    (9,2,'CERTIFIED_ENGINEER'),(9,4,'CERTIFIED_TECHNICIAN')]:
    set_cell_text(t0, r, c, '{{%s}}' % tok)
# Type checkboxes: rebuild the paragraph, generator turns the tokens into Wingdings check symbols
p = cell(t0, 1, 5).findall(W('p'))[0]
rpr = copy.deepcopy(xp(p, './/w:r/w:rPr')[0])
for r in p.findall(W('r')): p.remove(r)
for txt in ['    ', '{{TYPE_ASBUILT}}', ' As-Build  ', '{{TYPE_NEW}}', ' New']:
    r = etree.SubElement(p, W('r')); r.append(copy.deepcopy(rpr)); set_t(etree.SubElement(r, W('t')), txt)

# ---- Camera configuration table ------------------------------------------------------------------
t1 = T[1]; c0, c1 = [c.findall(W('p')) for c in t1.find(W('tr')).findall(W('tc'))]
replace_in_paragraph(c0[0], 'H.264', '{{ENCODING}}')
replace_in_paragraph(c0[1], '2560x1440p', '{{RESOLUTION}}')
replace_in_paragraph(c0[2], '25', '{{FPS}}')
replace_in_paragraph(c1[0], '4096', '{{BITRATE_KBPS}}')
replace_in_paragraph(c1[1], 'Day – ON', 'Day – {{WDR_DAY}}')
replace_in_paragraph(c1[2], 'OFF', '{{WDR_NIGHT}}')

# ---- 01 Camera table (loop row) --------------------------------------------------------------------
t2 = T[2]
for c, tok in enumerate(['SN','LOCATION_NAME','HEIGHT','DISTANCE','TARGET_AREA','CAMERA_MODEL','LENS_MODEL','INSTALL_TYPE','INSTALL_ENV']):
    set_cell_text(t2, 2, c, '{{%s}}' % tok)
set_cell_text(t2, 3, 2, '{{TOTAL_CAMERAS}}'); set_cell_text(t2, 3, 4, '{{CAMERA_VENDOR}}')

# ---- 02 NVR table (loop row) -----------------------------------------------------------------------
t3 = T[3]
for c, tok in enumerate(['SN','DEVICE_TYPE','MODEL','DESCRIPTION','QTY']):
    set_cell_text(t3, 1, c, '{{%s}}' % tok)
t3.remove(t3.findall(W('tr'))[2])

# ---- Verification table: pictures become addressable through alt-text --------------------------------
t4 = T[4]
for i in range(1, 7):
    pics = xp(cell(t4, i, 2), './/wp:docPr')
    pics[0].set('descr', '{{V%d}}' % i)
stamp = xp(cell(t4, 1, 3), './/wp:docPr'); stamp[0].set('descr', '{{VERIFICATION_STAMP}}')

# ---- Native storage-calculation table replaces the pasted picture ---------------------------------
def tc(text, w, bold=False, fill=None, span=1, sz=20, color=None, align='left', underline=False):
    shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill if fill else ''
    sp = '<w:gridSpan w:val="%d"/>' % span if span > 1 else ''
    rp = '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>' + ('<w:b/>' if bold else '') + \
         ('<w:color w:val="%s"/>' % color if color else '') + '<w:sz w:val="%d"/>' % sz + ('<w:u w:val="single"/>' if underline else '')
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s<w:tcBorders><w:top w:val="single" w:sz="4" w:color="000000"/><w:left w:val="single" w:sz="4" w:color="000000"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="000000"/><w:right w:val="single" w:sz="4" w:color="000000"/></w:tcBorders>%s<w:vAlign w:val="center"/></w:tcPr>'
            '<w:p><w:pPr><w:keepNext/><w:spacing w:before="20" w:after="20"/><w:jc w:val="%s"/></w:pPr><w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:p></w:tc>'
            ) % (w, sp, shd, align, rp, text)
A, B = 6800, 3000
rows = [
 ('Encoding Mode', '{{STG_ENCODING}}', True, None), ('Bitrate Type', '{{STG_BITRATE_TYPE}}', True, None),
 ('Recording Resolution', '{{STG_RESOLUTION}}', True, None), ('Frame Rate(fps)', '{{STG_FPS}}', True, None),
 ('Bitrate (Mbps)', '{{STG_BITRATE_MBPS}}', True, None), ('No. of Cameras', '{{STG_CAMERAS}}', True, 'FFFF00'),
 ('120 days Estimate storage per Camera (TB)', '{{STG_120D_PER_CAM_TB}}', False, None),
 ('Per 40 Seconds event recording per camera Estimate storage (MB)', '{{STG_EVENT_MB}}', False, None),
 ('Number of Events per Day per Camera', '{{STG_EVENTS_PER_DAY}}', True, 'FFFF00'),
 ('Per Day Event Recording per camera Estimate storage (GB)', '{{STG_DAY_EVENT_GB}}', False, None),
 ('90 Days event recording total camera Estimate storage (TB)', '{{STG_90D_EVENT_TB}}', False, None),
 ('1 Event Image size (MB)', '{{STG_IMG_MB}}', False, None),
 ('Image storage per day (GB)', '{{STG_IMG_GB_DAY}}', False, None),
 ('90 Days Image Storage (GB)', '{{STG_90D_IMG_GB}}', False, None),
 ('Total Required Storage (TB)', '{{STG_TOTAL_TB}}', True, None)]
xml = '<w:tbl xmlns:w="%s"><w:tblPr><w:tblW w:w="%d" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/></w:tblGrid>' % (NS['w'], A+B, A, B)
xml += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s%s</w:tr>' % (tc('STORAGE CALCULATION - (40s Recording (20s Pre &amp; 20s Post) + Image Events for 90 Days &amp; Continuous Record 120 Days', A+B, True, None, 2, 22, 'FF0000', 'left', True), '')
xml += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s%s</w:tr>' % (tc('Description', A, True, 'BFBFBF', 1, 24, None, 'center'), tc('POI System (90 Days Event Record)', B, True, 'BFBFBF', 1, 20, None, 'center'))
for lab, tok, bold, fill in rows:
    xml += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s%s</w:tr>' % (tc(lab, A, bold), tc(tok, B, bold, fill, 1, 20, None, 'center'))
xml += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s%s</w:tr>' % (tc('Total Required Storage with {{STG_EXTRA_PCT}}% Extra (TB)', A, True, None, 1, 26), tc('{{STG_TOTAL_EXTRA_TB}}', B, True, 'D9D9D9', 1, 26, None, 'center'))
xml += '<w:tr><w:trPr><w:cantSplit/></w:trPr>%s</w:tr></w:tbl>' % tc('Note :- POI storage calculations are project-dependent and the final confirmation will be provided by the MOI POI Team.', A+B, True, None, 2, 24, 'FF0000', 'center')
storage_tbl = etree.fromstring(xml)

kids = list(body)
def idx_of(prefix): return next(i for i, e in enumerate(kids) if e.tag == W('p') and ptext(e).strip().startswith(prefix))
i_nvr = kids.index(t3)
# remove spacer paragraph(s) + the pasted storage picture that follow the NVR table, insert native table
i03 = idx_of('03: Verification')
for e in kids[i_nvr + 1:i03]: body.remove(e)
spacer = etree.Element(W('p'))
t3.addnext(spacer); spacer.addnext(storage_tbl)
after = etree.Element(W('p')); storage_tbl.addnext(after)

# ---- Page breaks: replace stacks of empty paragraphs with real page-break-before ------------------
def page_break_before(p):
    ppr = p.find(W('pPr'))
    if ppr is None: ppr = etree.Element(W('pPr')); p.insert(0, ppr)
    if ppr.find(W('pageBreakBefore')) is None:
        pb = etree.Element(W('pageBreakBefore'))
        st = ppr.find(W('pStyle')); (st.addnext(pb) if st is not None else ppr.insert(0, pb))

def is_empty(e):
    return e.tag == W('p') and not ptext(e).strip() and not xp(e, './/w:drawing|.//w:pict')

kids = list(body); i03 = idx_of('03: Verification'); i04 = idx_of('04: Floor Key'); i05 = idx_of('05: Location Image')
page_break_before(kids[i03])
for e in kids[i03:i05]:
    if is_empty(e) and e is not kids[i03]: 
        # keep the one blank line between "Note" block paragraphs only if it is not trailing whitespace
        pass
# drop the trailing empty run of paragraphs (before 04) and between 04 and 05
for e in kids[i04 + 1:i05]:
    if is_empty(e) or e.tag.endswith('bookmarkEnd'): body.remove(e)
k2 = list(body); i = k2.index(kids[i04])
for e in reversed(k2[:i]):
    if is_empty(e): body.remove(e)
    else: break
page_break_before(kids[i04])
fp = etree.Element(W('p')); r = etree.SubElement(fp, W('r')); set_t(etree.SubElement(r, W('t')), '{{FLOOR_PLAN}}')
kids[i04].addnext(fp)

# ---- Per-camera photo pages: keep ONE prototype (the 2nd camera), delete the first ---------------
kids = list(body); ia = idx_of('05: Location Image'); ib = idx_of('Location Image Reference: Receiving')
for e in kids[ia:ib]: body.remove(e)
kids = list(body); ib = idx_of('Location Image Reference: Receiving'); sect = body.find(W('sectPr'))
block = [e for e in kids[ib:] if e is not sect]
for e in block:                                  # remove bookmark leftovers and VML fallbacks (Word reads mc:Choice)
    for x in list(e.iter(W('bookmarkStart'), W('bookmarkEnd'))): x.getparent().remove(x)
for fb in list(body.iter(q('mc:Fallback'))): fb.getparent().remove(fb)
block = [e for e in block if e.getparent() is body]
head = block[0]
page_break_before(head)
replace_in_paragraph(head, 'Location Image Reference: ', '{{SEC_PREFIX}}Location Image Reference: ')
replace_in_paragraph(head, 'Receiving Entrance', '{{LOCATION_NAME}}')
for e in block:
    for p in e.iter(W('p')):
        if 'Location: Receiving Entrance' in ptext(p):
            for r in p.findall(W('r')): p.remove(r)
            r1 = etree.SubElement(p, W('r')); r1pr = etree.SubElement(r1, W('rPr')); etree.SubElement(r1pr, W('b')); set_t(etree.SubElement(r1, W('t')), 'Location: ')
            r2 = etree.SubElement(p, W('r')); set_t(etree.SubElement(r2, W('t')), '{{LOCATION_NAME}}')
        elif 'Camera' in ptext(p) and 'Height:' in ptext(p):
            rpr = copy.deepcopy(xp(p, './/w:r/w:rPr')[0]) if xp(p, './/w:r/w:rPr') else None
            for r in p.findall(W('r')): p.remove(r)
            for n, line in enumerate(['Camera Location', 'Height: {{HEIGHT}} M', 'Distance: {{DISTANCE}} M', '{{INSTALL_TYPE}}']):
                r = etree.SubElement(p, W('r'))
                if rpr is not None: r.append(copy.deepcopy(rpr))
                if n: etree.SubElement(r, W('br'))
                set_t(etree.SubElement(r, W('t')), line)
pics = [d for e in block for d in xp(e, './/wp:inline//wp:docPr')]
assert len(pics) == 2, len(pics)
pics[0].set('descr', '{{IMG_TARGET}}'); pics[1].set('descr', '{{IMG_CAMERA}}')
def marker(txt):
    m = etree.Element(W('p')); r = etree.SubElement(m, W('r')); set_t(etree.SubElement(r, W('t')), txt); return m
head.addprevious(marker('{{#CAMERA_PAGES}}')); block[-1].addnext(marker('{{/CAMERA_PAGES}}'))
doc.write(doc_path, xml_declaration=True, encoding='UTF-8', standalone=True)

# ---- Header (date + revision live inside text boxes, duplicated in mc:Fallback) --------------------
hd = etree.parse(hdr_path)
for p in hd.getroot().iter(W('p')):
    if ptext(p).strip() == '24 Aug 2026': set_paragraph_text(p, '{{REPORT_DATE}}', False)
    replace_in_paragraph(p, 'REV 0', 'REV {{REVISION}}')
hd.write(hdr_path, xml_declaration=True, encoding='UTF-8', standalone=True)

# ---- Zip (Content_Types first) -----------------------------------------------------------------------
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(tmp, '[Content_Types].xml'), '[Content_Types].xml')
    for root, _, files in os.walk(tmp):
        for f in files:
            full = os.path.join(root, f); arc = os.path.relpath(full, tmp)
            if arc != '[Content_Types].xml': z.write(full, arc)
shutil.rmtree(tmp); print('template written:', dst)
