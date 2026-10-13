"""Proves static/rules.js and poi_rules.py give identical answers over a dense grid of inputs."""
import json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from poi_rules import calc, height_options
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ref = json.load(open(os.path.join(root, 'reference.default.json')))
options = height_options(ref, 6.8)
assert options['ok'] and options['table_distance'] == 6 and options['heights'] == [2.2, 2.3, 2.4], options
assert calc(ref, 6.8, 6)['height'] == 2.2
cases = [[round(i * 0.05, 2), a] for i in range(-4, 560) for a in (6, 7, 8)] + [['abc', 6], ['', 6], [5, 9], ['4,9', 8], [None, 6]]
js = subprocess.run(['node', '-e', '''const P=require("./static/rules.js");const ref=require("./reference.default.json");
const c=JSON.parse(process.argv[1]);console.log(JSON.stringify({results:c.map(([d,a])=>P.calc(ref,d,a)),options:P.heightOptions(ref,6.8)}))''', json.dumps(cases)], capture_output=True, text=True, encoding='utf-8', cwd=root)
assert js.returncode == 0, js.stderr
jr = json.loads(js.stdout); bad = 0
assert jr['options']['ok'] and jr['options']['table_distance'] == 6 and jr['options']['heights'] == [2.2, 2.3, 2.4], jr['options']
for (d, a), j in zip(cases, jr['results']):
    p = calc(ref, d, a); p = {k: p[k] for k in ('ok', 'height', 'lens', 'table_distance', 'error')}
    if p != j: bad += 1; print('MISMATCH', d, a, p, j) if bad < 6 else None
print('cases:', len(cases), 'mismatches:', bad); sys.exit(1 if bad else 0)
