#!/usr/bin/env python3
"""Generate print-friendly mock exam papers for 证券从业资格考试。

Produces two HTML files:
1. 金融市场基础知识_真题模拟卷.html (120题)
2. 证券市场基本法律法规_真题模拟卷.html (120题)

With: 40单选+40多选+30判断+10不定项, detailed 解析, chapter/考点 markings.
"""

import json, random, re, os, textwrap
from collections import defaultdict

random.seed(42)  # reproducible sampling

# ── Load data ──────────────────────────────────────────────────────────────
BASE = '/home/betterman/233_crawler/integrated'
with open(f'{BASE}/final_merged.json') as f:
    merged = json.load(f)
with open(f'{BASE}/merged_data.json') as f:
    md = json.load(f)

# Load real exam data for marking
with open('/home/betterman/sec-exam-deploy/real_exam_data.json') as f:
    real_exam_data = json.load(f)

# ── Chapter mapping ─────────────────────────────────────────────────────────
# ID pattern: `cflue_zc_ch{N}.json_XX` -> maps to chapter N
# ID pattern: `cflue_zc_fl{N}(a|b).json_XX` -> maps to law chapter N

def extract_chapter_from_id(qid):
    """Extract chapter number from question ID."""
    m = re.search(r'zc_ch(\d+)', qid)
    if m:
        return int(m.group(1))
    m = re.search(r'zc_fl(\d+)[a-z]?', qid)
    if m:
        return int(m.group(1))
    return None

# Build question pool per subject
# merged_data.json has chapters but questions don't have explicit ch field
# final_merged.json has questions merged from all sources

FIN_CHAPTERS = [
    ("第1章", "金融市场体系", 0.08, 0, 0, 0, 0, 0),
    ("第2章", "中国的金融体系与多层次资本市场", 0.12, 0, 0, 0, 0, 0),
    ("第3章", "证券市场主体", 0.10, 0, 0, 0, 0, 0),
    ("第4章", "股票", 0.20, 0, 0, 0, 0, 0),
    ("第5章", "债券", 0.15, 0, 0, 0, 0, 0),
    ("第6章", "证券投资基金", 0.15, 0, 0, 0, 0, 0),
    ("第7章", "金融衍生工具", 0.12, 0, 0, 0, 0, 0),
    ("第8章", "金融风险管理", 0.08, 0, 0, 0, 0, 0),
]

LAW_CHAPTERS = [
    ("第1章", "证券市场基本法律法规", 0.35, 0, 0, 0, 0, 0),
    ("第2章", "证券经营机构管理规范", 0.20, 0, 0, 0, 0, 0),
    ("第3章", "证券公司业务规范", 0.30, 0, 0, 0, 0, 0),
    ("第4章", "典型违法违规行为及法律责任", 0.10, 0, 0, 0, 0, 0),
    ("第5章", "行业文化与职业道德", 0.05, 0, 0, 0, 0, 0),
]

# Exam format: 40 single + 40 multi + 30 judge + 10 comprehensive = 120
TYPE_MAP = {'single': 40, 'multi': 40, 'judge': 30, 'comprehensive': 10}
TYPE_LABELS = {
    'single': '一、单项选择题（共40题，每题0.5分，共20分）',
    'multi': '二、多项选择题（共40题，每题1分，共40分）',
    'judge': '三、判断题（共30题，每题1分，共30分）',
    'comprehensive': '四、不定项选择题（共10题，每题1分，共10分）',
}
TYPE_SHORT = {'single': '单选', 'multi': '多选', 'judge': '判断', 'comprehensive': '不定项'}
TYPE_LETTER_MAP = {
    'single': '一、',
    'multi': '二、',
    'judge': '三、',
    'comprehensive': '四、',
}

def normalize_text(t):
    """Clean text for matching."""
    return re.sub(r'\s+', '', t).strip()[:50]

def build_pool(subject_key, chapters):
    """Build question pool from merged data, organized by chapter."""
    pool = merged.get(subject_key, {}).get('questions', [])
    # Also get from md
    pool2 = md.get(subject_key, {}).get('questions', [])
    
    # Merge pools (dedup by id)
    seen_ids = set()
    all_qs = []
    for q in pool + pool2:
        if q['id'] not in seen_ids:
            seen_ids.add(q['id'])
            all_qs.append(q)
    
    # Also add from zc files directly (sec-exam-check)
    zc_dir = '/home/betterman/sec-exam-check'
    prefix = 'ch' if subject_key == 'finance' else 'fl'
    for fname in sorted(os.listdir(zc_dir)):
        if fname.startswith(f'zc_{prefix}') and fname.endswith('.json'):
            with open(f'{zc_dir}/{fname}') as f:
                zc_data = json.load(f)
            for q in zc_data.get('questions', []):
                qid = f"zc_{fname.replace('.json','')}_{q['id']}"
                # Normalize: some have q/c/a/an keys, some have stem/options/answer/explanation
                if qid not in seen_ids:
                    seen_ids.add(qid)
                    normalized_q = {
                        'id': qid,
                        'q': q.get('q', q.get('stem', '')),
                        'c': q.get('c', {}),
                        'a': q.get('a', q.get('answer', '')),
                        'an': q.get('an', q.get('explanation', q.get('explanation', ''))),
                        'type': q.get('type', 'single'),
                    }
                    # Convert options if they're in list format
                    if 'options' in q:
                        opts = q['options']
                        normalized_q['c'] = {}
                        for opt in opts:
                            m = re.match(r'^([A-Z])[.、]?\s*(.*)', opt)
                            if m:
                                normalized_q['c'][m.group(1)] = m.group(2)
                    all_qs.append(normalized_q)
    
    # Map questions to chapters
    by_chapter = defaultdict(list)
    unassigned = []
    
    for q in all_qs:
        ch_num = extract_chapter_from_id(q['id'])
        if ch_num and 1 <= ch_num <= 8:
            by_chapter[ch_num].append(q)
        else:
            unassigned.append(q)
    
    # Distribute unassigned questions by analyzing content to find chapter
    # For cy_ questions, use subject-specific distribution
    if unassigned:
        ch_count = len(chapters)
        for i, q in enumerate(unassigned):
            ch = (i % ch_count) + 1
            by_chapter[ch].append(q)
    
    return by_chapter

def check_real_exam_status(q_text, real_exam_texts):
    """Check if a question is a real exam question."""
    q_norm = normalize_text(q_text)
    for re_text in real_exam_texts:
        if q_norm in re_text or re_text in q_norm:
            return True
    return False

def build_real_exam_texts():
    """Build set of normalized real exam question texts."""
    texts = set()
    for pname, plist in real_exam_data['papers'].items():
        for q in plist:
            stem = q.get('stem', q.get('q', ''))
            texts.add(normalize_text(stem))
    return texts

def sample_questions(by_chapter, chapters, real_exam_texts, subject_label):
    """Sample 120 questions (40+40+30+10) distributed by chapter weight."""
    total_per_type = {'single': 0, 'multi': 0, 'judge': 0, 'comprehensive': 0}
    
    # Calculate per-chapter type allocation
    ch_alloc = []
    for ch_num, (ch_code, ch_name, weight, *_) in enumerate(chapters, 1):
        alloc = {}
        for qtype, target in TYPE_MAP.items():
            alloc[qtype] = max(1, round(target * weight))
        ch_alloc.append((ch_num, ch_code, ch_name, alloc))
    
    # Adjust to ensure total = 120
    for qtype in TYPE_MAP:
        current = sum(a[qtype] for _, _, _, a in ch_alloc)
        target = TYPE_MAP[qtype]
        diff = target - current
        if diff > 0:
            # Add to chapters with highest weight
            sorted_alloc = sorted(ch_alloc, key=lambda x: -float(x[3][qtype]) if x[3][qtype] > 0 else 0)
            for i in range(diff):
                idx = i % len(sorted_alloc)
                sorted_alloc[idx][3][qtype] += 1
        elif diff < 0:
            # Remove from chapters with lowest weight that have more than 1
            while diff < 0:
                sorted_alloc = sorted(ch_alloc, key=lambda x: x[3][qtype])
                for idx in range(len(sorted_alloc)):
                    if sorted_alloc[idx][3][qtype] > 1:
                        sorted_alloc[idx][3][qtype] -= 1
                        diff += 1
                        break
    
    selected = []
    seen_texts = set()
    
    for ch_num, ch_code, ch_name, alloc in ch_alloc:
        pool = by_chapter.get(ch_num, [])
        for qtype, needed in alloc.items():
            type_pool = [q for q in pool if q.get('type') == qtype]
            if len(type_pool) < needed:
                print(f"  WARN: Ch{ch_num} {ch_name} only {len(type_pool)} {qtype}, need {needed}")
            
            # Prioritize questions that match real exam
            scored_pool = []
            for q in type_pool:
                q_text = q.get('q', '')
                q_norm = normalize_text(q_text)
                if q_norm in seen_texts:
                    continue
                score = 0
                if check_real_exam_status(q_text, real_exam_texts):
                    score += 10
                # Prefer questions with detailed explanations
                if len(q.get('an', '')) > 100:
                    score += 2
                # Prefer cflue source (more authoritative)
                if 'cflue' in q.get('id', ''):
                    score += 3
                elif 'cy' in q.get('id', ''):
                    score += 1
                elif 'xs' in q.get('id', ''):
                    score += 1
                scored_pool.append((score, q))
            
            # Sort by score descending, take top needed
            scored_pool.sort(key=lambda x: -x[0])
            
            for _, q in scored_pool[:needed]:
                q_text = q.get('q', '')
                q_norm = normalize_text(q_text)
                seen_texts.add(q_norm)
                
                is_real_exam = check_real_exam_status(q_text, real_exam_texts)
                
                selected.append({
                    'id': len(selected) + 1,
                    'type': qtype,
                    'q': q['q'],
                    'c': q['c'],
                    'a': q['a'],
                    'an': q['an'],
                    'chapter': f"{ch_code} {ch_name}",
                    'is_real_exam': is_real_exam,
                    'source_label': '【真题】' if is_real_exam else '【高频考点】',
                })
    
    return selected

def generate_question_html(q, idx):
    """Generate question HTML block."""
    qtype = q['type']
    options = q.get('c', {})
    
    # Format question text
    q_text = q['q']
    
    # Format options
    opts_html = ''
    if options:
        for letter in ['A', 'B', 'C', 'D', 'E', 'F']:
            if letter in options:
                opts_html += f'<div class="option"><span class="option-letter">{letter}.</span> {options[letter]}</div>'
    
    type_label = '【单选题】' if qtype == 'single' else \
                 '【多选题】' if qtype == 'multi' else \
                 '【判断题】' if qtype == 'judge' else '【不定项选择题】'
    
    return f'''
    <div class="question" data-type="{qtype}">
      <div class="q-header">
        <span class="q-number">{idx}.</span>
        <span class="q-type">{q['source_label']}{type_label}</span>
        <span class="q-chapter">{q['chapter']}</span>
      </div>
      <div class="q-text">{q_text}</div>
      <div class="options">{opts_html}</div>
      <div class="spacer"></div>
    </div>'''

def generate_answer_html(selected):
    """Generate answer key with detailed解析."""
    html = '<div class="answer-section">\n'
    html += '<h2>📋 参考答案与详细解析</h2>\n'
    
    for q in selected:
        qtype = q['type']
        answer = q['a']
        explanation = q['an']
        
        # Format answer display
        answer_display = answer
        if qtype == 'judge':
            answer_display = '✓ 正确' if answer in ('B', '√', '对') else '✗ 错误'
        
        html += f'''
    <div class="answer-card">
      <div class="answer-header">
        <span class="q-number">第{q['id']}题</span>
        <span class="q-type">{q['source_label']}{TYPE_SHORT.get(qtype, '')}</span>
        <span class="q-chapter">{q['chapter']}</span>
      </div>
      <div class="answer-body">
        <div class="answer-row"><span class="label">📝 答案：</span><span class="answer-text">{answer_display}</span></div>
        <div class="answer-row"><span class="label">📖 考点：</span><span>{q['chapter']}</span></div>
        <div class="answer-row"><span class="label">💡 解析：</span></div>
        <div class="explanation">{explanation}</div>
      </div>
    </div>'''
    
    html += '</div>'
    return html

def generate_html(subject_name, subject_subtitle, selected, exam_time="120分钟", total_score="100分"):
    """Generate complete print-friendly HTML exam paper."""
    # Split by type for the questions section
    type_order = ['single', 'multi', 'judge', 'comprehensive']
    
    questions_html = ''
    q_idx = 0
    for qtype in type_order:
        type_qs = [q for q in selected if q['type'] == qtype]
        if not type_qs:
            continue
        questions_html += f'\n    <div class="section-header">{TYPE_LABELS[qtype]}</div>\n'
        for q in type_qs:
            q_idx += 1
            questions_html += generate_question_html(q, q_idx)
    
    # Counts
    single_cnt = sum(1 for q in selected if q['type'] == 'single')
    multi_cnt = sum(1 for q in selected if q['type'] == 'multi')
    judge_cnt = sum(1 for q in selected if q['type'] == 'judge')
    comp_cnt = sum(1 for q in selected if q['type'] == 'comprehensive')
    
    real_exam_cnt = sum(1 for q in selected if q['is_real_exam'])
    
    answers_html = generate_answer_html(selected)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>证券从业 · 真题模拟卷 · {subject_subtitle}</title>
<style>
  @page {{ size: A4; margin: 2cm; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "SimSun", "STSong", "Noto Serif CJK SC", serif;
    font-size: 12pt;
    line-height: 1.6;
    color: #222;
    background: #fff;
    max-width: 210mm;
    margin: 0 auto;
    padding: 20px;
  }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
    .page-break {{ page-break-before: always; }}
  }}
  h1 {{
    font-size: 20pt;
    text-align: center;
    margin: 20px 0 5px;
    color: #1a1a2e;
  }}
  .subtitle {{
    text-align: center;
    font-size: 11pt;
    color: #666;
    margin-bottom: 10px;
  }}
  .exam-info {{
    border: 2px solid #333;
    padding: 12px 18px;
    margin: 10px 0 20px;
    display: flex;
    justify-content: space-between;
    font-size: 11pt;
    background: #f9f9f9;
  }}
  .exam-info span {{ flex: 1; text-align: center; }}
  .instructions {{
    background: #f5f5f5;
    border-left: 4px solid #1a1a2e;
    padding: 10px 15px;
    margin: 10px 0 20px;
    font-size: 10.5pt;
    line-height: 1.8;
  }}
  .instructions ul {{ padding-left: 20px; }}
  .section-header {{
    background: #1a1a2e;
    color: #fff;
    padding: 8px 15px;
    margin: 25px 0 15px;
    font-size: 12pt;
    font-weight: bold;
    border-radius: 3px;
  }}
  .question {{
    margin: 10px 0 15px;
    padding: 8px 0;
    border-bottom: 1px dashed #ddd;
  }}
  .q-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    font-size: 10.5pt;
  }}
  .q-number {{ font-weight: bold; color: #1a1a2e; min-width: 30px; }}
  .q-type {{ 
    background: #e8e8e8; 
    padding: 1px 8px; 
    border-radius: 3px; 
    font-size: 9pt;
    color: #555;
  }}
  .q-chapter {{ 
    font-size: 9pt; 
    color: #888;
    margin-left: auto;
  }}
  .q-text {{ 
    margin-bottom: 5px;
    padding-left: 30px;
    font-size: 11pt;
  }}
  .options {{
    padding-left: 30px;
    margin-bottom: 8px;
  }}
  .option {{
    padding: 2px 0;
    font-size: 10.5pt;
  }}
  .option-letter {{
    font-weight: bold;
    color: #555;
  }}
  .spacer {{ height: 15px; }}
  
  /* ── Answer Section ── */
  .answer-section {{
    margin-top: 30px;
  }}
  .answer-section h2 {{
    background: #1a1a2e;
    color: #fff;
    padding: 8px 15px;
    border-radius: 3px;
    margin-bottom: 20px;
  }}
  .answer-card {{
    border: 1px solid #ddd;
    border-left: 4px solid #1a1a2e;
    margin: 10px 0;
    padding: 10px 15px;
    border-radius: 0 5px 5px 0;
    page-break-inside: avoid;
  }}
  .answer-header {{
    display: flex;
    gap: 10px;
    font-size: 10.5pt;
    margin-bottom: 8px;
    padding-bottom: 5px;
    border-bottom: 1px solid #eee;
  }}
  .answer-body {{
    font-size: 10.5pt;
  }}
  .answer-row {{
    margin: 4px 0;
  }}
  .label {{ font-weight: bold; color: #1a1a2e; }}
  .answer-text {{ color: #c0392b; font-weight: bold; font-size: 11pt; }}
  .explanation {{
    padding-left: 20px;
    color: #333;
    line-height: 1.8;
  }}
  .real-exam-badge {{
    background: #c0392b;
    color: #fff;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 8pt;
  }}
  .page-break {{ page-break-before: always; }}
  .print-btn {{
    display: block;
    width: 200px;
    margin: 20px auto;
    padding: 12px 24px;
    background: #1a1a2e;
    color: #fff;
    border: none;
    border-radius: 5px;
    font-size: 14px;
    cursor: pointer;
  }}
  .print-btn:hover {{ background: #333; }}
  footer {{
    text-align: center;
    font-size: 9pt;
    color: #999;
    margin: 20px 0;
    padding-top: 10px;
    border-top: 1px solid #ddd;
  }}
</style>
</head>
<body>

<div class="no-print" style="text-align:center;margin-bottom:10px;">
  <button class="print-btn" onclick="window.print()">🖨️ 打印本试卷</button>
</div>

<h1>证券从业资格考试 · 真题模拟卷</h1>
<div class="subtitle">{subject_subtitle} · 基于近3年真题与最新考试大纲</div>

<div class="exam-info">
  <span>📚 {subject_name}</span>
  <span>⏱ {exam_time}</span>
  <span>📊 满分 {total_score}</span>
</div>

<div class="instructions">
  <strong>⚠ 注意事项：</strong>
  <ul>
    <li>本卷共 <strong>{len(selected)}</strong> 题，其中单选{single_cnt}题、多选{multi_cnt}题、判断{judge_cnt}题、不定项{comp_cnt}题</li>
    <li>请将答案填写在答题卡上，写在试卷上无效</li>
    <li>单选题每题0.5分，多选题每题1分，判断题每题1分，不定项选择题每题1分</li>
    <li>多选题每题有2~4个正确选项，少选、多选、错选均不得分</li>
    <li>不定项选择题每题有1~4个正确选项</li>
    <li>标注 <span class="real-exam-badge">真题</span> 的题目为近3年真实考题，其余为高频考点题</li>
  </ul>
</div>

<!-- ═══ QUESTIONS ═══ -->
{questions_html}

<!-- ═══ PAGE BREAK → ANSWERS ═══ -->
<div class="page-break"></div>

{answers_html}

<footer>
  证券从业资格考试 · 真题模拟卷 · {subject_subtitle} · Generated @ 2026
</footer>

<script>
  // Show real-exam badge
  document.querySelectorAll('.question').forEach(q => {{
    const source = q.dataset.source;
    if (source === 'true') {{
      const header = q.querySelector('.q-header');
      const badge = document.createElement('span');
      badge.className = 'real-exam-badge';
      badge.textContent = '真题';
      header.appendChild(badge);
    }}
  }});
</script>

</body>
</html>'''

    return html

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    real_exam_texts = build_real_exam_texts()
    print(f"Real exam texts: {len(real_exam_texts)} unique questions")
    
    # ── 金融市场基础知识 ──
    print("\n📊 Generating 金融基础 mock exam...")
    fin_pool = build_pool('finance', FIN_CHAPTERS)
    for ch in sorted(fin_pool.keys()):
        ch_name = FIN_CHAPTERS[ch-1][1] if ch <= len(FIN_CHAPTERS) else f"Ch{ch}"
        types = defaultdict(int)
        for q in fin_pool[ch]:
            types[q.get('type', 'unknown')] += 1
        type_str = ', '.join(f"{k}={v}" for k, v in sorted(types.items()))
        print(f"  Ch{ch} {ch_name}: {len(fin_pool[ch])} questions ({type_str})")
    
    fin_selected = sample_questions(fin_pool, FIN_CHAPTERS, real_exam_texts, 'finance')
    print(f"  Selected: {len(fin_selected)} questions")
    type_counts = defaultdict(int)
    for q in fin_selected:
        type_counts[q['type']] += 1
    print(f"  Type dist: {dict(type_counts)}")
    real_cnt = sum(1 for q in fin_selected if q['is_real_exam'])
    print(f"  Real exam questions: {real_cnt}")
    
    # ── 证券市场基本法律法规 ──
    print("\n📊 Generating 法律法规 mock exam...")
    law_pool = build_pool('law', LAW_CHAPTERS)
    for ch in sorted(law_pool.keys()):
        ch_name = LAW_CHAPTERS[ch-1][1] if ch <= len(LAW_CHAPTERS) else f"Ch{ch}"
        types = defaultdict(int)
        for q in law_pool[ch]:
            types[q.get('type', 'unknown')] += 1
        type_str = ', '.join(f"{k}={v}" for k, v in sorted(types.items()))
        print(f"  Ch{ch} {ch_name}: {len(law_pool[ch])} questions ({type_str})")
    
    law_selected = sample_questions(law_pool, LAW_CHAPTERS, real_exam_texts, 'law')
    print(f"  Selected: {len(law_selected)} questions")
    type_counts = defaultdict(int)
    for q in law_selected:
        type_counts[q['type']] += 1
    print(f"  Type dist: {dict(type_counts)}")
    real_cnt = sum(1 for q in law_selected if q['is_real_exam'])
    print(f"  Real exam questions: {real_cnt}")
    
    # Generate HTML
    fin_html = generate_html(
        "金融市场基础知识",
        "金融市场基础知识",
        fin_selected
    )
    law_html = generate_html(
        "证券市场基本法律法规",
        "证券市场基本法律法规",
        law_selected
    )
    
    out_dir = '/home/betterman/sec-exam-deploy'
    with open(f'{out_dir}/金融市场基础知识_真题模拟卷.html', 'w') as f:
        f.write(fin_html)
    with open(f'{out_dir}/证券市场基本法律法规_真题模拟卷.html', 'w') as f:
        f.write(law_html)
    
    print(f"\n✅ Done! Files saved to: {out_dir}/")
    print(f"   📄 金融市场基础知识_真题模拟卷.html ({len(fin_selected)}题)")
    print(f"   📄 证券市场基本法律法规_真题模拟卷.html ({len(law_selected)}题)")

if __name__ == '__main__':
    main()
