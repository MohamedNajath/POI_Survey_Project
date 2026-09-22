"""Small OOXML helpers shared by build_template.py and generate_report.py"""
from lxml import etree
NS = {
 'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
 'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
 'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
 'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'

def q(tag):
    p, l = tag.split(':'); return '{%s}%s' % (NS[p], l)

def W(tag): return q('w:' + tag)

def xp(el, path): return el.xpath(path, namespaces=NS)

def own_ts(p):
    """w:t elements belonging to paragraph p (excluding nested text-box paragraphs)."""
    return [t for t in p.iter(W('t')) if next(t.iterancestors(W('p'))) is p]

def ptext(p): return ''.join(t.text or '' for t in own_ts(p))

def set_t(t, text):
    t.text = text; t.set(XML_SPACE, 'preserve')

def replace_in_paragraph(p, old, new):
    """Replace `old` with `new` even if it spans several runs. Uses the first run's formatting."""
    ts = own_ts(p); s = ''.join(t.text or '' for t in ts)
    i = s.find(old)
    if i < 0: return False
    j = i + len(old); pos = 0; done = False
    for t in ts:
        txt = t.text or ''; a, b = pos, pos + len(txt); pos = b
        if b <= i or a >= j: continue
        if not done:
            set_t(t, txt[:i - a] + new + (txt[j - a:] if j < b else '')); done = True
        else:
            set_t(t, txt[j - a:] if j < b else '')
    return True

def set_paragraph_text(p, new, keep_leading_space=True):
    ts = own_ts(p)
    if not ts:
        r = etree.SubElement(p, W('r'))
        ppr_rpr = xp(p, 'w:pPr/w:rPr')
        if ppr_rpr:
            import copy; r.append(copy.deepcopy(ppr_rpr[0]))
        t = etree.SubElement(r, W('t')); ts = [t]; orig = ''
    else:
        orig = ''.join(x.text or '' for x in ts)
    lead = orig[:len(orig) - len(orig.lstrip())] if keep_leading_space else ''
    set_t(ts[0], lead + new)
    for t in ts[1:]: set_t(t, '')

def cell(tbl, r, c):
    return tbl.findall(W('tr'))[r].findall(W('tc'))[c]

def set_cell_text(tbl, r, c, new):
    set_paragraph_text(cell(tbl, r, c).findall(W('p'))[0], new)
