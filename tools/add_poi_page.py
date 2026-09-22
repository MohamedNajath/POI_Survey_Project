"""One-off: adds a '06: POI Camera Installation Table' page to template.docx, right before the closing sectPr.
A single {{POI_TABLE}} token paragraph marks where generate_report.py builds the real (colour-coded) table."""
import sys, zipfile, shutil, tempfile, os
from lxml import etree
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docx_xml import W, NS, xp

src = dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template.docx')
tmp = tempfile.mkdtemp(); zipfile.ZipFile(src).extractall(tmp)
dp = os.path.join(tmp, 'word/document.xml'); doc = etree.parse(dp); body = doc.getroot().find(W('body'))
if any('{{POI_TABLE}}' in ''.join(p.itertext()) for p in body.iter(W('p'))):
    print('POI_TABLE marker already present – nothing to do')
else:
    sect = body.find(W('sectPr'))
    heading = etree.fromstring(
      '<w:p xmlns:w="%s"><w:pPr><w:pageBreakBefore/></w:pPr>'
      '<w:r><w:rPr><w:b/><w:color w:val="89143C"/><w:u w:val="single"/><w:sz w:val="28"/></w:rPr>'
      '<w:t xml:space="preserve">06: POI Camera Installation Table (Reference)</w:t></w:r></w:p>' % NS['w'])
    note = etree.fromstring(
      '<w:p xmlns:w="%s"><w:pPr><w:spacing w:before="120" w:after="120"/></w:pPr>'
      '<w:r><w:rPr><w:i/><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">'
      'Used to determine the recommended installation height and lens model for each camera from its distance to the target.'
      '</w:t></w:r></w:p>' % NS['w'])
    marker = etree.fromstring('<w:p xmlns:w="%s"><w:r><w:t>{{POI_TABLE}}</w:t></w:r></w:p>' % NS['w'])
    sect.addprevious(heading); heading.addnext(note); note.addnext(marker)
    doc.write(dp, xml_declaration=True, encoding='UTF-8', standalone=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(tmp, '[Content_Types].xml'), '[Content_Types].xml')
        for r, _, fs in os.walk(tmp):
            for f in fs:
                full = os.path.join(r, f); arc = os.path.relpath(full, tmp)
                if arc != '[Content_Types].xml': z.write(full, arc)
    print('POI_TABLE page added')
shutil.rmtree(tmp)
