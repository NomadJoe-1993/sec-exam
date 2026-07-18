"""
证从刷题 · 会员激活后端
轻量 Flask 服务，提供：
  1. 管理面板 — 批量生成码/导出/库存管理
  2. 激活 API — 验证码并激活用户
  3. 状态 API — 查询会员状态
  4. Webhook/API — 对接发卡平台自动发货

数据库：SQLite (无需额外服务)
"""

import hashlib
import io
import json
import csv
import os
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, redirect, session, make_response
from flask_cors import CORS

# ─── 配置 ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "membership.db"
ADMIN_TOKEN_FILE = BASE_DIR / "data" / ".admin_token"
SECRET_KEY_FILE = BASE_DIR / "data" / ".flask_secret"

ADMIN_PASSWORD_ENV = "ADMIN_PASSWORD"
DEFAULT_ADMIN_PW = "admin888"

CODE_EXPIRY_DAYS = 365
CHAR_POOL = string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")
CODE_PREFIX = "ZC"

# ─── 应用初始化 ───────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

os.makedirs(BASE_DIR / "data", exist_ok=True)
if SECRET_KEY_FILE.exists():
    app.secret_key = SECRET_KEY_FILE.read_text().strip()
else:
    app.secret_key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(app.secret_key)


# ─── 数据库 ───────────────────────────────────────────────
def get_db():
    os.makedirs(BASE_DIR / "data", exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS activation_codes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash       TEXT NOT NULL UNIQUE,
            code_plaintext  TEXT,                   -- 明文码（仅管理面板可见，用于导出）
            code_prefix     TEXT NOT NULL,
            is_used         INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            used_by         TEXT,
            used_at         TEXT,
            expires_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS members (
            username    TEXT PRIMARY KEY,
            is_member   INTEGER NOT NULL DEFAULT 0,
            activated_at TEXT,
            expires_at  TEXT,
            code_used   TEXT,
            last_active TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_codes_hash ON activation_codes(code_hash);
        CREATE INDEX IF NOT EXISTS idx_codes_used ON activation_codes(is_used);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS userdata (
            username    TEXT PRIMARY KEY,
            history     TEXT NOT NULL DEFAULT '{}',
            wrong_book  TEXT NOT NULL DEFAULT '[]',
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ─── 工具函数 ─────────────────────────────────────────────
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def generate_code() -> str:
    """格式: ZC-XXXX-XXXX-XXXX"""
    def _block(n=4):
        return ''.join(secrets.choice(CHAR_POOL) for _ in range(n))
    return f"{CODE_PREFIX}-{_block()}-{_block()}-{_block()}"


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            stored = load_admin_token()
            if token == stored:
                return f(*args, **kwargs)
            return jsonify({"error": "unauthorized"}), 401

        if session.get("admin_logged_in"):
            return f(*args, **kwargs)

        return redirect("/admin/login")
    return decorated


def load_admin_token():
    if ADMIN_TOKEN_FILE.exists():
        return ADMIN_TOKEN_FILE.read_text().strip()
    token = secrets.token_hex(24)
    ADMIN_TOKEN_FILE.write_text(token)
    return token


def get_admin_password():
    pw = os.environ.get(ADMIN_PASSWORD_ENV, DEFAULT_ADMIN_PW)
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()
    conn.close()
    if row:
        return row["value"]
    return sha256(pw)


def set_admin_password(new_pw):
    pw_hash = sha256(new_pw)
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_password_hash', ?)", (pw_hash,))
    conn.commit()
    conn.close()
    return pw_hash


# ─── 首页 / 健康检查 ──────────────────────────────────────
@app.route("/")
def index():
    return jsonify({
        "service": "证从刷题 · 会员系统",
        "version": "1.1.0",
        "status": "running",
        "docs": "/admin"
    })


# ─── 管理面板 ─────────────────────────────────────────────
ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>管理员登录 · 证从刷题</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
body{background:#f5efe6;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#faf6f0;padding:32px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.08);width:360px;max-width:90vw}
h2{color:#1e5b8a;margin-bottom:20px;text-align:center}
input{width:100%;padding:10px 14px;border:1px solid #d4c9b8;border-radius:8px;font-size:14px;margin-bottom:12px;outline:none;background:white}
input:focus{border-color:#1e5b8a}
button{width:100%;padding:10px;background:#1e5b8a;color:white;border:none;border-radius:8px;font-size:14px;cursor:pointer;font-weight:600}
button:hover{background:#164a6e}
.error{color:#c23b22;text-align:center;font-size:13px;margin-top:8px}
</style>
</head>
<body>
<div class="card">
<h2>🔐 管理员登录</h2>
<form method="POST">
<input type="password" name="password" placeholder="管理密码" autofocus>
<button type="submit">登录</button>
</form>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
</div>
</body>
</html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>管理面板 · 证从刷题</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
body{background:#f5efe6;padding:16px;color:#3d3229}
.container{max-width:960px;margin:0 auto}
h1{color:#1e5b8a;font-size:20px;margin-bottom:16px}
h2{color:#1e5b8a;font-size:16px;margin:12px 0 8px}
.card{background:#faf6f0;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.stat-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.stat{flex:1;min-width:80px;background:#faf6f0;border-radius:10px;padding:12px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.stat .num{font-size:22px;font-weight:700}
.stat .num.blue{color:#1e5b8a}
.stat .num.green{color:#3d7246}
.stat .num.red{color:#c23b22}
.stat .num.gold{color:#c9a96e}
.stat .lbl{font-size:11px;color:#8b7e6e;margin-top:2px}
.btn{display:inline-block;padding:7px 16px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;text-decoration:none;line-height:1.4}
.btn-primary{background:#1e5b8a;color:white}
.btn-primary:hover{background:#164a6e}
.btn-success{background:#3d7246;color:white}
.btn-danger{background:#c23b22;color:white}
.btn-outline{background:white;border:1.5px solid #d4c9b8;color:#3d3229}
.btn-outline:hover{background:#f5efe6}
.btn-sm{padding:4px 10px;font-size:11px}
.mt-8{margin-top:8px}
.mb-8{margin-bottom:8px}
.flex{display:flex;align-items:center;gap:8px}
.flex-wrap{flex-wrap:wrap}
.justify-between{justify-content:space-between}
.text-dim{color:#8b7e6e;font-size:12px}
.text-sm{font-size:12px}
.text-center{text-align:center}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:5px 6px;text-align:left;border-bottom:1px solid #e8dfd0}
th{color:#8b7e6e;font-weight:600;font-size:10px;text-transform:uppercase;white-space:nowrap}
.tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}
.tag-used{background:#e8f5e9;color:#2e7d32}
.tag-active{background:#fff3e0;color:#e65100}
.gen-area{margin-top:10px;padding:14px;background:#e8f5e9;border-radius:8px;display:none}
.gen-area .code-row{display:flex;align-items:center;gap:8px;margin-bottom:5px;padding:6px 10px;background:white;border-radius:6px;border:1px solid #c8e6c9}
.gen-area .code-text{font-size:16px;font-weight:700;letter-spacing:1px;color:#1e5b8a;font-family:'Courier New',monospace;flex:1;user-select:all}
.gen-area .code-idx{color:#8b7e6e;font-size:11px;min-width:24px}
.copy-btn{background:white;border:1px solid #d4c9b8;padding:4px 10px;border-radius:5px;cursor:pointer;font-size:11px;transition:all .15s}
.copy-btn:hover{background:#1e5b8a;color:white;border-color:#1e5b8a}
.copy-btn.copied{background:#3d7246;color:white;border-color:#3d7246}
.tabs{display:flex;gap:4px;margin-bottom:12px;border-bottom:1.5px solid #e8dfd0;padding-bottom:0}
.tab{padding:8px 16px;cursor:pointer;font-size:13px;font-weight:600;color:#8b7e6e;border-bottom:2.5px solid transparent;transition:all .15s}
.tab:hover{color:#1e5b8a}
.tab.active{color:#1e5b8a;border-bottom-color:#1e5b8a}
.tab-content{display:none}
.tab-content.active{display:block}
.input-count{width:70px;padding:6px 10px;border:1px solid #d4c9b8;border-radius:6px;font-size:14px;text-align:center;outline:none}
.input-count:focus{border-color:#1e5b8a}
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#3d7246;color:white;padding:8px 20px;border-radius:8px;font-size:13px;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
.toast.error{background:#c23b22}
select{padding:6px 10px;border:1px solid #d4c9b8;border-radius:6px;font-size:13px;outline:none;background:white}
.pagination{display:flex;gap:4px;justify-content:center;margin-top:10px;flex-wrap:wrap}
.pagination .page-btn{padding:4px 10px;border:1px solid #d4c9b8;border-radius:4px;cursor:pointer;font-size:11px;background:white}
.pagination .page-btn.active{background:#1e5b8a;color:white;border-color:#1e5b8a}
.badge-new{background:#ff9800;color:white;font-size:9px;padding:1px 5px;border-radius:3px;margin-left:4px}
.export-formats{display:flex;gap:8px;margin-top:8px}
</style>
</head>
<body>
<div class="container">
<div class="flex justify-between mb-8">
<h1>📋 证从刷题 · 自动发卡管理</h1>
<a href="/admin/logout" style="color:#8b7e6e;font-size:12px;text-decoration:none">退出</a>
</div>

<!-- ===== 统计 ===== -->
<div class="stat-row">
<div class="stat"><div class="num blue">{{ stats.total }}</div><div class="lbl">总生成</div></div>
<div class="stat"><div class="num green">{{ stats.available }}</div><div class="lbl">可用库存</div></div>
<div class="stat"><div class="num red">{{ stats.used }}</div><div class="lbl">已使用</div></div>
<div class="stat"><div class="num gold">{{ stats.members }}</div><div class="lbl">激活用户</div></div>
</div>

<!-- ===== tabs ===== -->
<div class="tabs">
<div class="tab active" data-tab="generate" onclick="switchTab('generate')">🎫 生成码</div>
<div class="tab" data-tab="export" onclick="switchTab('export')">📦 库存导出</div>
<div class="tab" data-tab="codes" onclick="switchTab('codes')">📜 码列表</div>
<div class="tab" data-tab="webhook" onclick="switchTab('webhook')">🔗 发卡平台</div>
</div>

<!-- ===== Tab: 生成 ===== -->
<div class="tab-content active" id="tab-generate">
<div class="card">
<div class="flex flex-wrap" style="gap:8px">
<label style="font-size:13px;font-weight:600">生成数量：</label>
<input type="number" class="input-count" id="gen-count" value="10" min="1" max="500">
<button class="btn btn-primary" onclick="generateCodes()">🚀 批量生成</button>
</div>
<div class="text-dim" style="margin-top:6px">单次最多 500 个，生成后自动存入库存</div>
<div id="gen-area" class="gen-area"></div>
</div>
</div>

<!-- ===== Tab: 导出 ===== -->
<div class="tab-content" id="tab-export">
<div class="card">
<h2>📦 库存管理</h2>
<div class="stat-row" style="margin-bottom:8px">
<div class="stat"><div class="num green">{{ stats.available }}</div><div class="lbl">可用码</div></div>
<div class="stat"><div class="num">{{ stats.total }}</div><div class="lbl">总码数</div></div>
</div>
<div class="export-formats">
<button class="btn btn-success" onclick="exportCodes('csv')">📥 导出 CSV（发卡平台格式）</button>
<button class="btn btn-outline" onclick="exportCodes('txt')">📥 导出 TXT（每行一个）</button>
<button class="btn btn-outline" onclick="copyAllCodes()">📋 一键复制全部</button>
</div>

<!-- 闲鱼自动发货专用 -->
<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:10px;margin-top:10px">
<div class="flex" style="margin-bottom:6px">
<span style="font-weight:600;font-size:13px">🐟 闲鱼自动发货</span>
<span class="tag tag-active" style="font-size:10px">0费率</span>
</div>
<p class="text-sm text-dim" style="margin-bottom:8px">导出后复制到闲鱼「设置自动发货」→ 卡密发货，一行一个</p>
<div class="flex" style="gap:6px">
<button class="btn btn-primary" onclick="exportCodes('xianyu')">📤 导出闲鱼格式</button>
<button class="btn btn-sm btn-outline" onclick="copyAllCodes()">📋 复制全部到剪贴板</button>
</div>
<div class="text-dim" style="margin-top:6px;font-size:11px">
操作路径：闲鱼APP → 我的 → 我卖出的 → 找到商品 → 设置自动发货 → 卡密发货 → 粘贴
</div>
</div>

<div class="text-dim" style="margin-top:8px">只导出未使用的激活码，按生成时间排序</div>
</div>
</div>

<!-- ===== Tab: 码列表 ===== -->
<div class="tab-content" id="tab-codes">
<div class="card">
<div class="flex justify-between">
<h2>📜 激活码列表</h2>
<div class="flex">
<select id="filter-status" onchange="loadCodes(1)">
<option value="all">全部</option>
<option value="active">可用</option>
<option value="used">已用</option>
</select>
<button class="btn btn-sm btn-outline" onclick="loadCodes(1)">🔄 刷新</button>
</div>
</div>
<div id="codes-table-wrap"><div class="text-dim text-center" style="padding:20px">加载中...</div></div>
<div id="codes-pagination" class="pagination"></div>
</div>
</div>

<!-- ===== Tab: 发卡平台对接 ===== -->
<div class="tab-content" id="tab-webhook">
<div class="card">
<h2>🔗 发卡平台自动对接</h2>
<p class="text-dim" style="margin-bottom:10px">一键推送可用码到发卡平台，买家付款后自动发货</p>

<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px;margin-bottom:10px">
<div class="flex" style="margin-bottom:6px">
<span style="font-weight:600;font-size:13px">🌐 千寻寄售 qianxun1688.com</span>
<span class="tag tag-active" style="font-size:10px">推荐</span>
</div>
<p class="text-sm text-dim">全自动秒发 · 支付宝/微信支付 · T+0结算 · 费率约5%</p>
<div class="flex flex-wrap" style="margin-top:8px;gap:6px">
<button class="btn btn-sm btn-primary" onclick="pushToQianxun()">📤 推送到千寻寄售</button>
<button class="btn btn-sm btn-outline" onclick="exportCodes('qianxun')">📥 下载千寻格式CSV</button>
</div>
</div>

<div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;padding:12px">
<div class="flex" style="margin-bottom:6px">
<span style="font-weight:600;font-size:13px">📡 Webhook 直连</span>
</div>
<p class="text-sm text-dim">支持任意发卡平台回调，配置 webhook 后自动生成并推送码</p>
<div style="margin-top:6px">
<label style="font-size:12px;font-weight:600">Webhook URL：</label>
<input type="text" id="webhook-url" value="http://120.55.163.229/api/orders/webhook" readonly style="width:100%;padding:6px 10px;border:1px solid #d4c9b8;border-radius:6px;font-size:12px;margin-top:4px;background:#faf6f0">
</div>
<div class="text-dim" style="margin-top:4px;font-size:11px">在发卡平台后台配置此回调地址，secret 需双方约定一致</div>
</div>
</div>
</div>

</div>

<div id="toast" class="toast"></div>

<script>
// ── Tab switching ──
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.toggle('active', t.id === 'tab-' + tab));
}

// ── Toast ──
function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast' + (isError ? ' error' : '');
  setTimeout(() => t.classList.add('show'), 10);
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── Copy helper ──
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    if (btn) { btn.textContent = '✅'; btn.classList.add('copied'); setTimeout(() => { btn.textContent = '📋'; btn.classList.remove('copied'); }, 1500); }
    return true;
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    if (btn) { btn.textContent = '✅'; btn.classList.add('copied'); setTimeout(() => { btn.textContent = '📋'; btn.classList.remove('copied'); }, 1500); }
    return true;
  }
}

// ── Generate codes ──
async function generateCodes() {
  const count = Math.min(parseInt(document.getElementById('gen-count').value) || 10, 500);
  const area = document.getElementById('gen-area');
  area.style.display = 'block';
  area.innerHTML = '<div class="text-dim">⏳ 生成中...</div>';
  try {
    const r = await fetch('/api/admin/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer {{ token }}'},
      body: JSON.stringify({count})
    });
    const data = await r.json();
    if (data.codes) {
      let html = `<div class="text-sm" style="margin-bottom:8px">✅ 成功生成 ${data.codes.length} 个激活码：</div>`;
      data.codes.forEach((c, i) => {
        html += `<div class="code-row">
          <span class="code-idx">#${i+1}</span>
          <span class="code-text">${c}</span>
          <button class="copy-btn" onclick="copyText('${c}', this)">📋</button>
        </div>`;
      });
      html += '<div style="margin-top:6px"><button class="btn btn-sm btn-outline" onclick="document.getElementById(\\'gen-area\\').style.display=\\'none\\'">收起</button></div>';
      area.innerHTML = html;
      showToast(`✅ 成功生成 ${data.codes.length} 个码`);
      setTimeout(() => window.location.reload(), 1500);
    } else {
      area.innerHTML = `<div class="text-sm" style="color:#c23b22">❌ ${data.error || '生成失败'}</div>`;
    }
  } catch(e) {
    area.innerHTML = `<div class="text-sm" style="color:#c23b22">❌ ${e.message}</div>`;
  }
}

// ── Export ──
async function exportCodes(format) {
  try {
    const r = await fetch('/api/admin/export?format=' + format, {
      headers: {'Authorization': 'Bearer {{ token }}'}
    });
    if (!r.ok) { showToast('导出失败', true); return; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'activation_codes_' + new Date().toISOString().slice(0,10) + '.' + (format === 'csv' ? 'csv' : 'txt');
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ 已下载 ' + format.toUpperCase() + ' 文件');
  } catch(e) { showToast('导出失败: ' + e.message, true); }
}

// ── Copy all codes ──
async function copyAllCodes() {
  try {
    const r = await fetch('/api/admin/export?format=txt', {
      headers: {'Authorization': 'Bearer {{ token }}'}
    });
    const text = await r.text();
    await copyText(text.trim());
    showToast('✅ 已复制 ' + text.trim().split('\\n').length + ' 个码到剪贴板');
  } catch(e) { showToast('复制失败: ' + e.message, true); }
}

// ── Push to 千寻寄售 ──
async function pushToQianxun() {
  showToast('⏳ 正在推送...');
  try {
    const r = await fetch('/api/admin/export?format=qianxun_api', {
      headers: {'Authorization': 'Bearer {{ token }}'}
    });
    const data = await r.json();
    if (data.codes && data.codes.length > 0) {
      // Open 千寻寄售 in new tab with instructions
      window.open('https://qianxun1688.com', '_blank');
      showToast('✅ 已生成 ' + data.codes.length + ' 个码，请在千寻后台导入');
      // Also download CSV
      const r2 = await fetch('/api/admin/export?format=qianxun', {
        headers: {'Authorization': 'Bearer {{ token }}'}
      });
      const blob = await r2.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'qianxun_import_' + new Date().toISOString().slice(0,10) + '.csv';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else {
      showToast('❌ 没有可用码可导出', true);
    }
  } catch(e) { showToast('❌ ' + e.message, true); }
}

// ── Load codes with pagination ──
let currentPage = 1;

async function loadCodes(page) {
  currentPage = page || 1;
  const status = document.getElementById('filter-status').value;
  const wrap = document.getElementById('codes-table-wrap');
  wrap.innerHTML = '<div class="text-dim text-center" style="padding:20px">⏳ 加载中...</div>';
  try {
    const r = await fetch('/api/admin/codes?page=' + currentPage + '&status=' + status + '&per_page=30', {
      headers: {'Authorization': 'Bearer {{ token }}'}
    });
    if (!r.ok) { wrap.innerHTML = '<div class="text-dim text-center">加载失败</div>'; return; }
    const data = await r.json();
    if (data.codes.length === 0) {
      wrap.innerHTML = '<div class="text-dim text-center" style="padding:20px">暂无数据</div>';
      document.getElementById('codes-pagination').innerHTML = '';
      return;
    }
    let html = '<table><thead><tr><th>#</th><th>码 (前8位)</th><th>状态</th><th>生成时间</th><th>使用者</th></tr></thead><tbody>';
    data.codes.forEach((c, i) => {
      const statusLabel = c.is_used
        ? '<span class="tag tag-used">已使用</span>'
        : '<span class="tag tag-active">可用</span>';
      html += `<tr>
        <td>${(data.page-1)*data.per_page + i + 1}</td>
        <td><code style="background:#f5efe6;padding:1px 5px;border-radius:3px;font-size:11px">${c.code_prefix}•••</code></td>
        <td>${statusLabel}</td>
        <td style="font-size:11px;color:#8b7e6e">${(c.created_at||'').slice(0,10)}</td>
        <td style="font-size:11px">${c.used_by || '-'}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;

    // Pagination
    const totalPages = Math.ceil(data.total / data.per_page);
    let phtml = '';
    for (let p = 1; p <= totalPages; p++) {
      phtml += `<div class="page-btn ${p === data.page ? 'active' : ''}" onclick="loadCodes(${p})">${p}</div>`;
    }
    document.getElementById('codes-pagination').innerHTML = phtml;
    if (totalPages <= 1) document.getElementById('codes-pagination').innerHTML = '';
  } catch(e) {
    wrap.innerHTML = '<div class="text-dim text-center">加载失败</div>';
  }
}

// ── Init ──
loadCodes(1);
</script>
</body>
</html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        stored_hash = get_admin_password()
        if sha256(pw) == stored_hash:
            session["admin_logged_in"] = True
            session.permanent = True
            return redirect("/admin")
        return render_template_string(ADMIN_LOGIN_HTML, error="密码错误")
    return render_template_string(ADMIN_LOGIN_HTML, error="")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")


@app.route("/admin")
@app.route("/admin/")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    stats = {
        "total": conn.execute("SELECT COUNT(*) FROM activation_codes").fetchone()[0],
        "used": conn.execute("SELECT COUNT(*) FROM activation_codes WHERE is_used=1").fetchone()[0],
        "members": conn.execute("SELECT COUNT(*) FROM members WHERE is_member=1").fetchone()[0],
    }
    stats["available"] = stats["total"] - stats["used"]
    conn.close()

    return render_template_string(ADMIN_DASHBOARD_HTML, stats=stats, token=load_admin_token())


# ─── 管理 API ─────────────────────────────────────────────
@app.route("/api/admin/generate", methods=["POST"])
@admin_required
def api_generate():
    data = request.get_json(silent=True) or {}
    count = min(int(data.get("count", 1)), 500)
    if count < 1:
        return jsonify({"error": "count must be >= 1"}), 400

    conn = get_db()
    new_codes = []
    for _ in range(count):
        code = generate_code()
        code_hash = sha256(code)
        prefix = code[:7]
        expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO activation_codes (code_hash, code_plaintext, code_prefix, expires_at) VALUES (?, ?, ?, ?)",
            (code_hash, code, prefix, expires)
        )
        new_codes.append(code)
    conn.commit()
    conn.close()

    return jsonify({"codes": new_codes, "count": len(new_codes)})


@app.route("/api/admin/codes", methods=["GET"])
@admin_required
def api_list_codes():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(10, int(request.args.get("per_page", 30))))
    status = request.args.get("status", "all")

    conn = get_db()
    where = ""
    if status == "active":
        where = "WHERE is_used=0"
    elif status == "used":
        where = "WHERE is_used=1"

    total = conn.execute(f"SELECT COUNT(*) FROM activation_codes {where}").fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT code_prefix, is_used, created_at, used_by, used_at FROM activation_codes {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    conn.close()

    return jsonify({
        "codes": [dict(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, (total + per_page - 1) // per_page)
    })


@app.route("/api/admin/export", methods=["GET"])
@admin_required
def api_export():
    """导出可用激活码"""
    format_type = request.args.get("format", "csv")

    conn = get_db()
    rows = conn.execute(
        "SELECT code_plaintext, code_prefix, created_at FROM activation_codes WHERE is_used=0 ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    if format_type == "qianxun_api":
        codes = [r["code_plaintext"] for r in rows if r["code_plaintext"]]
        return jsonify({"codes": codes, "count": len(codes)})

    if format_type == "txt" or format_type == "xianyu":
        text = "\n".join(r["code_plaintext"] for r in rows if r["code_plaintext"])
        fname = "xianyu_import" if format_type == "xianyu" else "activation_codes"
        response = make_response(text)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename={fname}_{datetime.now().strftime('%Y%m%d')}.txt"
        return response

    if format_type == "qianxun":
        # 千寻寄售 CSV 格式：卡密,有效期,价格
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["卡密", "有效期", "价格"])
        for r in rows:
            if r["code_plaintext"]:
                expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).strftime("%Y-%m-%d")
                writer.writerow([r["code_plaintext"], expires, ""])
        csv_content = output.getvalue()
        response = make_response(csv_content)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename=qianxun_import_{datetime.now().strftime('%Y%m%d')}.csv"
        return response

    # Default: CSV (发卡平台通用格式)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["序号", "激活码", "状态", "有效期至"])
    for i, r in enumerate(rows, 1):
        if r["code_plaintext"]:
            expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).strftime("%Y-%m-%d")
            writer.writerow([i, r["code_plaintext"], "可用", expires])

    csv_content = output.getvalue()
    response = make_response(csv_content)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename=activation_codes_{datetime.now().strftime('%Y%m%d')}.csv"
    return response


@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_stats():
    conn = get_db()
    stats = {
        "total": conn.execute("SELECT COUNT(*) FROM activation_codes").fetchone()[0],
        "used": conn.execute("SELECT COUNT(*) FROM activation_codes WHERE is_used=1").fetchone()[0],
        "members": conn.execute("SELECT COUNT(*) FROM members WHERE is_member=1").fetchone()[0],
    }
    stats["available"] = stats["total"] - stats["used"]

    # Last 7 days generated
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stats["generated_7d"] = conn.execute(
        "SELECT COUNT(*) FROM activation_codes WHERE created_at > ?", (week_ago,)
    ).fetchone()[0]
    stats["activated_7d"] = conn.execute(
        "SELECT COUNT(*) FROM activation_codes WHERE is_used=1 AND used_at > ?", (week_ago,)
    ).fetchone()[0]
    conn.close()

    return jsonify(stats)


# ─── 发卡平台 API ─────────────────────────────────────────
@app.route("/api/faka/webhook", methods=["POST"])
def faka_webhook():
    """
    发卡平台订单回调
    当买家付款后，发卡平台调此接口获取激活码

    期望格式 (JSON):
    {
      "order_id": "xxx",
      "product_id": "xxx",
      "buyer": "xxx",
      "secret": "shared_secret"
    }
    返回:
    {
      "success": true,
      "code": "ZC-XXXX-XXXX-XXXX"
    }
    """
    FAKA_SECRET = os.environ.get("FAKA_WEBHOOK_SECRET", "change-me")

    data = request.get_json(silent=True) or {}
    if data.get("secret") != FAKA_SECRET:
        return jsonify({"error": "invalid secret"}), 401

    conn = get_db()
    # 找一个未使用的码
    row = conn.execute(
        "SELECT id, code_hash, code_plaintext, code_prefix FROM activation_codes WHERE is_used=0 ORDER BY created_at ASC LIMIT 1"
    ).fetchone()

    if not row:
        # 库存不足，自动生成一个
        code = generate_code()
        code_hash = sha256(code)
        prefix = code[:7]
        expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()
        conn.execute(
            "INSERT INTO activation_codes (code_hash, code_plaintext, code_prefix, expires_at) VALUES (?, ?, ?, ?)",
            (code_hash, code, prefix, expires)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "code": code, "note": "auto-generated"})

    # 标记为已使用
    buyer = data.get("buyer", "faka_auto")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE activation_codes SET is_used=1, used_by=?, used_at=? WHERE id=?", (buyer, now, row["id"]))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "code": row["code_plaintext"] or row["code_prefix"] + "...", "note": "ok"})


# ─── 用户 API ─────────────────────────────────────────────

@app.route("/api/user/sync", methods=["GET", "POST"])
def user_sync():
    if request.method == "GET":
        username = request.args.get("username")
        if not username:
            return jsonify({"error": "username required"}), 400
        conn = get_db()
        row = conn.execute(
            "SELECT history, wrong_book FROM userdata WHERE username=?",
            (username,)
        ).fetchone()
        conn.close()
        if row:
            return jsonify({
                "history": json.loads(row["history"]),
                "wrongBook": json.loads(row["wrong_book"])
            })
        return jsonify({"history": {}, "wrongBook": []})

    # POST
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"error": "username required"}), 400

    history_str = json.dumps(data.get("history", {}), ensure_ascii=False, default=str)
    wrong_book_str = json.dumps(data.get("wrongBook", []), ensure_ascii=False, default=str)

    conn = get_db()
    conn.execute(
        "INSERT INTO userdata (username, history, wrong_book, updated_at) "
        "VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(username) DO UPDATE SET "
        "history=excluded.history, wrong_book=excluded.wrong_book, "
        "updated_at=datetime('now')",
        (username, history_str, wrong_book_str)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/user/status", methods=["GET"])
def api_user_status():

    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"error": "username required"}), 400

    conn = get_db()
    row = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    conn.close()

    if not row or not row["is_member"]:
        return jsonify({"is_member": False})

    expires = row["expires_at"]
    is_expired = expires and expires < datetime.now(timezone.utc).isoformat()

    return jsonify({
        "is_member": not is_expired,
        "expires_at": row["expires_at"],
        "activated_at": row["activated_at"]
    })


@app.route("/api/activate", methods=["POST"])
def api_activate():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip().upper()
    username = data.get("username", "").strip()

    if not code or not username:
        return jsonify({"success": False, "error": "code and username required"}), 400

    code_hash = sha256(code)

    conn = get_db()

    row = conn.execute("SELECT * FROM activation_codes WHERE code_hash=?", (code_hash,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "激活码无效"}), 404

    if row["is_used"]:
        conn.close()
        return jsonify({"success": False, "error": "激活码已被使用"}), 409

    user = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    if user and user["is_member"]:
        expires = user["expires_at"]
        if expires and expires > datetime.now(timezone.utc).isoformat():
            conn.close()
            return jsonify({"success": False, "error": "该账号已是会员"}), 409

    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()

    conn.execute("UPDATE activation_codes SET is_used=1, used_by=?, used_at=? WHERE id=?",
                 (username, now, row["id"]))

    conn.execute(
        "INSERT OR REPLACE INTO members (username, is_member, activated_at, expires_at, code_used, last_active) VALUES (?, 1, ?, ?, ?, ?)",
        (username, now, expires_at, row["code_prefix"], now)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "expires_at": expires_at,
        "message": f"🎉 激活成功！有效期至 {expires_at[:10]}"
    })


# ─── 闲鱼自动发货 Webhook ────────────────────────────────
@app.route("/api/orders/webhook", methods=["POST"])
def orders_webhook():
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-in-production")

    data = request.get_json(silent=True) or {}
    secret = data.get("secret", "")
    if secret != WEBHOOK_SECRET:
        return jsonify({"error": "invalid secret"}), 401

    code = generate_code()
    code_hash = sha256(code)
    prefix = code[:7]
    expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO activation_codes (code_hash, code_plaintext, code_prefix, expires_at) VALUES (?, ?, ?, ?)",
        (code_hash, code, prefix, expires)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "activation_code": code,
        "expires_at": expires,
        "order_id": data.get("order_id", "")
    })


# ─── 启动 ─────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    init_db()
    print(f"📚 证从刷题 · 会员系统 v1.1.0")
    print(f"   DB:     {DB_PATH}")
    print(f"   Token:  {load_admin_token()[:16]}...")
    print(f"   管理面板: http://localhost:{port}/admin")
    print(f"   发卡Webhook: POST /api/faka/webhook")
    print(f"   闲鱼Webhook: POST /api/orders/webhook")
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
