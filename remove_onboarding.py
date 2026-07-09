#!/usr/bin/env python3
"""Remove onboarding/plan module from app.js and add weighted scoring."""
import re

with open('/home/betterman/sec-exam-deploy/app.js', encoding='utf-8') as f:
    js = f.read()

# 1. Remove onboarding init check
js = js.replace(
    '    if (!profile) { showPage(\'page-onboard\'); return; }\n    renderHome();',
    '    renderHome();\n    showPage(\'page-home\');'
)

# 2. Remove plan-banner section
old_banner = '''  const banner = document.getElementById('plan-banner');
  if (profile) {
    const dl = daysLeft(profile.date);
    banner.innerHTML = `<div class="plan-card clickable" onclick="showSettings()">
      <div class="flex justify-between items-center">
        <h3>备考计划</h3>
        <span class="text-sm text-dim">${dl}天后考试 ></span>
      </div>
      <div class="row"><span>目标</span><span class="val">${targetLabel(profile.target)}</span></div>
      <div class="row"><span>今日推荐</span><span class="val text-accent fw-600">${renderDailyRec()} 题</span></div>
    </div>`;
  } else {
    banner.innerHTML = `<div class="plan-card clickable text-center" onclick="showPage('page-onboard')">
      <h3>🎯 点击设置备考计划</h3>
      <p class="text-dim">根据你的时间和目标定制学习方案</p>
    </div>`;
  }'''

new_banner = "  document.getElementById('plan-banner').innerHTML = '';"

js = js.replace(old_banner, new_banner)

# 3. Remove profile-related functions
# saveProfile
js = re.sub(
    r'function saveProfile\(\) \{.*?showPage\(\'page-home\'\);\n\}',
    '// Profile module removed',
    js,
    flags=re.DOTALL
)

# showSettings
js = re.sub(
    r'function showSettings\(\) \{.*?showPage\(\'page-settings\'\);\n\}',
    '// Settings removed',
    js,
    flags=re.DOTALL
)

# resetProfile
js = re.sub(
    r'function resetProfile\(\) \{.*?\n\}',
    '// resetProfile removed',
    js,
    flags=re.DOTALL
)

# renderPlan
js = re.sub(
    r'function renderPlan\(\) \{.*?\n\}',
    '// renderPlan removed',
    js,
    flags=re.DOTALL
)

# renderDailyRec
js = re.sub(
    r'function renderDailyRec\(\) \{.*?return.*?;\n\}',
    '// renderDailyRec removed',
    js,
    flags=re.DOTALL
)

# targetLabel
js = re.sub(
    r'function targetLabel\(t\) \{.*?\n\}',
    '// targetLabel removed',
    js,
    flags=re.DOTALL
)

# daysLeft
js = re.sub(
    r'function daysLeft\(d\) \{.*?\n\}',
    '// daysLeft removed',
    js,
    flags=re.DOTALL
)

# 4. Add weighted scoring for mock exams
old_score = '''  submitted = true;
  let correct = 0;
  const examSubject = curExam.subject || (curExam.title || '').includes('金融') ? '金融市场基础知识' : '证券市场基本法律法规';
  curExam.questions.forEach(q => {
    const u = (userAns[q.id]||'').split('').sort().join('');
    const c = q.a.split('').sort().join('');
    const isCorrect = u === c;'''

new_score = '''  submitted = true;
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
    if (isCorrect) { correct++; weightedScore += weight; }'''

js = js.replace(old_score, new_score)

# Replace pct calculation
js = js.replace(
    '  const pct = Math.round(correct/t*100);',
    '  const pct = isFullMock ? Math.round(weightedScore/maxWeighted*100) : Math.round(correct/t*100);'
)

with open('/home/betterman/sec-exam-deploy/app.js', 'w', encoding='utf-8') as f:
    f.write(js)

print("Done - app.js updated")

# Verify
with open('/home/betterman/sec-exam-deploy/app.js', encoding='utf-8') as f:
    content = f.read()

checks = [
    ("onboarding removed", "page-onboard" not in content),
    ("profile init removed", "if (!profile) { showPage" not in content),
    ("plan banner empty", "innerHTML = ''" in content),
    ("weighted scoring", "weightedScore" in content),
    ("isFullMock", "isFullMock" in content),
]

for name, result in checks:
    print(f"  [{'PASS' if result else 'FAIL'}] {name}")
