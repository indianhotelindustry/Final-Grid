"""Deep-diff result.json of matching PVF packs from two battery outputs.
Ignores volatile keys (timestamps, durations, paths, run ids, hosts, pids)."""
import json, os, re, sys
VOL = re.compile(r'(time|_at$|^at$|duration|elapsed|_ms$|seconds|started|finished|path|dir|root|run_id|pack|host|pid|python|cwd|worktree|generated|created|timestamp|stamp|wall|copy|tmp|work|^id$)', re.I)
def walk(a, b, p, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if VOL.search(str(k)): continue
            walk(a.get(k, '<absent>'), b.get(k, '<absent>'), p + '/' + str(k), out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): out.append((p, 'len %d' % len(a), 'len %d' % len(b)))
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, p + '[%d]' % i, out)
    elif a != b:
        out.append((p, a, b))
A, B = sys.argv[1], sys.argv[2]
for pack in sorted(os.listdir(os.path.join(A, 'pvf'))):
    fa = os.path.join(A, 'pvf', pack, 'result.json'); fb = os.path.join(B, 'pvf', pack, 'result.json')
    if not os.path.exists(fb):
        print('##', pack, 'MISSING in branch'); continue
    out = []
    walk(json.load(open(fa, encoding='utf-8')), json.load(open(fb, encoding='utf-8')), '', out)
    print('##', pack, 'differences:', len(out))
    for p, x, y in out[:40]:
        print('   ', p[:150], '|', str(x)[:90], '->', str(y)[:90])
