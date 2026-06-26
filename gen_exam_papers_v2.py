#!/usr/bin/env python3
"""
证券从业资格考试 · 真题模拟卷生成器
生成两份打印友好的HTML模拟卷:
  金融市场基础知识（40单选+40多选+30判断+10不定项）
  证券市场基本法律法规（40单选+40多选+30判断+10不定项）
"""

import json, re, os, random
from collections import defaultdict
from copy import deepcopy

random.seed(42)

SRC = '/home/betterman/233_crawler/integrated'
DEST = '/home/betterman/sec-exam-deploy'

# ── Chapter config ──────────────────────────────────────────────────────────
FIN_CHAPTERS = [
    (1,  "第1章", "金融市场体系",               0.08),
    (2,  "第2章", "中国的金融体系与多层次资本市场", 0.12),
    (3,  "第3章", "证券市场主体",               0.10),
    (4,  "第4章", "股票",                     0.20),
    (5,  "第5章", "债券",                     0.15),
    (6,  "第6章", "证券投资基金",              0.15),
    (7,  "第7章", "金融衍生工具",              0.12),
    (8,  "第8章", "金融风险管理",              0.08),
]
LAW_CHAPTERS = [
    (1,  "第1章", "证券市场基本法律法规",         0.35),
    (2,  "第2章", "证券经营机构管理规范",         0.20),
    (3,  "第3章", "证券公司业务规范",            0.30),
    (4,  "第4章", "典型违法违规行为及法律责任",   0.10),
    (5,  "第5章", "行业文化与职业道德",          0.05),
]
TARGET = {'single': 40, 'multi': 40, 'judge': 30, 'comprehensive': 10}

TYPE_LABELS = {
    'single': '一、单项选择题（共40题，每题0.5分，共20分）',
    'multi':  '二、多项选择题（共40题，每题1分，共40分）',
    'judge':  '三、判断题（共30题，每题1分，共30分）',
    'comprehensive': '四、不定项选择题（共10题，每题1分，共10分）',
}
TYPE_CN = {'single': '单选题', 'multi': '多选题', 'judge': '判断题', 'comprehensive': '不定项选择题'}

# ── Helpers ──────────────────────────────────────────────────────────────────
def load_data():
    """Load all data sources."""
    with open(f'{SRC}/final_merged.json') as f:
        fm = json.load(f)
    with open(f'{SRC}/merged_data.json') as f:
        md = json.load(f)
    with open(f'{DEST}/real_exam_data.json') as f:
        rex = json.load(f)

    # Real exam stems for marking
    real_stems = set()
    for pname, plist in rex['papers'].items():
        for q in plist:
            s = q.get('stem', q.get('q', ''))
            real_stems.add(re.sub(r'\s+', '', s))

    return fm, md, real_stems


def load_extra_comp(subject):
    """Load sprint_不定项 questions for a subject."""
    subj_name = '金融基础' if subject == 'finance' else '法律法规'
    extra = []
    for fname in sorted(os.listdir(DEST)):
        if fname.startswith(f'sprint_{subj_name}') and '不定项' in fname and fname.endswith('.json'):
            with open(f'{DEST}/{fname}') as f:
                data = json.load(f)
            extra.extend(data.get('questions', []))
    return extra


def chapter_from_id(qid):
    """Extract chapter number from question ID."""
    m = re.search(r'zc_ch(\d+)', qid)
    if m: return int(m.group(1))
    m = re.search(r'zc_fl(\d+)[a-z]?', qid)
    if m: return int(m.group(1))
    return None


def norm(t):
    return re.sub(r'\s+', '', t)[:60]


def build_pool(subject, chapters):
    """Build question pool organized by chapter."""
    fm, md, real_stems = load_data()
    prefix = 'ch' if subject == 'finance' else 'fl'
    
    all_qs = []
    seen_ids = set()
    
    # Combine from final_merged and merged_data
    for src in [fm.get(subject, {}).get('questions', []),
                md.get(subject, {}).get('questions', [])]:
        for q in src:
            if q['id'] not in seen_ids:
                seen_ids.add(q['id'])
                all_qs.append(deepcopy(q))
    
    # Also from zc files in sec-exam-check
    zc_dir = '/home/betterman/sec-exam-check'
    for fname in sorted(os.listdir(zc_dir)):
        if fname.startswith(f'zc_{prefix}') and fname.endswith('.json'):
            with open(f'{zc_dir}/{fname}') as f:
                zc_data = json.load(f)
            for q in zc_data.get('questions', []):
                qid = f"zc_{fname.replace('.json','')}_{q['id']}"
                if qid not in seen_ids:
                    seen_ids.add(qid)
                    c = q.get('c', {})
                    # Handle list-style options
                    if isinstance(c, list) or 'options' in q:
                        opts = q.get('options', q.get('c', []))
                        c_dict = {}
                        for o in opts:
                            m = re.match(r'^([A-D])[.、]?\s*(.*)', str(o))
                            if m: c_dict[m.group(1)] = m.group(2)
                        c = c_dict
                    all_qs.append({
                        'id': qid,
                        'q': q.get('q', q.get('stem', '')),
                        'c': c,
                        'a': q.get('a', q.get('answer', '')),
                        'an': q.get('an', q.get('explanation', '')),
                        'type': q.get('type', 'single'),
                        'source': 'cflue',
                    })
    
    # Extra comprehensive questions from sprint files
    extra_comp = load_extra_comp(subject)
    for q in extra_comp:
        qid = f"sprint_{q['id']}"
        if qid not in seen_ids:
            seen_ids.add(qid)
            q['id'] = qid
            q['source'] = 'sprint'
            all_qs.append(q)
    
    # Distribute by chapter
    by_ch = defaultdict(list)
    unk = []
    for q in all_qs:
        ch = chapter_from_id(q['id'])
        if ch and 1 <= ch <= len(chapters):
            by_ch[ch].append(q)
        else:
            unk.append(q)
    
    # Spread unknowns evenly
    if unk:
        for i, q in enumerate(unk):
            ch = (i % len(chapters)) + 1
            by_ch[ch].append(q)
    
    return by_ch


def allocate_by_weight(chapters):
    """Allocate questions per chapter by type and weight."""
    alloc = {}
    for ch_num, ch_code, ch_name, weight in chapters:
        alloc[ch_num] = {}
        for qtype, target in TARGET.items():
            alloc[ch_num][qtype] = max(1, round(target * weight))
    
    # Adjust to hit exact targets
    for qtype in TARGET:
        total = sum(a[qtype] for a in alloc.values())
        diff = TARGET[qtype] - total
        if diff > 0:
            # Add to chapters with room (sorted by current count / weight ratio)
            while diff > 0:
                sorted_ch = sorted([(c, a) for c, a in alloc.items()],
                                   key=lambda x: x[1][qtype] / chapters[x[0]-1][3])
                alloc[sorted_ch[0][0]][qtype] += 1
                diff -= 1
        elif diff < 0:
            while diff < 0:
                sorted_ch = sorted([(c, a) for c, a in alloc.items()],
                                   key=lambda x: -x[1][qtype])
                for c, a in sorted_ch:
                    if a[qtype] > 1:
                        a[qtype] -= 1
                        diff += 1
                        break
    
    return alloc


def sample(subject, chapters):
    """Sample 120 questions for one mock exam paper."""
    by_ch = build_pool(subject, chapters)
    alloc = allocate_by_weight(chapters)
    _, _, real_stems = load_data()
    
    selected = []
    seen_questions = set()
    
    for ch_num, ch_code, ch_name, weight in chapters:
        pool = by_ch.get(ch_num, [])
        for qtype, needed in alloc[ch_num].items():
            # Filter by type, dedup
            type_pool = [q for q in pool if q.get('type') == qtype]
            # Score: prefer real stems match, detailed explanations, longer answers
            scored = []
            for q in type_pool:
                qn = norm(q['q'])
                if qn in seen_questions:
                    continue
                score = 0
                # Real exam match
                for rs in real_stems:
                    if rs in qn or qn in rs:
                        score += 20
                        break
                # Prefer longer explanations (more detailed)
                score += min(5, len(q.get('an', '')) / 100)
                # Prefer comprehensive from sprint (they have the right format)
                if q.get('source') == 'sprint' and qtype == 'comprehensive':
                    score += 3
                elif 'cflue' in q.get('id', ''):
                    score += 2
                scored.append((score, q))
            
            scored.sort(key=lambda x: -x[0])
            
            taken = 0
            for score, q in scored:
                if taken >= needed:
                    break
                qn = norm(q['q'])
                if qn in seen_questions:
                    continue
                seen_questions.add(qn)
                is_real = any(rs in qn or qn in rs for rs in real_stems)
                selected.append({
                    'id': len(selected) + 1,
                    'type': qtype,
                    'q': q['q'],
                    'c': q.get('c', {}),
                    'a': q.get('a', ''),
                    'an': q.get('an', ''),
                    'chapter': f"{ch_code} {ch_name}",
                    'is_real_exam': is_real,
                })
                taken += 1
            
            if taken < needed:
                print(f"  ⚠ WARN: {ch_name} {TYPE_CN[qtype]}: need {needed}, got {taken}")
    
    return selected


def fmt_q(q, idx):
    """Format a single question as HTML."""
    opts = q.get('c', {})
    opts_html = ''
    for L in ['A','B','C','D','E','F']:
        if L in opts:
            opts_html += f'<div class="opt"><span class="opt-l">{L}.</span>{opts[L]}</div>'
    
    tn = TYPE_CN[q['type']]
    label = '真题' if q['is_real_exam'] else '高频考点'
    bg = '#c0392b' if q['is_real_exam'] else '#888'
    
    return f'''
    <div class="q" data-type="{q['type']}">
      <div class="qh">
        <span class="qn">{idx}.</span>
        <span class="qt" style="background:{bg};color:#fff;padding:1px 8px;border-radius:3px;font-size:9pt">{label}</span>
        <span class="qt" style="background:#e8e8e8;padding:1px 8px;border-radius:3px;font-size:9pt;color:#555">{tn}</span>
        <span class="qc" style="font-size:9pt;color:#999;margin-left:auto">{q['chapter']}</span>
      </div>
      <div class="qtxt">{q['q']}</div>
      <div class="opts">{opts_html}</div>
    </div>'''


def fmt_answers(selected):
    """Format answer key with detailed解析."""
    html = '<div class="ans-section">\n<h2>📋 参考答案与详细解析</h2>\n'
    for q in selected:
        ans = q['a']
        if q['type'] == 'judge':
            ans_display = '✓ 正确' if ans in ('B','对','√') else '✗ 错误'
        else:
            ans_display = ans
        
        label = '真题' if q['is_real_exam'] else '高频考点'
        bg = '#c0392b' if q['is_real_exam'] else '#888'
        
        html += f'''
    <div class="ac">
      <div class="ah">
        <span class="qn">第{q['id']}题</span>
        <span class="qt" style="background:{bg};color:#fff;padding:1px 8px;border-radius:3px;font-size:9pt">{label}</span>
        <span class="qt" style="background:#e8e8e8;padding:1px 8px;border-radius:3px;font-size:9pt;color:#555">{TYPE_CN[q['type']]}</span>
        <span class="qc" style="font-size:9pt;color:#999;margin-left:auto">{q['chapter']}</span>
      </div>
      <div class="ab">
        <div><b>📝 答案：</b><span style="color:#c0392b;font-weight:bold">{ans_display}</span></div>
        <div><b>📖 考点：</b>{q['chapter']}</div>
        <div><b>💡 解析：</b></div>
        <div class="exp">{q['an']}</div>
      </div>
    </div>'''
    html += '</div>'
    return html


def gen_html(title, selected):
    """Generate print-friendly HTML exam paper."""
    qs_html = ''
    for qtype in ['single','multi','judge','comprehensive']:
        subset = [q for q in selected if q['type'] == qtype]
        if not subset: continue
        qs_html += f'\n    <div class="sh">{TYPE_LABELS[qtype]}</div>\n'
        for idx, q in enumerate(subset, 1):
            qs_html += fmt_q(q, idx)
    
    ans_html = fmt_answers(selected)
    
    real_cnt = sum(1 for q in selected if q['is_real_exam'])
    total = len(selected)
    type_cnt = ' + '.join(f'{sum(1 for q in selected if q["type"]==t)}{TYPE_CN[t][0]}' 
                          for t in ['single','multi','judge','comprehensive'])
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>证券从业 · 真题模拟卷 · {title}</title>
<style>
  @page {{ size: A4; margin: 2cm; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:"SimSun","STSong","Noto Serif CJK SC",serif; font-size:12pt; line-height:1.6; color:#222; background:#fff; max-width:210mm; margin:0 auto; padding:20px; }}
  @media print {{ body {{ padding:0; }} .np {{ display:none; }} .pb {{ page-break-before:always; }} }}
  h1 {{ font-size:20pt; text-align:center; margin:20px 0 5px; color:#1a1a2e; }}
  .sub {{ text-align:center; font-size:11pt; color:#666; margin-bottom:10px; }}
  .ei {{ border:2px solid #333; padding:12px 18px; margin:10px 0 20px; display:flex; justify-content:space-between; font-size:11pt; background:#f9f9f9; }}
  .ei span {{ flex:1; text-align:center; }}
  .ins {{ background:#f5f5f5; border-left:4px solid #1a1a2e; padding:10px 15px; margin:10px 0 20px; font-size:10.5pt; line-height:1.8; }}
  .ins ul {{ padding-left:20px; }}
  .sh {{ background:#1a1a2e; color:#fff; padding:8px 15px; margin:25px 0 15px; font-size:12pt; font-weight:bold; border-radius:3px; }}
  .q {{ margin:10px 0 12px; padding:6px 0; border-bottom:1px dashed #ddd; }}
  .qh {{ display:flex; align-items:center; gap:6px; margin-bottom:4px; font-size:10.5pt; }}
  .qn {{ font-weight:bold; color:#1a1a2e; min-width:28px; }}
  .qtxt {{ margin-bottom:4px; padding-left:30px; font-size:11pt; }}
  .opts {{ padding-left:30px; }}
  .opt {{ padding:2px 0; font-size:10.5pt; }}
  .opt-l {{ font-weight:bold; color:#555; margin-right:4px; }}
  .ans-section {{ margin-top:30px; }}
  .ans-section h2 {{ background:#1a1a2e; color:#fff; padding:8px 15px; border-radius:3px; margin-bottom:20px; }}
  .ac {{ border:1px solid #ddd; border-left:4px solid #1a1a2e; margin:10px 0; padding:10px 15px; border-radius:0 5px 5px 0; page-break-inside:avoid; }}
  .ah {{ display:flex; gap:10px; font-size:10.5pt; margin-bottom:8px; padding-bottom:5px; border-bottom:1px solid #eee; }}
  .ab {{ font-size:10.5pt; }}
  .ab div {{ margin:4px 0; }}
  .exp {{ padding-left:20px; color:#333; line-height:1.8; }}
  .pb {{ page-break-before:always; }}
  .pb {{ page-break-before:always; }}
  .btn {{ display:block; width:200px; margin:20px auto; padding:12px 24px; background:#1a1a2e; color:#fff; border:none; border-radius:5px; font-size:14px; cursor:pointer; }}
  .btn:hover {{ background:#333; }}
  footer {{ text-align:center; font-size:9pt; color:#999; margin:20px 0; padding-top:10px; border-top:1px solid #ddd; }}
</style>
</head>
<body>

<div class="np" style="text-align:center;margin-bottom:10px;">
  <button class="btn" onclick="window.print()">🖨️ 打印本试卷</button>
</div>

<h1>证券从业资格考试 · 真题模拟卷</h1>
<div class="sub">{title}</div>
<div class="sub" style="font-size:10pt;color:#999">基于近3年真题题库与2025最新考试大纲 · 含详细解析与考点标注</div>

<div class="ei">
  <span>📚 {title}</span>
  <span>⏱ 120分钟</span>
  <span>📊 满分100分</span>
</div>

<div class="ins">
  <strong>⚠ 注意事项：</strong>
  <ul>
    <li>本卷共 <strong>{total}</strong> 题：{type_cnt}</li>
    <li>单选题每题0.5分，多选题/判断题/不定项选择题每题1分</li>
    <li>多选题有2~4个正确选项，少选多选错选均不得分；不定项选择题有1~4个正确选项</li>
    <li>标注 <span style="background:#c0392b;color:#fff;padding:1px 6px;border-radius:3px;font-size:8pt">真题</span> 的为近3年真实考题</li>
    <li>标注 <span style="background:#888;color:#fff;padding:1px 6px;border-radius:3px;font-size:8pt">高频考点</span> 的为233网校/冲呀刷题高频考点题</li>
    <li>请将答案填写在答题纸上，本卷仅供模拟考试使用</li>
  </ul>
</div>

{qs_html}

<div style="text-align:center;margin:30px 0;font-size:12pt;color:#1a1a2e;">
  <strong>— 试卷结束 · 请检查后交卷 —</strong>
</div>

<div class="pb"></div>

{ans_html}

<footer>
  证券从业资格考试 · 真题模拟卷 · {title} · Generated @ 2026-06
</footer>

</body>
</html>'''


def main():
    print("📊 开始生成真题模拟卷...\n")
    
    for subject, chapters, subj_name in [
        ('finance', FIN_CHAPTERS, '金融市场基础知识'),
        ('law', LAW_CHAPTERS, '证券市场基本法律法规'),
    ]:
        print(f"▶ {subj_name}")
        selected = sample(subject, chapters)
        print(f"  已选: {len(selected)} 题")
        
        # Type stats
        tc = defaultdict(int)
        for q in selected:
            tc[q['type']] += 1
        print(f"  题型: 单选{tc['single']} 多选{tc['multi']} 判断{tc['judge']} 不定项{tc['comprehensive']}")
        print(f"  真题: {sum(1 for q in selected if q['is_real_exam'])} 题")
        
        html = gen_html(subj_name, selected)
        fname = f'{subj_name}_真题模拟卷.html'
        with open(f'{DEST}/{fname}', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  ✅ {fname}\n")
    
    print("✅ 完成！文件位于 sec-exam-deploy/")


if __name__ == '__main__':
    main()
