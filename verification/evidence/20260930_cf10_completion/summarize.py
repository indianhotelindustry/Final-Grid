"""Summarise result files in this pack: python summarize.py [label-prefix]"""
import glob, json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
pref = sys.argv[1] if len(sys.argv) > 1 else ''
for f in sorted(glob.glob('results_%s*.json' % pref)):
    d = json.load(open(f, encoding='utf-8'))
    fails = [c['case'] for c in d['checks'] if c['severity'] == 'gate' and not c['pass']]
    notes = [c['case'] for c in d['checks'] if c['severity'] != 'gate' and not c['pass']]
    print('%-34s %s %s/%s %-4s prod=%s commit=%s clean=%s fails=%s notes=%s' % (
        f, d['started'], d['gates_passed'], d['gates_total'], d['verdict'],
        d['production_sha256_after'][:8], (d.get('app_commit') or '?')[:7],
        d.get('app_tree_clean'), fails[:8], notes))
