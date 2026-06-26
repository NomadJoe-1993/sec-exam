#!/usr/bin/env python3
"""
证券从业 · 真题模拟卷生成器 v3 — 修复版
核心修复：不再相信数据源的type字段，而是根据答案格式推断真实题型
"""

import json, re, os, random
from collections import defaultdict, Counter
from copy import deepcopy

random.seed(42)

SRC = '/home/betterman/233_crawler/integrated'
DEST = '/home/betterman/sec-exam-deploy'

FIN_CHAPTERS = [
    (1, "第1章", "金融市场体系",               0.08),
    (2, "第2章", "中国的金融体系与多层次资本市场", 0.12),
    (3, "第3章", "证券市场主体",               0.10),
    (4, "第4章", "股票",                     0.20),
    (5, "第5章", "债券",                     0.15),
    (6, "第6章", "证券投资基金",              0.15),
    (7, "第7章", "金融衍生工具",              0.12),
    (8, "第8章", "金融风险管理",              0.08),
]
LAW_CHAPTERS = [
    (1, "第1章", "证券市场基本法律法规",         0.35),
    (2, "第2章", "证券经营机构管理规范",         0.20),
    (3, "第3章", "证券公司业务规范",            0.30),
    (4, "第4章", "典型违法违规行为及法律责任",   0.10),
    (5, "第5章", "行业文化与职业道德",          0.05),
]
TARGET = {'single': 40, 'multi': 40, 'judge': 30, 'comprehensive': 10}

TYPE_CN = {'single': '单选题', 'multi': '多选题', 'judge': '判断题', 'comprehensive': '不定项选择题'}
TYPE_LABELS = {
    'single': '一、单项选择题（共40题，每题0.5分，共20分）',
    'multi':  '二、多项选择题（共40题，每题1分，共40分）',
    'judge':  '三、判断题（共30题，每题1分，共30分）',
    'comprehensive': '四、不定项选择题（共10题，每题1分，共10分）',
}

def load_data():
    with open(f'{SRC}/final_merged.json') as f:
        fm = json.load(f)
    with open(f'{SRC}/merged_data.json') as f:
        md = json.load(f)
    with open(f'{DEST}/real_exam_data.json') as f:
        rex = json.load(f)
    real_stems = set()
    for pname, plist in rex['papers'].items():
        for q in plist:
            s = q.get('stem', q.get('q', ''))
            real_stems.add(re.sub(r'\s+', '', s))
    return fm, md, real_stems


def load_extra_comp(subject):
    subj_name = '金融基础' if subject == 'finance' else '法律法规'
    extra = []
    for fname in sorted(os.listdir(DEST)):
        if fname.startswith(f'sprint_{subj_name}') and '不定项' in fname and fname.endswith('.json'):
            with open(f'{DEST}/{fname}') as f:
                data = json.load(f)
            extra.extend(data.get('questions', []))
    return extra


def infer_true_type(q):
    """
    Infer the TRUE question type from the answer format, not from the data's type field.
    Rules:
    - If answer is 'A'/'B'/'C'/'D' alone → single
    - If answer has commas (A,B,C) or multiple letters (ABC, ABCD) → multi
    - If answer is '对'/'错'/'√'/'×'/'B'/'A' (with options 对/错) → judge
    - If answer has both comma AND multiple letters → comprehensive or multi
    """
    ans = q.get('a', '').strip()
    source_type = q.get('type', 'single')
    q_text = q.get('q', '')
    
    # Check if options indicate judge format (对/错)
    opts = q.get('c', {})
    opt_keys = list(opts.keys())
    
    # Check for judge-type options
    if set(opt_keys) <= {'A', 'B'} and any(k in str(opts.get(k, '')) for k in opt_keys for term in ['对', '错', '√', '×', '正确', '错误']):
        is_judge_opts = True
        for k in opt_keys:
            v = str(opts.get(k, ''))
            if '对' not in v and '错' not in v and '√' not in v and '×' not in v and '正确' not in v and '错误' not in v:
                is_judge_opts = False
                break
        if is_judge_opts:
            return 'judge'
    
    # If options are just 'A.对 B.错', it's judge
    if len(opt_keys) <= 2:
        vals = [str(opts.get(k, '')) for k in opt_keys]
        if any('对' in v or '错' in v or '√' in v or '×' in v or '正确' in v or '错误' in v for v in vals):
            if all(v in ['对', '错', '正确', '错误', '√', '×', ''] or v.startswith('对') or v.startswith('错') for v in vals):
                return 'judge'
    
    # Check answer format
    if ans in ('A', 'B', 'C', 'D'):
        return 'single'
    
    if ans in ('对', '错', '正确', '错误', '√', '×'):
        return 'judge'
    
    # Multi-letter answer (ABC, ABCD, AB, etc.) or comma-separated (A,B,C)
    clean_ans = ans.replace(',', '').replace('、', '').replace(' ', '')
    if len(clean_ans) >= 2:
        if all(c in 'ABCD' for c in clean_ans):
            return 'multi'
    
    # With commas
    if ',' in ans or '、' in ans:
        parts = [p.strip() for p in ans.replace('、', ',').split(',')]
        if all(p in 'ABCD' for p in parts):
            return 'multi'
    
    # Fall back to source type
    return source_type


def chapter_from_id(qid):
    m = re.search(r'zc_ch(\d+)', qid)
    if m: return int(m.group(1))
    m = re.search(r'zc_fl(\d+)[a-z]?', qid)
    if m: return int(m.group(1))
    return None


def norm(t):
    return re.sub(r'\s+', '', t)[:60]


def build_pool(subject, chapters):
    """Build clean question pool. Reclassify types based on actual answer."""
    fm, md, real_stems = load_data()
    prefix = 'ch' if subject == 'finance' else 'fl'
    
    all_qs = []
    seen_ids = set()
    
    for src in [fm.get(subject, {}).get('questions', []),
                md.get(subject, {}).get('questions', [])]:
        for q in src:
            if q['id'] not in seen_ids:
                seen_ids.add(q['id'])
                qc = deepcopy(q)
                # Reclassify type
                true_type = infer_true_type(qc)
                qc['true_type'] = true_type
                all_qs.append(qc)
    
    # Also from zc files
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
                    if isinstance(c, list) or 'options' in q:
                        opts = q.get('options', q.get('c', []))
                        c_dict = {}
                        for o in opts:
                            m = re.match(r'^([A-D])[.、]?\s*(.*)', str(o))
                            if m: c_dict[m.group(1)] = m.group(2)
                        c = c_dict
                    qc = {
                        'id': qid, 'q': q.get('q', q.get('stem', '')),
                        'c': c, 'a': q.get('a', q.get('answer', '')),
                        'an': q.get('an', q.get('explanation', '')),
                        'type': q.get('type', 'single'),
                    }
                    qc['true_type'] = infer_true_type(qc)
                    all_qs.append(qc)
    
    # Extra comprehensive from sprint
    extra_comp = load_extra_comp(subject)
    for q in extra_comp:
        qid = f"sprint_{q['id']}"
        if qid not in seen_ids:
            seen_ids.add(qid)
            q['id'] = qid
            q['source'] = 'sprint'
            q['true_type'] = 'comprehensive'
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
    if unk:
        for i, q in enumerate(unk):
            ch = (i % len(chapters)) + 1
            by_ch[ch].append(q)
    
    return by_ch


def allocate_by_weight(chapters):
    alloc = {}
    for ch_num, ch_code, ch_name, weight in chapters:
        alloc[ch_num] = {}
        for qtype, target in TARGET.items():
            alloc[ch_num][qtype] = max(1, round(target * weight))
    for qtype in TARGET:
        total = sum(a[qtype] for a in alloc.values())
        diff = TARGET[qtype] - total
        if diff > 0:
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
    by_ch = build_pool(subject, chapters)
    alloc = allocate_by_weight(chapters)
    _, _, real_stems = load_data()
    selected = []
    seen_questions = set()
    
    for ch_num, ch_code, ch_name, weight in chapters:
        pool = by_ch.get(ch_num, [])
        for qtype, needed in alloc[ch_num].items():
            # Filter by TRUE type (reclassified)
            type_pool = [q for q in pool if q.get('true_type') == qtype]
            
            if len(type_pool) < needed:
                print(f"  ⚠ {ch_name} {TYPE_CN[qtype]}: 池中{len(type_pool)}不足{needed}，尝试放宽条件")
                # Fall back to source type
                fallback = [q for q in pool if q.get('type') == qtype and q not in type_pool]
                type_pool.extend(fallback)
            
            scored = []
            for q in type_pool:
                qn = norm(q['q'])
                if qn in seen_questions:
                    continue
                score = 0
                for rs in real_stems:
                    if rs in qn or qn in rs:
                        score += 20
                        break
                score += min(5, len(q.get('an', '')) / 100)
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
                    'type': qtype,  # use RE-CLASSIFIED type
                    'q': q['q'],
                    'c': q.get('c', {}),
                    'a': q.get('a', ''),
                    'an': q.get('an', ''),
                    'chapter': f"{ch_code} {ch_name}",
                    'is_real_exam': is_real,
                })
                taken += 1
            
            if taken < needed:
                print(f"  ✗ {ch_name} {TYPE_CN[qtype]}: 仅取到{taken}/{needed}")
    
    return selected


def fmt_q(q, idx):
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
    html = '<div class="ans-section">\n<h2>📋 参考答案与详细解析</h2>\n'
    for qtype in ['single','multi','judge','comprehensive']:
        subset = [q for q in selected if q['type'] == qtype]
        if not subset: continue
        tn = TYPE_CN[qtype]
        html += f'\n    <div class="sh" style="margin-top:10px">{tn} 答案</div>\n'
        for idx, q in enumerate(subset, 1):
            ans = q['a']
            if q['type'] == 'judge':
                ans_display = '✓ 正确' if ans in ('B','对','√','正确') else '✗ 错误'
            elif q['type'] == 'single':
                ans_display = ans
            elif q['type'] == 'multi':
                clean = ans.replace('、', ',').replace(' ', '')
                if ',' not in clean and len(clean) > 1:
                    ans_display = ','.join(list(clean))
                else:
                    ans_display = ans
            else:
                ans_display = ans
            
            label = '真题' if q['is_real_exam'] else '高频考点'
            bg = '#c0392b' if q['is_real_exam'] else '#888'
            html += f'''
    <div class="ac">
      <div class="ah">
        <span class="qn">第{idx}题</span>
        <span class="qt" style="background:{bg};color:#fff;padding:1px 8px;border-radius:3px;font-size:9pt">{label}</span>
        <span class="qt" style="background:#e8e8e8;padding:1px 8px;border-radius:3px;font-size:9pt;color:#555">{tn}</span>
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
    qs_html = ''
    for qtype in ['single','multi','judge','comprehensive']:
        subset = [q for q in selected if q['type'] == qtype]
        if not subset: continue
        qs_html += f'\n    <div class="sh">{TYPE_LABELS[qtype]}</div>\n'
        for idx, q in enumerate(subset, 1):
            qs_html += fmt_q(q, idx)
    
    ans_html = fmt_answers(selected)
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
    fm, md, _ = load_data()
    
    # Pre-check: show reclassification stats
    print("📊 题型重分类统计（按答案格式推断真实题型）\n")
    for subject, chapters, subj_name in [
        ('finance', FIN_CHAPTERS, '金融市场基础知识'),
        ('law', LAW_CHAPTERS, '证券市场基本法律法规'),
    ]:
        by_ch = build_pool(subject, chapters)
        all_qs = []
        for qs in by_ch.values():
            all_qs.extend(qs)
        
        orig = Counter(q.get('type') for q in all_qs)
        truth = Counter(q.get('true_type') for q in all_qs)
        
        print(f'{subj_name}:')
        print(f'  原始type分布: {dict(orig)}')
        print(f'  重分类true_type: {dict(truth)}')
        
        # Show examples of reclassified questions
        reclassified = [q for q in all_qs if q.get('type') != q.get('true_type')]
        print(f'  被重分类的题数: {len(reclassified)}')
        for q in reclassified[:5]:
            print(f'    {q["id"]}: type={q["type"]} → {q["true_type"]}, ans="{q["a"]}"')
        print()
    
    print("📊 开始生成真题模拟卷...\n")
    
    for subject, chapters, subj_name in [
        ('finance', FIN_CHAPTERS, '金融市场基础知识'),
        ('law', LAW_CHAPTERS, '证券市场基本法律法规'),
    ]:
        print(f"▶ {subj_name}")
        selected = sample(subject, chapters)
        print(f"  已选: {len(selected)} 题")
        tc = Counter(q['type'] for q in selected)
        print(f"  题型: 单{tc['single']} 多{tc['multi']} 判{tc['judge']} 不{tc['comprehensive']}")
        print(f"  真题: {sum(1 for q in selected if q['is_real_exam'])} 题")
        
        # Verify: no单选题应有多个答案
        errors = [q for q in selected if q['type'] == 'single' and (',' in q['a'] or '、' in q['a'] or len(q['a']) > 1)]
        if errors:
            print(f"  ⚠ 错误：{len(errors)}道单选题答案异常！")
            for e in errors:
                print(f"    第{e['id']}题 ans={e['a']}")
        else:
            print(f"  ✅ 单选题答案格式全部正确")
        
        html = gen_html(subj_name, selected)
        fname = f'{subj_name}_真题模拟卷.html'
        with open(f'{DEST}/{fname}', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  ✅ {fname}\n")
    
    print("✅ 完成！")


if __name__ == '__main__':
    main()
