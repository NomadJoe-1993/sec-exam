#!/usr/bin/env python3
"""Generate 章节精练 with section (小节) level breakdown."""
import re, json

# ====== 0. READ ORIGINAL FILES FIRST ======
ORIG_DIR = '.'  # current dir

def parse_chapter_practice(filepath):
    with open(filepath) as f:
        content = f.read()
    m = re.search(r'var CHAPTERS\s*=\s*(\[[^\]]+\])\s*;', content, re.DOTALL)
    chapters = json.loads(m.group(1)) if m else []
    m = re.search(r'var CH_MAP\s*=\s*(\[[^\]]+\])\s*;', content, re.DOTALL)
    ch_map = json.loads(m.group(1)) if m else []
    m = re.search(r'var ALL_QUESTIONS\s*=\s*(\[.*?\])\s*;', content, re.DOTALL)
    all_q = json.loads(m.group(1)) if m else []
    m = re.search(r"var SUBJECT\s*=\s*\"([^\"]+)\"", content)
    subject = m.group(1) if m else ''
    m = re.search(r"var STORAGE_KEY\s*=\s*'([^']+)'", content)
    storage_key = m.group(1) if m else ''
    return {'chapters': chapters, 'ch_map': ch_map, 'questions': all_q,
            'subject': subject, 'storage_key': storage_key}

fin_data = parse_chapter_practice('章节精练_金融市场基础.html')
law_data = parse_chapter_practice('章节精练_法律法规.html')
print(f"读取原始数据: 金融基础 {len(fin_data['questions'])}题 {len(fin_data['chapters'])}章, 法律法规 {len(law_data['questions'])}题 {len(law_data['chapters'])}章")

# ====== 1. Parse section structure from 备考全景 HTML ======
with open('/mnt/c/Users/34558/Desktop/证券从业_备考全景系统.html') as f:
    panorama = f.read()

tabs = re.split(r'<div class="tab-content[^"]*" id="(tab[01])">', panorama)
tab_contents = {}
for i in range(1, len(tabs)-1, 2):
    tab_contents[tabs[i]] = tabs[i+1]

def parse_sections_from_html(html_content):
    chapters = []
    chapter_blocks = re.findall(
        r'<div class="chapter">(.*?)(?=</div>\s*(?:<div class="chapter">|</div>\s*<div class="card))',
        html_content, re.DOTALL
    )
    for block in chapter_blocks:
        ch_m = re.search(r'<span class="name">([^<]+)</span>', block)
        if not ch_m:
            continue
        ch_name = ch_m.group(1).strip()
        secs = []
        for sec_m in re.finditer(
            r'<span class="sname">(第[^<]+节[^<]+)</span><span class="scount">(\d+)题</span>', block
        ):
            secs.append({'name': sec_m.group(1).strip(), 'count': int(sec_m.group(2))})
        if secs:
            chapters.append({'chapter': ch_name, 'sections': secs})
    return chapters

sections = {}
for tab_id, section_key in [('tab0', 'fin'), ('tab1', 'law')]:
    if tab_id in tab_contents:
        sections[section_key] = parse_sections_from_html(tab_contents[tab_id])
        print(f"{section_key}: {len(sections[section_key])}章 {sum(len(c['sections']) for c in sections[section_key])}节")

# ====== 2. Map sections to question ranges ======
def map_sections_to_questions(section_structure, ch_map, all_questions):
    result = []
    for ch_idx, ch_data in enumerate(section_structure):
        if ch_idx >= len(ch_map):
            print(f"  WARNING: ch_idx {ch_idx} out of ch_map range ({len(ch_map)})")
            break
        ch_info = ch_map[ch_idx]
        ch_start = ch_info['start']
        ch_count = ch_info['count']
        ch_sections = ch_data['sections']
        total_section_count = sum(s['count'] for s in ch_sections)
        
        section_ranges = []
        q_offset = 0
        for sec_idx, s in enumerate(ch_sections):
            if total_section_count > 0:
                s_count = max(1, round(ch_count * s['count'] / total_section_count))
            else:
                s_count = 0
            if sec_idx == len(ch_sections) - 1:
                s_count = ch_count - q_offset
            section_ranges.append({
                'name': s['name'],
                'orig_count': s['count'],
                'q_start': ch_start + q_offset,
                'q_count': s_count
            })
            q_offset += s_count
        total_mapped = sum(sr['q_count'] for sr in section_ranges)
        if total_mapped != ch_count and section_ranges:
            section_ranges[-1]['q_count'] += ch_count - total_mapped
        result.append({'chapter': ch_data['chapter'], 'sections': section_ranges,
                       'ch_start': ch_start, 'ch_count': ch_count})
    return result

section_map_fin = map_sections_to_questions(sections['fin'], fin_data['ch_map'], fin_data['questions'])
section_map_law = map_sections_to_questions(sections['law'], law_data['ch_map'], law_data['questions'])
print(f"小节映射: 金融基础 {len(section_map_fin)}章, 法律法规 {len(section_map_law)}章")

# ====== 3. Generate HTML ======
def gen_html(data, section_map, subject_label):
    s = data['subject']
    qs = data['questions']
    chs = data['chapters']
    ch_list_json = json.dumps(chs, ensure_ascii=False)
    qs_json = json.dumps(qs, ensure_ascii=False)
    sec_json = json.dumps(section_map, ensure_ascii=False)
    
    # Build CH_MAP from section data
    ch_map_entries = []
    q_idx = 0
    for ci, ch in enumerate(section_map):
        ch_start = q_idx
        ch_count = sum(s['q_count'] for s in ch['sections'])
        ch_map_entries.append({
            'code': f'第{ci+1}章',
            'name': re.sub(r'^第.章\s*', '', ch['chapter']),
            'start': ch_start,
            'count': ch_count
        })
        q_idx += ch_count
    ch_map_json = json.dumps(ch_map_entries, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>证券从业 · 章节精练 · {s}</title>
<style>
:root {{
  --bg: #f5efe6; --card: #faf6f0; --card-alt: #f0e8db;
  --border: #d4c9b8; --border-light: #e8dfd0;
  --text: #3d3229; --text-dim: #8a7e6f; --text-light: #b8a99a;
  --blue: #1e5b8a; --blue-light: #4a8bc2; --blue-dim: #7ba3c7;
  --blue-bg: rgba(30,91,138,0.06);
  --red: #c23b22; --red-light: #d4735e; --red-bg: rgba(194,59,34,0.08);
  --green: #3d7246; --green-light: #5c9a66; --green-bg: rgba(61,114,70,0.08);
  --gold: #c9a96e; --gold-light: #e8dbaa;
  --shadow: rgba(61,50,41,0.06);
}}
* {{ margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
body {{ font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--text); line-height:1.7; padding:0.6rem; min-height:100vh; }}
.container {{ max-width:860px; margin:0 auto; }}
.hd {{ text-align:center; padding:1rem 0.5rem 0.6rem; margin-bottom:0.5rem; position:relative; }}
.hd::after {{ content:''; display:block; width:50px; height:3px; background:linear-gradient(90deg,var(--blue),var(--gold)); margin:0.5rem auto 0; border-radius:2px; }}
.hd h1 {{ font-size:1.2rem; font-weight:800; color:var(--blue); letter-spacing:1px; }}
.hd .sub {{ color:var(--text-dim); font-size:0.75rem; margin-top:0.2rem; }}
.legend-bar {{ display:flex; justify-content:center; gap:0.5rem 1.2rem; flex-wrap:wrap; padding:0.4rem 0.6rem; margin:0 0 0.5rem; font-size:0.72rem; background:var(--card); border-radius:8px; border:1px solid var(--border-light); }}
.legend-item {{ display:flex; align-items:center; gap:4px; }}
.legend-item .star {{ color:var(--gold); font-size:0.8rem; letter-spacing:-1px; }}
.legend-item .lbl {{ color:var(--text-dim); }}

.section-view {{ display:block; }}
.section-view.hidden {{ display:none; }}
.q-view {{ display:none; }}
.q-view.show {{ display:block; }}

.ch-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; margin-bottom:0.5rem; overflow:hidden; }}
.ch-head {{ display:flex; justify-content:space-between; align-items:center; padding:0.7rem 0.8rem; cursor:pointer; user-select:none; background:linear-gradient(135deg,var(--card),var(--card-alt)); }}
.ch-head:active {{ background:var(--card-alt); }}
.ch-head .name {{ font-weight:700; font-size:0.9rem; color:var(--blue); }}
.ch-head .meta {{ font-size:0.72rem; color:var(--text-dim); }}
.ch-head .arrow {{ transition:transform 0.2s; font-size:0.7rem; color:var(--text-light); }}
.ch-head.exp .arrow {{ transform:rotate(180deg); }}
.sec-list {{ display:none; padding:0.2rem 0.8rem 0.6rem; }}
.sec-list.show {{ display:block; }}
.sec-item {{ display:flex; justify-content:space-between; align-items:center; padding:0.45rem 0.6rem; margin:0.2rem 0; border-radius:6px; cursor:pointer; border:1px solid transparent; }}
.sec-item:active {{ background:var(--blue-bg); border-color:var(--blue-dim); }}
.sec-item .sname {{ font-size:0.82rem; color:var(--text); }}
.sec-item .scount {{ font-size:0.72rem; color:var(--text-dim); background:var(--card-alt); padding:0.1rem 0.5rem; border-radius:10px; }}
.sec-item .sbar {{ flex:1; height:4px; background:var(--border-light); border-radius:2px; margin:0 0.6rem; overflow:hidden; }}
.sec-item .sbar-fill {{ height:100%; border-radius:2px; background:linear-gradient(90deg,var(--blue),var(--blue-light)); }}

.ch-nav {{ display:flex; flex-wrap:wrap; gap:5px; justify-content:center; margin:0.4rem 0 0.6rem; }}
.ch-btn {{ padding:0.35rem 0.6rem; border-radius:8px; font-size:0.76rem; font-weight:600; border:1.5px solid var(--border); cursor:pointer; background:var(--card); color:var(--text-dim); white-space:nowrap; text-align:center; }}
.ch-btn.on {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
.ch-btn .ch-title {{ display:block; }}
.ch-btn .ch-meta {{ display:block; font-weight:400; font-size:0.65rem; opacity:0.8; }}
.stats {{ display:flex; justify-content:space-between; align-items:center; padding:0.5rem 0.8rem; background:var(--card); border-radius:8px; margin-bottom:0.6rem; border:1px solid var(--border-light); font-size:0.78rem; }}
.stats .pct {{ color:var(--blue); font-weight:700; font-size:0.9rem; }}
.progress-bar {{ height:4px; background:var(--border-light); border-radius:2px; margin:0.4rem 0 0.8rem; overflow:hidden; }}
.progress-fill {{ height:100%; background:linear-gradient(90deg,var(--blue),var(--blue-light)); border-radius:2px; transition:width 0.4s ease; }}
.back-btn {{ display:inline-flex; align-items:center; gap:4px; padding:0.3rem 0.7rem; border-radius:6px; font-size:0.78rem; font-weight:600; border:1px solid var(--border); cursor:pointer; background:var(--card); color:var(--blue); margin-bottom:0.4rem; }}

.q-wrap {{ margin-bottom:1rem; }}
.q-head {{ display:flex; align-items:center; gap:6px; margin-bottom:0.4rem; }}
.q-num {{ font-weight:700; font-size:0.85rem; color:var(--blue); min-width:24px; }}
.q-tag {{ font-size:0.65rem; padding:0.05rem 0.4rem; border-radius:4px; background:var(--card-alt); color:var(--text-dim); }}
.q-text {{ font-size:0.9rem; margin-bottom:0.5rem; line-height:1.8; }}
.opt {{ display:flex; align-items:flex-start; gap:6px; padding:0.4rem 0.5rem; margin:0.15rem 0; border-radius:6px; border:1px solid var(--border-light); cursor:pointer; background:var(--card); font-size:0.85rem; line-height:1.6; }}
.opt.selected {{ border-color:var(--blue); background:var(--blue-bg); }}
.opt.correct {{ border-color:var(--green); background:var(--green-bg); }}
.opt.wrong {{ border-color:var(--red); background:var(--red-bg); }}
.opt.disabled {{ opacity:0.7; pointer-events:none; }}
.okey {{ font-weight:700; color:var(--blue); min-width:20px; }}
.oval {{ flex:1; }}
.ans-box {{ padding:0.5rem; border-radius:6px; margin-top:0.4rem; font-size:0.82rem; line-height:1.6; }}
.ans-box.correct {{ background:var(--green-bg); border:1px solid var(--green); color:var(--green); }}
.ans-box.wrong {{ background:var(--red-bg); border:1px solid var(--red); color:var(--red); }}
.ans-box .a-text {{ color:var(--text); margin-top:0.3rem; }}
.action-row {{ display:flex; gap:6px; margin-top:0.5rem; }}
.action-row button {{ padding:0.35rem 0.8rem; border-radius:6px; font-size:0.78rem; font-weight:600; border:1px solid var(--border); cursor:pointer; }}
.btn-check {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
.btn-reset {{ background:var(--card); color:var(--text-dim); }}
</style>
</head>
<body>
<div class="container">
<div class="hd"><h1>📚 章节精练 · {s}</h1><div class="sub">按章分节 · 逐步突破 · 每题含解析</div></div>
<div class="legend-bar">
<span class="legend-item"><span class="star">★★★★★</span><span class="lbl">掌握</span></span>
<span class="legend-item"><span class="star">★★★☆☆</span><span class="lbl">熟悉</span></span>
<span class="legend-item"><span class="star">★★☆☆☆</span><span class="lbl">了解</span></span>
</div>
<div id="sectionView" class="section-view"></div>
<div id="questionView" class="q-view">
  <button class="back-btn" onclick="showSectionView()">‹ 返回章节列表</button>
  <div class="ch-nav" id="chNav"></div>
  <div class="stats" id="stats"></div>
  <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
  <div id="questionList"></div>
</div>
</div>
<script>
var SUBJECT = "{s}";
var CHAPTERS = {ch_list_json};
var ALL_QUESTIONS = {qs_json};
var SECTION_DATA = {sec_json};
var CH_MAP = {ch_map_json};
var STORAGE_KEY = 'sec_exam_chapter_{s}';
var state = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
var currentCh = 0;
var currentSec = -1;
var selected = {{}};

function saveState() {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }}

function renderSectionView() {{
  var el = document.getElementById('sectionView');
  var html = '';
  SECTION_DATA.forEach(function(ch, ci) {{
    var chInfo = CHAPTERS[ci] || {{}};
    var stars = '★'.repeat(chInfo.stars||0) + '☆'.repeat(5-(chInfo.stars||0));
    html += '<div class="ch-card"><div class="ch-head" onclick="toggleSections('+ci+')">'
         + '<div><div class="name">'+esc(ch.chapter)+'</div>'
         + '<div class="meta">'+stars+' · '+ch.ch_count+'题</div></div>'
         + '<span class="arrow">▼</span></div>'
         + '<div class="sec-list" id="secList-'+ci+'">';
    ch.sections.forEach(function(sec, si) {{
      var pct = ch.ch_count > 0 ? Math.round(sec.q_count/ch.ch_count*100) : 0;
      html += '<div class="sec-item" onclick="startSection('+ci+','+si+')">'
           + '<span class="sname">'+esc(sec.name)+'</span>'
           + '<div class="sbar"><div class="sbar-fill" style="width:'+pct+'%"></div></div>'
           + '<span class="scount">'+sec.q_count+'题</span></div>';
    }});
    html += '</div></div>';
  }});
  el.innerHTML = html;
}}

function toggleSections(ci) {{
  var head = document.querySelectorAll('.ch-head')[ci];
  var list = document.getElementById('secList-'+ci);
  if (!list) return;
  head.classList.toggle('exp');
  list.classList.toggle('show');
}}

function startSection(ci, si) {{
  currentCh = ci; currentSec = si;
  renderNav(); renderStats(); renderQuestions();
  document.getElementById('sectionView').classList.add('hidden');
  document.getElementById('questionView').classList.add('show');
}}

function showSectionView() {{
  document.getElementById('sectionView').classList.remove('hidden');
  document.getElementById('questionView').classList.remove('show');
}}

function renderNav() {{
  var nav = document.getElementById('chNav');
  var html = '';
  CHAPTERS.forEach(function(ch, i) {{
    var a = i === currentCh ? 'on' : '';
    html += '<div class="ch-btn '+a+'" onclick="switchCh('+i+')">'
         + '<span class="ch-title">'+esc(ch.name)+'</span>'
         + '<span class="ch-meta">'+ch.count+'题</span></div>';
  }});
  nav.innerHTML = html;
}}

function renderStats() {{
  var ch = CH_MAP[currentCh];
  if (!ch) return;
  var start, count;
  if (currentSec >= 0) {{
    var sec = SECTION_DATA[currentCh].sections[currentSec];
    start = sec.q_start; count = sec.q_count;
  }} else {{ start = ch.start; count = ch.count; }}
  var done=0, correct=0;
  for (var i=start; i<start+count && i<ALL_QUESTIONS.length; i++) {{
    if (state[i] && state[i].done) {{ done++; if (state[i].correct) correct++; }}
  }}
  var pct = done>0 ? Math.round(correct/done*100) : 0;
  document.getElementById('stats').innerHTML = '<span>📝 '+done+'/'+count+' 已做</span><span class="pct">✅ '+pct+'%</span>';
  document.getElementById('progressFill').style.width = (count>0?Math.round(done/count*100):0)+'%';
}}

function getQs() {{
  var ch = CH_MAP[currentCh];
  if (!ch) return [];
  var start, count;
  if (currentSec >= 0) {{
    var sec = SECTION_DATA[currentCh].sections[currentSec];
    start = sec.q_start; count = sec.q_count;
  }} else {{ start = ch.start; count = ch.count; }}
  var qs = [];
  for (var i=start; i<start+count && i<ALL_QUESTIONS.length; i++) qs.push({{idx:i, q:ALL_QUESTIONS[i]}});
  return qs;
}}

function renderQuestions() {{
  var c = document.getElementById('questionList');
  var qs = getQs();
  var html = '';
  qs.forEach(function(item) {{
    var q = item.q, idx = item.idx, s = state[idx] || {{}};
    var keys = Object.keys(q.c);
    var isSingle = q.type==='single'||q.type==='judge';
    var tl = q.type==='judge'?'判断':(q.type==='multi'?'多选':'单选');
    html += '<div class="q-wrap" id="qw-'+idx+'">';
    html += '<div class="q-head"><span class="q-num">'+(qs.indexOf(item)+1)+'.</span><span class="q-tag">'+tl+'</span></div>';
    html += '<div class="q-text">'+esc(q.q)+'</div><div class="opts" id="opts-'+idx+'">';
    keys.forEach(function(key) {{
      var val = q.c[key];
      if (val==null) return;
      var extra = '';
      if (s.done) {{
        var isC = q.a.indexOf(key)>=0;
        var isSel = s.answers && s.answers.indexOf(key)>=0;
        extra = isSel&&isC ? ' correct disabled' : (isSel&&!isC ? ' wrong disabled' : (isC ? ' correct disabled' : ' disabled'));
      }}
      html += '<div class="opt'+extra+'" onclick="toggleOpt('+idx+',\\''+key+'\\')"><span class="okey">'+key+'</span><span class="oval">'+esc(val)+'</span></div>';
    }});
    html += '</div>';
    if (s.done) {{
      html += '<div class="ans-box '+(s.correct?'correct':'wrong')+'">'+(s.correct?'✅ 回答正确':'❌ 回答错误')+' · 正确答案：'+esc(q.a)+(s.answers&&!s.correct?' · 你的答案：'+esc(s.answers.join('')):'')+'</div>';
      html += '<div class="ans-box" style="background:var(--card-alt);border-color:var(--border-light);color:var(--text);margin-top:0.3rem;"><div class="a-text">'+esc(q.an)+'</div></div>';
    }}
    html += '</div>';
  }});
  html += '<div class="action-row"><button class="btn-check" onclick="checkAll()">📝 批改本页</button><button class="btn-reset" onclick="resetAll()">🔄 重置本页</button></div>';
  c.innerHTML = html;
}}

function switchCh(idx) {{ currentCh=idx; currentSec=-1; renderNav(); renderStats(); renderQuestions(); }}

function toggleOpt(idx, key) {{
  if (state[idx] && state[idx].done) return;
  if (!selected[idx]) selected[idx]=[];
  var arr = selected[idx], pos = arr.indexOf(key);
  var q = ALL_QUESTIONS[idx], isSingle = q.type==='single'||q.type==='judge';
  if (isSingle) {{ selected[idx]=[key]; }} else {{ if(pos>=0) arr.splice(pos,1); else arr.push(key); }}
  var opts = document.getElementById('opts-'+idx);
  if (opts) opts.querySelectorAll('.opt').forEach(function(o) {{
    o.classList.toggle('selected', selected[idx].indexOf(o.dataset.key||'')>=0);
  }});
}}

function checkSingle(idx) {{
  var q = ALL_QUESTIONS[idx];
  if (state[idx] && state[idx].done) return;
  var sel = selected[idx]||[]; if(sel.length===0) return;
  var isC = sel.sort().join('') === q.a;
  state[idx] = {{done:true, correct:isC, answers:sel.slice()}};
  saveState();
}}

function checkAll() {{ getQs().forEach(function(item){{ checkSingle(item.idx); }}); renderStats(); renderQuestions(); }}

function resetAll() {{
  getQs().forEach(function(item){{ delete state[item.idx]; delete selected[item.idx]; }});
  saveState(); renderStats(); renderQuestions();
}}

function esc(s) {{ if(s==null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;'); }}

renderSectionView();
</script>
</body>
</html>'''

# Generate
for label, data, smap in [('fin', fin_data, section_map_fin), ('law', law_data, section_map_law)]:
    subject_label = 'finance' if label == 'fin' else 'law'
    html = gen_html(data, smap, subject_label)
    fname = f'章节精练_{"金融市场基础" if label=="fin" else "法律法规"}.html'
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✅ {fname} 生成 ({len(data["questions"])}题)')
