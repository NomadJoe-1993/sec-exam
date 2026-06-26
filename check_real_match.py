"""Check real exam matching and comprehensive question distribution."""
import json, re
from collections import defaultdict

# Load data
with open('/home/betterman/233_crawler/integrated/merged_data.json') as f:
    md = json.load(f)
with open('/home/betterman/233_crawler/integrated/final_merged.json') as f:
    fm = json.load(f)
with open('/home/betterman/sec-exam-deploy/real_exam_data.json') as f:
    rex = json.load(f)

# Real exam texts - collect all
real_stems = set()
for pname, plist in rex['papers'].items():
    for q in plist:
        stem = q.get('stem', q.get('q', ''))
        norm = re.sub(r'\s+', '', stem)[:50]
        real_stems.add(norm)
print(f"Real exam unique stems: {len(real_stems)}")

# Check finance questions from merged_data that match real exam
fin_qs = md['finance']['questions']
matches = 0
for q in fin_qs[:500]:
    qn = re.sub(r'\s+', '', q['q'])[:50]
    for rs in real_stems:
        if rs in qn or qn in rs:
            matches += 1
            break
print(f"Finance matching (first 500): {matches}")

# Check comprehensive questions
for subject, subj_name in [('finance', '金融基础'), ('law', '法律法规')]:
    # From merged_data
    md_qs = md.get(subject, {}).get('questions', [])
    md_comp = [q for q in md_qs if q.get('type') == 'comprehensive']
    
    # From final_merged
    fm_qs = fm.get(subject, {}).get('questions', [])
    fm_comp = [q for q in fm_qs if q.get('type') == 'comprehensive']
    
    # Also from zc files and sprint
    zc_dir = '/home/betterman/sec-exam-deploy'
    extra_comp = []
    prefix = 'ch' if subject == 'finance' else 'fl'
    import os, glob
    for fname in sorted(glob.glob(f'{zc_dir}/sprint_{subj_name}*_不定项*')):
        with open(fname) as f:
            data = json.load(f)
        for q in data.get('questions', []):
            extra_comp.append(q)
    
    print(f'\n{subj_name} comprehensive:')
    print(f'  merged_data: {len(md_comp)}')
    print(f'  final_merged: {len(fm_comp)}')
    if extra_comp:
        print(f'  sprint_不定项: {len(extra_comp)}')
        print(f'  Sample: {json.dumps(extra_comp[0], ensure_ascii=False)[:200]}')
