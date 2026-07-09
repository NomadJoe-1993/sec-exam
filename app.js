// ====== State ======
let MANIFEST = null;
let curExam = null, curIdx = 0, userAns = {}, submitted = false, confirmed = {};
let memorizeMode = false;
let history = JSON.parse(localStorage.getItem('secHistory') || '{}');
let wrongBook = JSON.parse(localStorage.getItem('secWrongBook') || '[]');

// ====== Init ======
(async function init() {
  try {
    const r = await fetch('manifest.json?_t=' + Date.now());
    MANIFEST = await r.json();
    renderHome();
    showPage('page-home');
  } catch(e) {
    document.getElementById('home-content').innerHTML =
      `<div class="empty-state"><div class="icon">⚠️</div><p>加载失败: ${e.message}</p></div>`;
  }
})();

// ====== Profile / Onboarding ======
// Profile module removed

// Settings removed

// resetProfile removed

// targetLabel removed

// daysLeft removed

// renderPlan removed

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

  document.getElementById('plan-banner').innerHTML = '';
}


// renderDailyRec removed

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
    const r = await fetch(examId + '.json?_t=' + Date.now());
    if (!r.ok) throw new Error('not found');
    curExam = await r.json();
    curIdx = 0; userAns = {}; submitted = false; confirmed = {}; memorizeMode = false;
    const h = history[examId];
    if (h && h.answers) { userAns = {...h.answers}; submitted = h.submitted || false; confirmed = h.confirmed || {}; }
    document.getElementById('mode-toggle').textContent = '📖 背题';
    document.getElementById('mode-toggle').classList.remove('memorize');
    showPage('page-exam');
    renderQ();
  } catch(e) {
    // Try HTML fallback for standalone pages
    window.location.href = examId + '.html';
  }
}

// ====== Toggle Memorize Mode ======
function toggleMode() {
  memorizeMode = !memorizeMode;
  const btn = document.getElementById('mode-toggle');
  if (memorizeMode) {
    btn.textContent = '📝 考试';
    btn.classList.add('memorize');
  } else {
    btn.textContent = '📖 背题';
    btn.classList.remove('memorize');
  }
  renderQ();
  updateSubmitBtn();
}

// ====== Render Q ======
function renderQ() {
  const q = curExam.questions[curIdx];
  if (!q) return;
  const total = curExam.questions.length;

  document.getElementById('q-num').textContent = q.id || (curIdx + 1);
  const tag = document.getElementById('q-tag');
  const tmap = { single:'单选', multi:'多选', judge:'判断', comprehensive:'不定项' };
  tag.textContent = tmap[q.type] || q.type; tag.className = 'q-tag ' + q.type;
  document.getElementById('q-text').textContent = q.q;
  document.getElementById('exam-counter').textContent = q.id + ' / ' + total;
  document.getElementById('progress-fill').style.width = ((q.id-1)/total*100)+'%';

  const oe = document.getElementById('q-options'); oe.innerHTML = '';
  const sel = userAns[q.id] || '';
  const isAnswered = confirmed[q.id] === true || memorizeMode;
  // In memorize mode, show correct answer always
  const displayAns = memorizeMode && !isAnswered ? q.a : (sel || '');
  Object.keys(q.c).forEach(k => {
    const d = document.createElement('div');
    d.className = 'opt';
    if (isAnswered || memorizeMode) d.classList.add('disabled');
    if (memorizeMode) {
      // Show correct answer directly
      if (q.a.includes(k)) d.classList.add('cor');
    } else {
      if (sel.includes(k)) d.classList.add('sel');
    }
    if (isAnswered) {
      if (q.a.includes(k)) d.classList.add('cor');
      else if (sel.includes(k)) d.classList.add('wro');
    }
    d.innerHTML = '<span class="k">' + k + '</span><span class="v">' + q.c[k] + '</span>';
    d.addEventListener('click', () => select(k));
    oe.appendChild(d);
  });

  // ── Analysis box ──
  const ab = document.getElementById('analysis-box');
  if (isAnswered || memorizeMode) {
    document.getElementById('analysis-ans').textContent = '✅ 正确答案：' + q.a.split('').join('、');
    document.getElementById('analysis-exp').textContent = q.an || '暂无解析';
    ab.classList.add('show');
  } else ab.classList.remove('show');

  // ── Confirm button for multi/comprehensive ──
  if (!isAnswered && !submitted && (q.type === 'multi' || q.type === 'comprehensive') && (userAns[q.id] || '').length > 0) {
    const cb = document.createElement('button');
    cb.className = 'btn btn-primary mt-10';
    cb.textContent = '✅ 确认答案';
    cb.style.width = '100%';
    cb.addEventListener('click', confirmAnswer);
    oe.parentNode.appendChild(cb);
  }

  document.getElementById('prev-btn').disabled = curIdx === 0;
  document.getElementById('next-btn').disabled = curIdx === total-1;
  updateSubmitBtn();
}

function select(key) {
  if (submitted || confirmed[curExam.questions[curIdx].id] || memorizeMode) return;
  const q = curExam.questions[curIdx];
  if (q.type === 'multi' || q.type === 'comprehensive') {
    const s = userAns[q.id] || '';
    userAns[q.id] = s.includes(key) ? s.replace(key,'') : (s+key).split('').sort().join('');
  } else {
    // single/judge: immediately confirm
    userAns[q.id] = key;
    confirmed[q.id] = true;
    // also save to wrong book immediately
    const u = key;
    const c = q.a;
    if (u !== c) {
      const exist = wrongBook.find(w => w.qid === q.id && w.examId === curExam.id);
      if (!exist) {
        wrongBook.push({ examId: curExam.id, examTitle: curExam.title, qid: q.id, q: q.q,
          type: q.type, choices: q.c, userAns: u, correctAns: q.a, analysis: q.an, time: Date.now() });
      }
    }
    // record to dashboard
    if (window.ExamRecorder) {
      var typeCn = q.type === 'judge' ? '判断' : '单选';
      window.ExamRecorder.record({
        questionId: curExam.id + '-' + q.id,
        subject: curExam.subject || '',
        chapter: curExam.title || '', type: q.type === 'judge' ? 'j' : 's',
        typeCn: typeCn, question: q.q || '', userAnswer: u, correctAnswer: q.a || '',
        isCorrect: u === q.a, choices: q.c || {}, source: curExam.subject || '试卷'
      });
    }
  }
  saveProgress(); renderQ();
}

function confirmAnswer() {
  if (submitted) return;
  const q = curExam.questions[curIdx];
  if (!userAns[q.id]) return;
  confirmed[q.id] = true;
  // save to wrong book
  const u = userAns[q.id];
  const c = q.a;
  const isCorrect = u.split('').sort().join('') === c.split('').sort().join('');
  if (!isCorrect) {
    const exist = wrongBook.find(w => w.qid === q.id && w.examId === curExam.id);
    if (!exist) {
      wrongBook.push({ examId: curExam.id, examTitle: curExam.title, qid: q.id, q: q.q,
        type: q.type, choices: q.c, userAns: u, correctAns: q.a, analysis: q.an, time: Date.now() });
    }
  }
  // record to dashboard
  if (window.ExamRecorder) {
    var typeCn = q.type === 'multi' ? '多选' : '不定项';
    window.ExamRecorder.record({
      questionId: curExam.id + '-' + q.id, subject: curExam.subject || '',
      chapter: curExam.title || '', type: q.type === 'multi' ? 'm' : 'c',
      typeCn: typeCn, question: q.q || '', userAnswer: u, correctAnswer: q.a || '',
      isCorrect: isCorrect, choices: q.c || {}, source: curExam.subject || '试卷'
    });
  }
  localStorage.setItem('secWrongBook', JSON.stringify(wrongBook));
  saveProgress(); renderQ();
}

function saveProgress() {
  if (!curExam) return;
  history[curExam.id] = {
    answers: userAns, confirmed: confirmed, submitted: submitted,
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
  if (memorizeMode) { btn.style.display = 'none'; return; }
  btn.style.display = '';
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

  // Confirm any multi/comprehensive not yet confirmed
  curExam.questions.forEach(q => {
    if (confirmed[q.id]) return;
    if (userAns[q.id]) {
      confirmed[q.id] = true;
    }
  });

  submitted = true;
  let correct = 0;
  let weightedScore = 0;
  let maxWeighted = 0;
  const isFullMock = curExam.questions.length === 120 &&
    curExam.questions.some(q => q.type === 'comprehensive');
  const examSubject = curExam.subject || (curExam.title || '').includes('金融') ? '金融市场基础知识' : '证券市场基本法律法规';
  curExam.questions.forEach(q => {
    const u = (userAns[q.id]||'').split('').sort().join('');
    const c = q.a.split('').sort().join('');
    const isCorrect = u === c;
    // Weighted scoring for mock exams (syllabus: single=0.5, multi/judge/comprehensive=1)
    const weight = (isFullMock && q.type === 'single') ? 0.5 : 1;
    maxWeighted += weight;
    if (isCorrect) { correct++; weightedScore += weight; }
    if (isCorrect) correct++;
    // Record wrong answer (if not already recorded by select()/confirmAnswer())
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
    // Record to dashboard (only unanswered questions not yet recorded)
    if (window.ExamRecorder && !userAns[q.id]) {
      var typeCn = q.type === 'multi' ? '多选' : (q.type === 'judge' ? '判断' : (q.type === 'comprehensive' ? '不定项' : '单选'));
      window.ExamRecorder.record({
        questionId: curExam.id + '-' + q.id,
        subject: examSubject,
        chapter: curExam.title || '',
        type: q.type === 'judge' ? 'j' : (q.type === 'multi' ? 'm' : 's'),
        typeCn: typeCn,
        question: q.q || '',
        userAnswer: userAns[q.id] || '',
        correctAnswer: q.a || '',
        isCorrect: isCorrect,
        choices: q.c || {},
        source: curExam.subject === '章节高频考点' ? '章节练习' : (curExam.subject || '试卷')
      });
    }
  });
  localStorage.setItem('secWrongBook', JSON.stringify(wrongBook));

  const pct = isFullMock ? Math.round(weightedScore/maxWeighted*100) : Math.round(correct/t*100);
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
  submitted = false; userAns = {}; confirmed = {}; curIdx = 0;
  const h = history[curExam.id];
  if (h) { h.answers = {}; h.submitted = false; localStorage.setItem('secHistory', JSON.stringify(history)); }
  showPage('page-exam'); renderQ();
}

// ====== Q Grid ======
function showQGrid() {
  if (!curExam) return;
  const grid = document.getElementById('qgrid-items'); grid.innerHTML = '';
  let answeredCount = 0;
  curExam.questions.forEach((q,i) => {
    const d = document.createElement('div'); d.className = 'qgrid-item';
    const u = userAns[q.id]||'';
    if (submitted) {
      const isCor = u.split('').sort().join('')===q.a.split('').sort().join('');
      d.className += isCor?' correct':' wrong';
    } else if (u.length>0) { d.className += ' answered'; answeredCount++; }
    d.textContent = q.id;
    d.onclick = () => { curIdx = i; closeQGrid(); renderQ(); };
    grid.appendChild(d);
  });
  const total = curExam.questions.length;
  document.getElementById('qgrid-stats').textContent = submitted
    ? '已批改'
    : `已答 ${answeredCount}/${total}`;
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
function openStudyCards() { window.location.href = 'study_cards.html'; }
function openDashboard() { window.location.href = 'dashboard.html'; }
