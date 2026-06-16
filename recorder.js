/**
 * recorder.js — 答题记录引擎
 * 插入到所有试卷HTML中，自动记录答题情况到 localStorage
 * 所有试卷共享同一存储（需通过 HTTP 访问）
 */
(function() {
  'use strict';

  const STORAGE_KEY = 'sec_exam_records';
  const QUIZ_KEY_PREFIX = 'sec_exam_quiz_';

  // ── 数据结构 ──
  // 每条记录: { id, subject, chapter, type, question, userAnswer,
  //             correctAnswer, isCorrect, timestamp, source }
  // 全局存在 localStorage[STORAGE_KEY] 中

  function loadRecords() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch(e) { return []; }
  }

  function saveRecords(records) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
  }

  // ── 公开 API ──
  window.ExamRecorder = {
    // 记录一次答题
    record: function(opts) {
      if (!opts.questionId) return;
      const records = loadRecords();
      // 避免重复记录同一题
      const existing = records.findIndex(r => r.id === opts.questionId);
      const record = {
        id: opts.questionId,
        subject: opts.subject || '',
        chapter: opts.chapter || '',
        type: opts.type || '',          // s/m/j
        typeCn: opts.typeCn || '',
        question: opts.question || '',
        userAnswer: opts.userAnswer || '',
        correctAnswer: opts.correctAnswer || '',
        isCorrect: opts.isCorrect || false,
        timestamp: Date.now(),
        source: opts.source || '',
        // 选项（用于详情弹窗展示）
        choices: opts.choices || null,
        // 知识点
        knowledgePoint: opts.knowledgePoint || '',
      };
      if (existing >= 0) {
        // 更新（重做）
        records[existing] = record;
      } else {
        records.push(record);
      }
      saveRecords(records);
      // 触发自定义事件，方便页面实时更新统计
      document.dispatchEvent(new CustomEvent('exam-record', { detail: record }));
    },

    // 批量导入（从JSON文件恢复）
    importFromJSON: function(jsonStr) {
      try {
        const data = JSON.parse(jsonStr);
        const arr = Array.isArray(data) ? data : [data];
        const records = loadRecords();
        arr.forEach(r => {
          const existing = records.findIndex(x => x.id === r.id);
          if (existing >= 0) records[existing] = r;
          else records.push(r);
        });
        saveRecords(records);
        return { success: true, count: arr.length };
      } catch(e) {
        return { success: false, error: e.message };
      }
    },

    // 导出所有记录
    exportJSON: function() {
      return JSON.stringify(loadRecords(), null, 2);
    },

    // 获取统计
    getStats: function() {
      const records = loadRecords();
      const total = records.length;
      const correct = records.filter(r => r.isCorrect).length;
      const byChapter = {};
      const byType = { s: {total:0, correct:0}, m: {total:0, correct:0}, j: {total:0, correct:0} };
      records.forEach(r => {
        const ch = r.chapter || '未知';
        if (!byChapter[ch]) byChapter[ch] = { total: 0, correct: 0 };
        byChapter[ch].total++;
        byChapter[ch].correct += r.isCorrect ? 1 : 0;
        const t = r.type || 's';
        if (byType[t]) {
          byType[t].total++;
          byType[t].correct += r.isCorrect ? 1 : 0;
        }
      });
      // 计算各章正确率并排序
      const chapterStats = Object.entries(byChapter)
        .map(([ch, v]) => ({
          chapter: ch,
          total: v.total,
          correct: v.correct,
          rate: v.total > 0 ? (v.correct / v.total * 100).toFixed(1) : 0
        }))
        .sort((a, b) => a.rate - b.rate);  // 弱的在前面

      return {
        total,
        correct,
        accuracy: total > 0 ? (correct / total * 100).toFixed(1) : 0,
        byChapter: chapterStats,
        byType: {
          single: { total: byType.s.total, correct: byType.s.correct, rate: byType.s.total > 0 ? (byType.s.correct/byType.s.total*100).toFixed(1) : 0 },
          multi: { total: byType.m.total, correct: byType.m.correct, rate: byType.m.total > 0 ? (byType.m.correct/byType.m.total*100).toFixed(1) : 0 },
          judge: { total: byType.j.total, correct: byType.j.correct, rate: byType.j.total > 0 ? (byType.j.correct/byType.j.total*100).toFixed(1) : 0 },
        }
      };
    },

    // 清空所有记录
    clear: function() {
      if (confirm('确定清除所有答题记录？')) {
        localStorage.removeItem(STORAGE_KEY);
        location.reload();
      }
    },

    // 获取第X题当前的答题状态（用于恢复）
    getRecord: function(questionId) {
      const records = loadRecords();
      return records.find(r => r.id === questionId) || null;
    }
  };

  // ── 导出按钮辅助 ──
  window.downloadRecords = function() {
    const data = window.ExamRecorder.exportJSON();
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `答题记录_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  console.log('📝 ExamRecorder loaded — 答题记录引擎就绪');
})();
