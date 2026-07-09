#!/usr/bin/env python3
"""Generate per-chapter multi-select practice with reliable classification."""
import json, glob, os
from collections import defaultdict

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Clean up old auto-classified files
for f in glob.glob('multi_*.json'):
    if f not in ('multi_fin.json', 'multi_law.json'):
        os.remove(f)

# ── Chapter definitions ──
FIN_CHAPTERS = [
    ("ch1",  "第1章·金融市场体系"),
    ("ch2",  "第2章·中国的金融体系与多层次资本市场"),
    ("ch3",  "第3章·证券市场主体"),
    ("ch4a", "第4章·股票 (上)"),
    ("ch4b", "第4章·股票 (下)"),
    ("ch5a", "第5章·债券 (上)"),
    ("ch5b", "第5章·债券 (下)"),
    ("ch6",  "第6章·证券投资基金"),
    ("ch7",  "第7章·金融衍生工具"),
    ("ch8",  "第8章·金融风险管理"),
]

LAW_CHAPTERS = [
    ("fl1a", "第1章·证券市场基本法律法规 (上)"),
    ("fl1b", "第1章·证券市场基本法律法规 (下)"),
    ("fl2",  "第2章·证券经营机构管理规范"),
    ("fl3a", "第3章·证券公司业务规范 (上)"),
    ("fl3b", "第3章·证券公司业务规范 (下)"),
    ("fl4",  "第4章·典型违法违规行为及法律责任"),
    ("fl5",  "第5章·行业文化、职业道德与从业人员行为规范"),
]

# ── Phase 1: Extract multi-select from zc_* (reliable chapter assignment) ──
fin_multi = defaultdict(list)
law_multi = defaultdict(list)

# zc_* chapter name → short code mapping
chapter_map = {}
for code, title in FIN_CHAPTERS:
    chapter_map[title] = code
for code, title in LAW_CHAPTERS:
    chapter_map[title] = code

# Reverse: zc_* file key → chapter code
zc_fin_map = {
    'zc_ch1': 'ch1', 'zc_ch2': 'ch2', 'zc_ch3': 'ch3',
    'zc_ch4a': 'ch4a', 'zc_ch4b': 'ch4b', 'zc_ch5a': 'ch5a', 'zc_ch5b': 'ch5b',
    'zc_ch6': 'ch6', 'zc_ch7': 'ch7', 'zc_ch8': 'ch8'
}
zc_law_map = {
    'zc_fl1a': 'fl1a', 'zc_fl1b': 'fl1b', 'zc_fl2': 'fl2',
    'zc_fl3a': 'fl3a', 'zc_fl3b': 'fl3b', 'zc_fl4': 'fl4', 'zc_fl5': 'fl5'
}

for fname in sorted(glob.glob('zc_*.json')):
    key = fname.replace('.json', '')
    with open(fname) as f:
        data = json.load(f)
    
    ch_code = zc_fin_map.get(key) or zc_law_map.get(key)
    if not ch_code:
        continue
    
    target = fin_multi if key.startswith('zc_ch') else law_multi
    for q in data.get('questions', []):
        if q.get('type') == 'multi':
            target[ch_code].append(q)

# ── Phase 2: Add multi-select from sprint/sim/zt sources ──
# Use keyword matching only for these additional sources
FIN_KWS = {
    'ch1':  ['金融市场体系','直接融资','间接融资','货币市场','资本市场','金融工具'],
    'ch2':  ['中国金融','央行','货币政策','多层次资本','科创板','创业板','北交所','新三板','中小板'],
    'ch3':  ['市场主体','证券公司','证券交易所','证券业协会','证监会','投资者保护','中介'],
    'ch4a': ['股票','普通股','优先股','IPO','注册制','发行上市'],
    'ch4b': ['股票交易','竞价','做市商','融资融券','指数','沪港通','深港通'],
    'ch5a': ['债券','国债','地方债','金融债','公司债','企业债','可转债'],
    'ch5b': ['债券评级','收益率','久期','债券市场'],
    'ch6':  ['基金','证券投资','开放式','封闭式','ETF','LOF','基金管理','托管'],
    'ch7':  ['衍生','期货','期权','互换','远期','股指期货','套期保值'],
    'ch8':  ['风险','VaR','系统性','非系统性','风险控制'],
}
LAW_KWS = {
    'fl1a': ['证券法','公司法','基金法','合伙企业','法律基本'],
    'fl1b': ['证券发行','证券交易','上市公司收购','信息披露'],
    'fl2':  ['经营机构','管理规范','净资本','合规','内控','风险控制'],
    'fl3a': ['业务规范','经纪','承销','保荐','自营','投行'],
    'fl3b': ['资产管理','融资融券','IB','中间业务','私募'],
    'fl4':  ['违法','违规','内幕交易','操纵市场','虚假陈述','处罚','责任'],
    'fl5':  ['文化','职业道','从业规范','廉洁'],
}

def classify(q, kws_map):
    text = (q.get('q','') + ' ' + (q.get('an','') or '')).lower()
    best_ch = list(kws_map.keys())[0]
    best_score = 0
    for ch, kws in kws_map.items():
        score = sum(1 for kw in kws if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_ch = ch
    return best_ch

all_files = sorted(glob.glob('*.json'))
skip_source = {'manifest.json', 'real_exam_data.json', 'gw_fin.json', 'gw_law.json',
               'check_comp.py', 'check_real_match.py', 'audit_questions.py',
               'gen_exam_papers.py', 'gen_exam_papers_v2.py', 'gen_exam_papers_v3.py',
               'gen_section_practice.py', 'start-server.bat', 'fin_review_50.json',
               'split_multi_by_chapter.py'}

for fname in all_files:
    if fname.startswith('multi_') or fname.startswith('zc_') or fname in skip_source or fname.endswith('.html'):
        continue
    with open(fname) as f:
        try:
            data = json.load(f)
        except:
            continue
    
    multis = [q for q in data.get('questions', []) if q.get('type') == 'multi']
    if not multis:
        continue
    
    subject = data.get('subject', '')
    fname_l = fname.lower()
    
    if '金融' in subject or '金融' in fname_l or subject.startswith('金融市场'):
        kws = FIN_KWS
        target = fin_multi
    elif '法规' in subject or 'law' in fname_l:
        kws = LAW_KWS
        target = law_multi
    else:
        continue
    
    for q in multis:
        ch = classify(q, kws)
        target[ch].append(q)

# ── Phase 3: Dedup by question text ──
def dedup(questions):
    seen = set()
    result = []
    for q in questions:
        fp = q.get('q', '')[:50]
        if fp not in seen:
            seen.add(fp)
            result.append(q)
    return result

for d in [fin_multi, law_multi]:
    for ch in list(d.keys()):
        d[ch] = dedup(d[ch])

# ── Phase 4: Merge small chapters ──
# Create merged chapter mapping
fin_merged_map = {
    'ch1': 'ch1', 'ch2': 'ch2', 'ch3': 'ch3',
    'ch4': ['ch4a', 'ch4b'],  # merge ch4a+ch4b
    'ch5': ['ch5a', 'ch5b'],  # merge ch5a+ch5b
    'ch6': 'ch6', 'ch7': 'ch7', 'ch8': 'ch8'
}
law_merged_map = {
    'fl1': ['fl1a', 'fl1b'],  # merge fl1a+fl1b
    'fl2': 'fl2',
    'fl3': ['fl3a', 'fl3b'],  # merge fl3a+fl3b
    'fl4': ['fl4', 'fl5'],    # merge fl4+fl5
}

def merge_chapters(src, merge_map):
    result = {}
    for merged_key, sources in merge_map.items():
        if isinstance(sources, str):
            result[merged_key] = dedup(src.get(sources, []))
        else:
            combined = []
            for s in sources:
                combined.extend(src.get(s, []))
            result[merged_key] = dedup(combined)
    return result

fin_merged = merge_chapters(fin_multi, fin_merged_map)
law_merged = merge_chapters(law_multi, law_merged_map)

# Updated chapter definitions after merge
FIN_CHAPTERS_MERGED = [
    ("ch1",  "第1章·金融市场体系"),
    ("ch2",  "第2章·中国的金融体系与多层次资本市场"),
    ("ch3",  "第3章·证券市场主体"),
    ("ch4",  "第4章·股票"),
    ("ch5",  "第5章·债券"),
    ("ch6",  "第6章·证券投资基金"),
    ("ch7",  "第7章·金融衍生工具"),
    ("ch8",  "第8章·金融风险管理"),
]

LAW_CHAPTERS_MERGED = [
    ("fl1", "第1章·证券市场基本法律法规"),
    ("fl2", "第2章·证券经营机构管理规范"),
    ("fl3", "第3章·证券公司业务规范"),
    ("fl4", "第4章·法律责任与职业道德"),
]

# ── Write files ──
print("=== 金融基础 多选(按章) ===")
for ch_id, ch_title in FIN_CHAPTERS_MERGED:
    qs = dedup(fin_merged[ch_id])
    for i, q in enumerate(qs):
        q['id'] = i + 1
    fname = f"multi_fin_{ch_id}.json"
    with open(fname, 'w') as f:
        json.dump({
            "id": f"multi_fin_{ch_id}",
            "title": ch_title + "·多选",
            "subject": "金融市场基础知识",
            "count": len(qs),
            "questions": qs
        }, f, ensure_ascii=False, indent=2)
    print(f"  {fname:20s} {ch_title:25s} {len(qs):3d}题")

print("\n=== 法律法规 多选(按章) ===")
for ch_id, ch_title in LAW_CHAPTERS_MERGED:
    qs = dedup(law_merged[ch_id])
    for i, q in enumerate(qs):
        q['id'] = i + 1
    fname = f"multi_law_{ch_id}.json"
    with open(fname, 'w') as f:
        json.dump({
            "id": f"multi_law_{ch_id}",
            "title": ch_title + "·多选",
            "subject": "证券市场基本法律法规",
            "count": len(qs),
            "questions": qs
        }, f, ensure_ascii=False, indent=2)
    print(f"  {fname:20s} {ch_title:25s} {len(qs):3d}题")

# ── Update manifest ──
with open('manifest.json') as f:
    manifest = json.load(f)

manifest['categories'] = [c for c in manifest['categories'] if not c['id'].startswith('multi_practice')]

fin_items = []
for ch_id, ch_title in FIN_CHAPTERS_MERGED:
    qs = dedup(fin_merged[ch_id])
    if qs:
        fin_items.append({
            "id": f"multi_fin_{ch_id}",
            "title": ch_title,
            "subject": "金融市场基础知识",
            "count": len(qs)
        })

law_items = []
for ch_id, ch_title in LAW_CHAPTERS_MERGED:
    qs = dedup(law_merged[ch_id])
    if qs:
        law_items.append({
            "id": f"multi_law_{ch_id}",
            "title": ch_title,
            "subject": "证券市场基本法律法规",
            "count": len(qs)
        })

new_cats = [
    {
        "id": "multi_practice_fin",
        "title": "🎯 多选专项 · 金融基础",
        "desc": "按章节逐章攻克多选题",
        "color": "#e91e63",
        "items": fin_items
    },
    {
        "id": "multi_practice_law",
        "title": "🎯 多选专项 · 法律法规",
        "desc": "按章节逐章攻克多选题",
        "color": "#9c27b0",
        "items": law_items
    }
]

review_idx = next(i for i, c in enumerate(manifest['categories']) if c['id'] == 'review')
manifest['categories'][review_idx+1:review_idx+1] = new_cats

with open('manifest.json', 'w') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("\n✅ manifest.json updated")
total_fin = sum(i['count'] for i in fin_items)
total_law = sum(i['count'] for i in law_items)
print(f"   金融基础: {total_fin}题 / {len(fin_items)}章")
print(f"   法律法规: {total_law}题 / {len(law_items)}章")
