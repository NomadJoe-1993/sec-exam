#!/usr/bin/env python3
"""Split multi-select questions by chapter, with keyword classification."""
import json, glob, os, re
from collections import defaultdict

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ---- Chapter definitions ----
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

# ---- Chapter keywords for classification ----
FIN_KEYWORDS = {
    "ch1":  ["金融市场体系", "金融工具", "直接融资", "间接融资", "货币市场", "资本市场", "金融资产"],
    "ch2":  ["中国金融体系", "中央银行", "货币政策", "多层次资本市场", "科创板", "创业板", "主板", "北交所", "新三板"],
    "ch3":  ["证券市场主体", "证券公司", "证券交易所", "证券业协会", "证监会", "投资者", "中介机构"],
    "ch4a": ["股票", "普通股", "优先股", "IPO", "注册制", "核准制", "发行", "上市"],
    "ch4b": ["股票交易", "竞价", "做市商", "融资融券", "行情", "指数", "沪港通", "深港通"],
    "ch5a": ["债券", "国债", "地方政府债", "金融债", "公司债", "企业债", "可转债"],
    "ch5b": ["债券交易", "债券评级", "收益率", "久期", "信用风险", "债券市场"],
    "ch6":  ["基金", "证券投资基金", "开放式", "封闭式", "ETF", "LOF", "基金管理人", "托管人"],
    "ch7":  ["衍生工具", "期货", "期权", "互换", "远期", "金融衍生品", "股指期货", "套期保值"],
    "ch8":  ["风险管理", "风险", "VaR", "系统性风险", "非系统性风险", "信用风险", "市场风险"],
}

LAW_KEYWORDS = {
    "fl1a": ["证券市场基本法律", "证券法", "公司法", "基金法", "法律"],
    "fl1b": ["合伙企业", "合同法", "信托法", "证券发行", "证券交易"],
    "fl2":  ["经营机构管理", "证券公司管理", "风控", "净资本", "合规", "内部控制", "风险控制"],
    "fl3a": ["业务规范", "证券经纪", "证券承销", "保荐", "财务顾问", "证券自营"],
    "fl3b": ["资产管理", "融资融券", "IB业务", "代办股份转让", "中间介绍"],
    "fl4":  ["违法违规", "法律责任", "内幕交易", "操纵市场", "虚假陈述", "老鼠仓", "处罚"],
    "fl5":  ["行业文化", "职业道德", "从业人员", "行为规范", "廉洁从业"],
}

def classify_chapter(q_text, chapter_map, keywords_map):
    """Classify a question into a chapter by keyword matching."""
    text = (q_text.get('q', '') + ' ' + q_text.get('an', '')).lower()
    best_chapter = list(chapter_map.keys())[0]
    best_score = 0
    for ch_id, kws in keywords_map.items():
        score = sum(1 for kw in kws if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_chapter = ch_id
    return best_chapter

# ---- Collect multi-select questions from all sources ----
all_files = sorted(glob.glob('*.json'))
skip = {'manifest.json', 'real_exam_data.json', 'gw_fin.json', 'gw_law.json',
        'check_comp.py', 'check_real_match.py', 'audit_questions.py',
        'gen_exam_papers.py', 'gen_exam_papers_v2.py', 'gen_exam_papers_v3.py',
        'gen_section_practice.py', 'start-server.bat', 'fin_review_50.json',
        'multi_fin.json', 'multi_law.json'}

fin_multi_by_ch = defaultdict(list)
law_multi_by_ch = defaultdict(list)

for fname in all_files:
    if fname in skip or fname.startswith('multi_') or fname.endswith('.html'):
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
    fname_lower = fname.lower()
    
    # Determine if this is finance or law
    if '金融' in subject or '金融' in fname:
        chapter_map = {k: v[0] for k, v in FIN_CHAPTERS}
        kws_map = FIN_KEYWORDS
        target = fin_multi_by_ch
    elif '法规' in subject or 'law' in fname:
        chapter_map = {k: v[0] for k, v in LAW_CHAPTERS}
        kws_map = LAW_KEYWORDS
        target = law_multi_by_ch
    else:
        continue
    
    for q in multis:
        ch = classify_chapter(q, chapter_map, kws_map)
        target[ch].append(q)

print("=== 金融基础 各章多选分配 ===")
for ch_id, title in FIN_CHAPTERS:
    qs = fin_multi_by_ch[ch_id]
    print(f"  {ch_id:5s} {title:30s} | {len(qs):3d} 题")

print("\n=== 法律法规 各章多选分配 ===")
for ch_id, title in LAW_CHAPTERS:
    qs = law_multi_by_ch[ch_id]
    print(f"  {ch_id:5s} {title:30s} | {len(qs):3d} 题")

# ---- Deduplicate by question text fingerprint ----
def dedup(questions):
    seen = set()
    result = []
    for q in questions:
        fp = q.get('q', '')[:40]
        if fp not in seen:
            seen.add(fp)
            result.append(q)
    return result

# ---- Write per-chapter JSON files ----
print("\n--- 写入文件 ---")
chapter_titles_fin = {k: v for k, v in FIN_CHAPTERS}
chapter_titles_law = {k: v for k, v in LAW_CHAPTERS}

for prefix, ch_map, titles, output_prefix in [
    ('fin', FIN_CHAPTERS, chapter_titles_fin, 'multi'),
    ('law', LAW_CHAPTERS, chapter_titles_law, 'multi'),
]:
    data_source = fin_multi_by_ch if prefix == 'fin' else law_multi_by_ch
    for ch_id, ch_title in ch_map:
        qs = dedup(data_source[ch_id])
        # Sort by ID
        for i, q in enumerate(qs):
            q['id'] = i + 1
        
        if not qs:
            continue
        
        fname = f"{output_prefix}_{prefix}_{ch_id}.json"
        doc = {
            "id": f"{output_prefix}_{prefix}_{ch_id}",
            "title": ch_title + "·多选专项",
            "subject": "金融市场基础知识" if prefix == 'fin' else "证券市场基本法律法规",
            "count": len(qs),
            "questions": qs
        }
        with open(fname, 'w') as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"  ✅ {fname} ({len(qs)}题)")

# ---- Update manifest.json ----
with open('manifest.json') as f:
    manifest = json.load(f)

# Remove old multi_practice
manifest['categories'] = [c for c in manifest['categories'] if c['id'] != 'multi_practice']

# Add new per-chapter multi categories
fin_items = []
for ch_id, ch_title in FIN_CHAPTERS:
    fname = f"multi_fin_{ch_id}"
    qs = dedup(fin_multi_by_ch[ch_id])
    if qs:
        fin_items.append({
            "id": fname,
            "title": ch_title,
            "subject": "金融市场基础知识",
            "count": len(qs)
        })

law_items = []
for ch_id, ch_title in LAW_CHAPTERS:
    fname = f"multi_law_{ch_id}"
    qs = dedup(law_multi_by_ch[ch_id])
    if qs:
        law_items.append({
            "id": fname,
            "title": ch_title,
            "subject": "证券市场基本法律法规",
            "count": len(qs)
        })

# Insert after review category
review_idx = next(i for i, c in enumerate(manifest['categories']) if c['id'] == 'review')
new_categories = [
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
manifest['categories'][review_idx+1:review_idx+1] = new_categories

with open('manifest.json', 'w') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("\n✅ manifest.json updated")
print(f"   金融基础多选: {sum(i['count'] for i in fin_items)} 题 / {len(fin_items)} 章")
print(f"   法律法规多选: {sum(i['count'] for i in law_items)} 题 / {len(law_items)} 章")
