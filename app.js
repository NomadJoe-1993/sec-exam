// ====== State ======
let MANIFEST = null;
let curExam = null, curIdx = 0, userAns = {}, submitted = false;
let history = JSON.parse(localStorage.getItem('secHistory') || '{}');
let wrongBook = JSON.parse(localStorage.getItem('secWrongBook') || '[]');
let profile = JSON.parse(localStorage.getItem('secProfile') || 'null');

// ====== Init ======
(async function init() {
  try {
    const r = await fetch('manifest.json');
    MANIFEST = await r.json();
    if (!profile) { showPage('page-onboard'); return; }
    renderHome();
  } catch(e) {
    document.getElementById('home-content').innerHTML =
      `<div class="empty-state"><div class="icon">⚠️</div><p>加载失败: ${e.message}</p></div>`;
  }
})();

// ====== Profile / Onboarding ======
function saveProfile() {
  const target = document.getElementById('ob-target').value;
  const level = parseInt(document.getElementById('ob-level').value);
  const hours = parseFloat(document.getElementById('ob-time').value);
  const date = document.getElementById('ob-date').value;
  if (!date) { alert('请选择考试日期'); return; }
  profile = { target, level, hours, date, created: Date.now() };
  localStorage.setItem('secProfile', JSON.stringify(profile));
  renderHome();
  showPage('page-home');
}

function showSettings() {
  if (!profile) { showPage('page-onboard'); return; }
  const el = document.getElementById('settings-content');
  const d = new Date(profile.date);
  el.innerHTML = `
    <div class="mb-8"><h2 class="page-title">我的备考计划</h2></div>
    <div class="plan-card">
      <div class="row"><span>考试目标</span><span class="val">${targetLabel(profile.target)}</span></div>
      <div class="row"><span>当前基础</span><span class="val">${['零基础','有基础','已复习一轮'][profile.level]}</span></div>
      <div class="row"><span>每日学习</span><span class="val">${profile.hours} 小时</span></div>
      <div class="row"><span>考试日期</span><span class="val">${d.toLocaleDateString('zh-CN')}</span></div>
      <div class="row"><span>剩余天数</span><span class="val">${daysLeft(profile.date)} 天</span></div>
    </div>
    <div class="mt-14">
      <h3 class="fw-600 mb-8 fs-15">📋 每日推荐</h3>
      <div class="glass p-14">
        ${renderPlan()}
      </div>
    </div>
    <button class="onboard-btn mt-16" onclick="resetProfile()">🔄 重新设置</button>
  `;
  showPage('page-settings');
}

function resetProfile() {
  if (confirm('重新设置将清空当前学习计划，确定吗？')) {
    localStorage.removeItem('secProfile');
    profile = null;
    showPage('page-onboard');
  }
}

function targetLabel(t) {
  return { both:'双科', fin:'金融市场基础知识', law:'证券市场基本法律法规' }[t] || t;
}

function daysLeft(d) {
  const diff = new Date(d) - new Date();
  return Math.max(0, Math.ceil(diff / 86400000));
}

function renderPlan() {
  if (!profile) return '<p class="text-dim">请先设置备考信息</p>';
  const total = countAll();
  const days = daysLeft(profile.date);
  const daily = Math.max(10, Math.ceil(total * 1.5 / days));
  const focus = profile.target === 'fin' ? '金融市场基础知识' :
               profile.target === 'law' ? '证券市场基本法律法规' : '双科同步';
  return `
    <div class="row"><span>每日建议题量</span><span class="val text-accent fw-600 fs-16">${daily} 题</span></div>
    <div class="row"><span>复习重点</span><span class="val">${focus}</span></div>
    <div class="row"><span>推荐顺序</span><span class="val">章节高频 → 冲刺卷 → 模拟卷</span></div>
    <div class="text-sm text-dim mt-6">${profile.level === 0 ? '💡 零基础建议先看一遍教材再刷题' : ''}</div>
  `;
}

// ====== Home ======
function renderHome() {
  const data = calcStats();
  document.getElementById('home-stats').innerHTML = `
    <div class="stat-card" onclick="openCategory('chapter')"><div class="num text-accent">${data.done}</div><div class="lbl">已做试卷</div></div>
    <div class="stat-card" onclick="showWrongBook()"><div class="num text-red">${data.wrong}</div><div class="lbl">错题总数</div></div>
    <div class="stat-card"><div class="num text-green">${data.avgScore}%</div><div class="lbl">平均得分</div></div>`;
  const wc = wrongBook.length;
  document.getElementById('wrong-count-badge').textContent = wc > 0 ? wc + ' 道待复习' : '暂无错题';
  document.getElementById('wrong-badge').textContent = wc > 0 ? wc + '题' : '';
  document.getElementById('wrong-badge').style.display = wc > 0 ? '' : 'none';

  const banner = document.getElementById('plan-banner');
  if (profile) {
    const dl = daysLeft(profile.date);
    banner.innerHTML = `<div class="plan-card clickable" onclick="showSettings()">
      <div class="flex justify-between items-center">
        <h3>📋 备考计划</h3>
        <span class="text-sm text-dim">${dl}天后考试 ›</span>
      </div>
      <div class="row"><span>目标</span><span class="val">${targetLabel(profile.target)}</span></div>
      <div class="row"><span>今日推荐</span><span class="val text-accent fw-600">${renderDailyRec()} 题</span></div>
    </div>`;
  } else {
    banner.innerHTML = `<div class="plan-card clickable text-center" onclick="showPage('page-onboard')">
      <h3>🎯 点击设置备考计划</h3>
      <p class="text-dim">根据你的时间和目标定制学习方案</p>
    </div>`;
  }
}

function renderDailyRec() {
  if (!profile) return 0;
  return Math.max(10, Math.ceil(countAll() * 1.5 / daysLeft(profile.date)));
}

function calcStats() {
  const examIds = Object.keys(history).filter(k => history[k].submitted);
  let done = examIds.length, wrong = wrongBook.length, totalScore = 0;
  examIds.forEach(k => { totalScore += history[k].lastScore || 0; });
  return { done, wrong, avgScore: done > 0 ? Math.round(totalScore / done) : 0 };
}

function countAll() {
  let t = 0;
  if (MANIFEST) MANIFEST.categories.forEach(c => c.items.forEach(i => t += i.count));
  return t;
}

// ====== Category → Exam List ======
function openCategory(catId) {
  const cat = MANIFEST.categories.find(c => c.id === catId);
  if (!cat) return;
  document.getElementById('list-title').textContent = cat.title;
  let done = 0, total = cat.items.length;
  cat.items.forEach(i => { if (history[i.id] && history[i.id].submitted) done++; });
  document.getElementById('list-progress').textContent = done + '/' + total;

  const el = document.getElementById('list-content');
  let html = '';
  cat.items.forEach(item => {
    const h = history[item.id];
    const completed = h && h.submitted;
    const score = h ? h.lastScore : null;
    const best = h ? h.best : null;
    const color = best !== null ? (best >= 70 ? 'var(--green)' : 'var(--red)') : 'var(--dim)';
    html += `<div class="exam-item" onclick="startExam('${item.id}')">
      <div class="info"><h3>${item.title}</h3>
        <div class="meta">${item.count}题${completed ? ' · 上次 ' + score + '% · 最高 ' + best + '%' : ' · 未完成'}</div></div>
      <div class="status-dot" style="background:${color}"></div></div>`;
  });
  el.innerHTML = html;
  showPage('page-list');
}

// ====== Start Exam ======
async function startExam(examId) {
  try {
    const r = await fetch(examId + '.json');
    curExam = await r.json();
    curIdx = 0; userAns = {}; submitted = false;
    const h = history[examId];
    if (h && h.answers) { userAns = {...h.answers}; submitted = h.submitted || false; }
    showPage('page-exam');
    renderQ();
  } catch(e) { alert('加载失败: ' + e.message); }
}

// ====== Render Q ======
function renderQ() {
  const q = curExam.questions[curIdx];
  if (!q) return;
  const total = curExam.questions.length;

  document.getElementById('q-num').textContent = q.id || (curIdx + 1);
  const tag = document.getElementById('q-tag');
  const tmap = { single:'单选', multi:'多选', judge:'判断' };
  tag.textContent = tmap[q.type] || q.type; tag.className = 'q-tag ' + q.type;
  document.getElementById('q-text').textContent = q.q;
  document.getElementById('exam-counter').textContent = q.id + ' / ' + total;
  document.getElementById('progress-fill').style.width = ((q.id-1)/total*100)+'%';

  const oe = document.getElementById('q-options'); oe.innerHTML = '';
  const sel = userAns[q.id] || '';
  Object.keys(q.c).forEach(k => {
    const d = document.createElement('div');
    d.className = 'opt'; d.dataset.key = k;
    if (submitted) d.classList.add('disabled');
    if (sel.includes(k)) d.classList.add('sel');
    if (submitted) {
      if (q.a.includes(k)) d.classList.add('cor');
      else if (sel.includes(k)) d.classList.add('wro');
    }
    d.innerHTML = '<span class="k">' + k + '</span><span class="v">' + q.c[k] + '</span>';
    d.addEventListener('click', () => select(k));
    oe.appendChild(d);
  });

  const ab = document.getElementById('analysis-box');
  if (submitted) {
    document.getElementById('analysis-ans').textContent = '✅ 正确答案：' + q.a.split('').join('、');
    document.getElementById('analysis-exp').textContent = q.an || '暂无解析';
    ab.classList.add('show');
  } else ab.classList.remove('show');

  document.getElementById('prev-btn').disabled = curIdx === 0;
  document.getElementById('next-btn').disabled = curIdx === total-1;
  updateSubmitBtn();
}

function select(key) {
  if (submitted) return;
  const q = curExam.questions[curIdx];
  if (q.type === 'multi') {
    const s = userAns[q.id] || '';
    userAns[q.id] = s.includes(key) ? s.replace(key,'') : (s+key).split('').sort().join('');
  } else userAns[q.id] = key;
  saveProgress(); renderQ();
}

function saveProgress() {
  if (!curExam) return;
  history[curExam.id] = {
    answers: userAns, submitted: submitted,
    lastScore: history[curExam.id]?.lastScore, best: history[curExam.id]?.best
  };
  localStorage.setItem('secHistory', JSON.stringify(history));
}

function navQ(d) {
  const n = curIdx + d;
  if (n >= 0 && n < curExam.questions.length) { curIdx = n; renderQ(); }
}

function updateSubmitBtn() {
  const btn = document.getElementById('submit-btn');
  if (submitted) { btn.textContent = '✅ 已提交'; btn.disabled = true; return; }
  const a = Object.keys(userAns).length, t = curExam.questions.length;
  btn.textContent = a < t ? '📝 交卷 (' + a + '/' + t + ')' : '📝 交卷批改';
  btn.disabled = false;
}

// ====== Submit ======
function submitExam() {
  if (submitted) return;
  const a = Object.keys(userAns).length, t = curExam.questions.length;
  if (a < t && !confirm('还有 ' + (t-a) + ' 题未答，确定交卷吗？')) return;

  submitted = true;
  let correct = 0;
  curExam.questions.forEach(q => {
    const u = (userAns[q.id]||'').split('').sort().join('');
    const c = q.a.split('').sort().join('');
    if (u === c) correct++;
    else {
      const exist = wrongBook.find(w => w.qid === q.id && w.examId === curExam.id);
      if (!exist) {
        wrongBook.push({
          examId: curExam.id, examTitle: curExam.title, qid: q.id, q: q.q,
          type: q.type, choices: q.c, userAns: userAns[q.id]||'',
          correctAns: q.a, analysis: q.an, time: Date.now()
        });
      }
    }
  });
  localStorage.setItem('secWrongBook', JSON.stringify(wrongBook));

  const pct = Math.round(correct/t*100);
  const h = history[curExam.id] || {answers:{},submitted:false};
  h.answers = userAns; h.submitted = true; h.lastScore = pct;
  h.best = Math.max(pct, h.best||0);
  history[curExam.id] = h;
  localStorage.setItem('secHistory', JSON.stringify(history));

  renderQ();
  showResult(correct, t, pct);
}

// ====== Result ======
function showResult(correct, total, pct) {
  const el = document.getElementById('result-content');
  const color = pct>=70?'var(--green)':pct>=60?'var(--yellow)':'var(--red)';
  const msg = pct>=70?'✅ 稳了！考场正常发挥就能过'
            : pct>=60?'⚠️ 差一点，趁热打铁再来一遍'
            : '❌ 知识点还有漏洞，重做一轮';
  el.innerHTML = `
    <h2 class="fs-18">${curExam.title}</h2>
    <div class="score-ring" style="border-color:${color}"><div class="num" style="color:${color}">${pct}%</div><div class="lbl">得分</div></div>
    <div class="result-detail">正确 <span class="text-green fw-600">${correct}</span> 题 · 错误 <span class="text-red fw-600">${total-correct}</span> 题 · 共 ${total} 题</div>
    <div class="result-msg">${msg}</div>
    <div class="result-actions">
      <button class="btn-rp" onclick="reviewWrong()">📖 查看错题</button>
      <button class="btn-rs" onclick="resetExam()">🔄 重做</button>
      <button class="btn-rg" onclick="goHome()">🏠 首页</button>
    </div>`;
  showPage('page-result');
}

function reviewWrong() {
  showPage('page-exam');
  for (let i=0; i<curExam.questions.length; i++) {
    const q = curExam.questions[i];
    if ((userAns[q.id]||'').split('').sort().join('') !== q.a.split('').sort().join('')) { curIdx = i; break; }
  }
  renderQ();
}

function resetExam() {
  submitted = false; userAns = {}; curIdx = 0;
  const h = history[curExam.id];
  if (h) { h.answers = {}; h.submitted = false; localStorage.setItem('secHistory', JSON.stringify(history)); }
  showPage('page-exam'); renderQ();
}

// ====== Q Grid ======
function showQGrid() {
  if (!curExam) return;
  const grid = document.getElementById('qgrid-items'); grid.innerHTML = '';
  curExam.questions.forEach((q,i) => {
    const d = document.createElement('div'); d.className = 'qgrid-item';
    const u = userAns[q.id]||'';
    if (submitted) d.className += u.split('').sort().join('')===q.a.split('').sort().join('')?' correct':' wrong';
    else if (u.length>0) d.className += ' answered';
    d.textContent = q.id;
    d.onclick = () => { curIdx = i; closeQGrid(); renderQ(); };
    grid.appendChild(d);
  });
  showPage('page-qgrid');
}
function closeQGrid() { showPage('page-exam'); }

// ====== Wrong Book ======
function showWrongBook() {
  const el = document.getElementById('wrong-content');
  document.getElementById('clear-wrong-btn').style.display = wrongBook.length > 0 ? '' : 'none';
  if (wrongBook.length === 0) {
    el.innerHTML = '<div class="empty-state"><div class="icon">🎉</div><p>还没有错题，继续保持！</p></div>';
    showPage('page-wrong'); return;
  }
  let html = '<div class="text-sm text-dim mb-8">共 ' + wrongBook.length + ' 道错题</div>';
  wrongBook.forEach((w, idx) => {
    const tmap = { single:'单选', multi:'多选', judge:'判断' };
    html += '<div class="wrong-item" onclick="reviewWrongItem(' + idx + ')">' +
      '<div class="src">📝 ' + w.examTitle + ' · 第' + w.qid + '题 · ' + (tmap[w.type]||w.type) + '</div>' +
      '<div class="q">' + w.q + '</div>' +
      '<div class="meta"><span class="text-red">你的答案: ' + (w.userAns||'未选') + '</span>' +
      '<span class="text-green">正确: ' + w.correctAns.split('').join('、') + '</span></div></div>';
  });
  el.innerHTML = html;
  showPage('page-wrong');
}

function reviewWrongItem(idx) {
  const w = wrongBook[idx];
  if (w && w.examId) { startExam(w.examId); }
}

function clearWrongBook() {
  if (confirm('确定清空所有错题吗？')) {
    wrongBook = [];
    localStorage.setItem('secWrongBook', JSON.stringify(wrongBook));
    showWrongBook();
    renderHome();
  }
}

// ====== Page Routing ======
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}
function goHome() { showPage('page-home'); renderHome(); }
function openStudyCards() { window.open('study_cards.html', '_blank'); }
