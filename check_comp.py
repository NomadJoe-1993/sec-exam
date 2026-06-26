import json, re
from collections import defaultdict

with open('../../233_crawler/integrated/final_merged.json') as f:
    d = json.load(f)

law = d['law']['questions']
comp = [q for q in law if q.get('type') == 'comprehensive']
print(f'Total law comprehensive questions: {len(comp)}')

by_ch = defaultdict(list)
for q in comp:
    m = re.search(r'zc_fl(\d+)', q['id'])
    ch = int(m.group(1)) if m else 0
    by_ch[ch].append(q)

for ch in sorted(by_ch.keys()):
    print(f'  Ch{ch}: {len(by_ch[ch])}')
    for q in by_ch[ch][:2]:
        print(f'    {q["id"]}: {q["q"][:60]}...')

# Also check finance comp
fin = d['finance']['questions']
fin_comp = [q for q in fin if q.get('type') == 'comprehensive']
print(f'\nTotal finance comprehensive questions: {len(fin_comp)}')
by_ch = defaultdict(list)
for q in fin_comp:
    m = re.search(r'zc_ch(\d+)', q['id'])
    ch = int(m.group(1)) if m else 0
    by_ch[ch].append(q)
for ch in sorted(by_ch.keys()):
    print(f'  Ch{ch}: {len(by_ch[ch])}')
