#!/usr/bin/env python3
"""Audit all question JSON files for numbering + answer correctness."""
import json, glob, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

json_files = sorted(glob.glob('*.json'))
skip_files = {'manifest.json', 'real_exam_data.json', 'gw_fin.json', 'gw_law.json',
              'check_comp.py', 'check_real_match.py', 'audit_questions.py',
              'gen_exam_papers.py', 'gen_exam_papers_v2.py', 'gen_exam_papers_v3.py',
              'gen_section_practice.py', 'start-server.bat'}
json_files = [f for f in json_files if f not in skip_files and not f.endswith('.html')]

report = []
total_questions = 0
total_issues = 0
type_dist = {}

for fname in json_files:
    with open(fname) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            report.append("{}: JSON parse error - {}".format(fname, e))
            total_issues += 1
            continue

    questions = data.get('questions', [])
    if not questions:
        continue

    total_questions += len(questions)
    issues = []

    # Track question type distribution
    for q in questions:
        qt = q.get('type', 'unknown')
        type_dist[qt] = type_dist.get(qt, 0) + 1

    # Check 1: Sequential IDs
    ids = [q.get('id', 0) for q in questions]
    non_seq = sum(1 for i, qid in enumerate(ids) if qid != i + 1)
    if non_seq > 0:
        first_bad = [(i+1, ids[i]) for i in range(min(5, len(ids))) if ids[i] != i+1]
        issues.append("  ID非连续: {}/{} 题异常, 例如 {}".format(non_seq, len(questions), first_bad))

    # Check 2: Missing required fields
    for i, q in enumerate(questions):
        missing = []
        for field in ['type', 'q', 'c', 'a']:
            if field not in q or not q.get(field):
                missing.append(field)
        if missing:
            issues.append("  题{}(id={}): 缺少字段 {}".format(i+1, q.get('id','?'), missing))

        # Check type validity
        if q.get('type') not in ('single', 'multi', 'judge', 'comprehensive'):
            issues.append("  题{}(id={}): 未知题型 '{}'".format(i+1, q.get('id','?'), q.get('type')))

    # Check 3: Answer format consistency
    for i, q in enumerate(questions):
        qtype = q.get('type', '')
        ans = q.get('a', '')
        if not ans:
            issues.append("  题{}(id={}): 答案为空".format(i+1, q.get('id','?')))
            continue
        if qtype == 'judge':
            if ans not in ('A', 'B', '1', '0', '对', '错'):
                issues.append("  题{}(id={}): 判断题答案异常 '{}'".format(i+1, q.get('id','?'), ans))
        elif qtype == 'single':
            if len(ans) != 1:
                issues.append("  题{}(id={}): 单选答案应为单个字母 '{}'".format(i+1, q.get('id','?'), ans))

    # Check 4: Answer references exist in choices
    for i, q in enumerate(questions):
        choices = q.get('c', {})
        ans = q.get('a', '')
        if ans:
            ans_chars = ans.replace(',', '').replace(' ', '').replace('、', '')
            for c in ans_chars:
                if c not in choices:
                    issues.append("  题{}(id={}): 答案'{}'不在选项中(选项:{})".format(
                        i+1, q.get('id','?'), c, list(choices.keys())))

    if issues:
        report.append("{} ({}题): {} 个问题".format(fname, len(questions), len(issues)))
        report.extend(issues)
        total_issues += len(issues)
    else:
        report.append("{} ({}题): 通过".format(fname, len(questions)))

report.append("\n题型分布: {}".format(type_dist))
report.append("总计: {}文件, {}题, {}个问题".format(len(json_files), total_questions, total_issues))
print('\n'.join(report))
