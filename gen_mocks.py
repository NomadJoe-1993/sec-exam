#!/usr/bin/env python3
"""Generate 2 new mock papers from existing paper data."""
import json, random, hashlib

random.seed(42)  # reproducible

# 1. Load all questions from existing papers
all_q = {}  # dedup by question text hash
for prefix in ['paper_金融基础', 'paper_法律法规']:
    for i in range(1, 6):
        fn = f'{prefix}_{i}.json'
        with open(fn) as f:
            p = json.load(f)
        for q in p['questions']:
            # Dedup by question text hash
            h = hashlib.md5(q['q'].encode()).hexdigest()
            if h not in all_q:
                all_q[h] = q

questions = list(all_q.values())
print(f"Total unique questions: {len(questions)}")
types = {}
for q in questions:
    types[q['type']] = types.get(q['type'], 0) + 1
print(f"Type distribution: {types}")

# 2. Separate by type
by_type = {'single': [], 'multi': [], 'judge': []}
for q in questions:
    t = q['type']
    if t in by_type:
        by_type[t].append(q)

for t, lst in by_type.items():
    print(f"  {t}: {len(lst)} questions")
    random.shuffle(lst)

# 3. Compose 2 mock papers (120 q each)
# Target: ~45 single, ~45 multi, ~30 judge
TOTAL = 120
TARGET = {'single': 45, 'multi': 45, 'judge': 30}

mocks = []
for mock_id in [3, 4]:
    selected = []
    used_indices = {}
    for t, n in TARGET.items():
        pool = by_type[t]
        # Pick questions, avoiding duplicates with already selected
        picked = []
        for q in pool:
            h = hashlib.md5(q['q'].encode()).hexdigest()
            if h not in used_indices and len(picked) < n:
                picked.append(q)
                used_indices[h] = True
        selected.extend(picked)
        print(f"  mock_{mock_id}: {t} picked {len(picked)}/{n}")
    
    # Shuffle within types for variety
    random.shuffle(selected)
    
    mock = {
        "id": f"mock_{mock_id}",
        "title": f"模拟卷{mock_id} · 全真模拟",
        "subject": "全真模拟",
        "count": len(selected),
        "questions": selected
    }
    
    fn = f"mock_{mock_id}.json"
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(mock, f, ensure_ascii=False, indent=2)
    print(f"✅ Written {fn}: {len(selected)} questions")
    mocks.append(mock)

# 4. Update manifest.json
with open('manifest.json') as f:
    manifest = json.load(f)

# Find the 'mock' category
for cat in manifest['categories']:
    if cat['id'] == 'mock':
        # Add new mocks
        existing_ids = {item['id'] for item in cat['items']}
        for mock_id in [3, 4]:
            mock_id_str = f"mock_{mock_id}"
            if mock_id_str not in existing_ids:
                item = {
                    "id": mock_id_str,
                    "title": f"模拟卷{mock_id} · 全真模拟",
                    "subject": "全真模拟",
                    "count": 120
                }
                cat['items'].append(item)
                print(f"✅ Added {mock_id_str} to manifest mock category")
        break

with open('manifest.json', 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("✅ Manifest updated")
