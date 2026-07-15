"""
证从刷题 · 会员激活后端
轻量 Flask 服务，提供：
  1. 管理面板 — 生成/查看激活码
  2. 激活 API — 验证码并激活用户
  3. 状态 API — 查询会员状态
  4. Webhook — 对接闲鱼自动发货

数据库：SQLite (无需额外服务)
部署：支持 gunicorn / flask run
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, redirect, session
from flask_cors import CORS

# ─── 配置 ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "membership.db"
ADMIN_TOKEN_FILE = BASE_DIR / "data" / ".admin_token"
SECRET_KEY_FILE = BASE_DIR / "data" / ".flask_secret"

# 默认管理密码（首次启动时用，登录后会重设）
ADMIN_PASSWORD_ENV = "ADMIN_PASSWORD"
DEFAULT_ADMIN_PW = "admin888"  # 首次启动后请立即修改！

CODE_EXPIRY_DAYS = 365       # 激活码有效期
CHAR_POOL = string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")
CODE_PREFIX = "ZC"           # 证从 前缀

# ─── 应用初始化 ───────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Flask secret key for session
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
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash   TEXT NOT NULL UNIQUE,        -- SHA256(代码)
            code_prefix TEXT NOT NULL,               -- 前4位，方便管理员识别
            is_used     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            used_by     TEXT,
            used_at     TEXT,
            expires_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS members (
            username    TEXT PRIMARY KEY,
            is_member   INTEGER NOT NULL DEFAULT 0,
            activated_at TEXT,
            expires_at  TEXT,
            code_used   TEXT,                         -- 使用的激活码前4位(非完整)
            last_active TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_codes_hash ON activation_codes(code_hash);
        CREATE INDEX IF NOT EXISTS idx_codes_used ON activation_codes(is_used);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ─── 工具函数 ─────────────────────────────────────────────
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def generate_code() -> str:
    """生成格式: ZC-XXXX-XXXX-XXXX"""
    def _block(n=4):
        return ''.join(secrets.choice(CHAR_POOL) for _ in range(n))
    return f"{CODE_PREFIX}-{_block()}-{_block()}-{_block()}"


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # 方式1: Bearer Token (API)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            stored = load_admin_token()
            if token == stored:
                return f(*args, **kwargs)
            return jsonify({"error": "unauthorized"}), 401

        # 方式2: Session (Web)
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)

        return redirect("/admin/login")
    return decorated


def load_admin_token():
    if ADMIN_TOKEN_FILE.exists():
        return ADMIN_TOKEN_FILE.read_text().strip()
    # 首次启动自动生成
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
    return sha256(pw)  # fallback


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
        "version": "1.0.0",
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
input{width:100%;padding:10px 14px;border:1px solid #d4c9b8;border-radius:8px;font-size:14px;margin-bottom:12px;outline:none}
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
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>管理面板 · 证从刷题</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
body{background:#f5efe6;padding:16px;color:#3d3229}
.container{max-width:800px;margin:0 auto}
h1{color:#1e5b8a;font-size:20px;margin-bottom:16px}
h2{color:#1e5b8a;font-size:16px;margin:16px 0 8px}
.card{background:#faf6f0;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.stat-row{display:flex;gap:12px;flex-wrap:wrap}
.stat{flex:1;min-width:100px;background:#faf6f0;border-radius:10px;padding:14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.stat .num{font-size:24px;font-weight:700}
.stat .num.blue{color:#1e5b8a}
.stat .num.green{color:#3d7246}
.stat .num.red{color:#c23b22}
.stat .lbl{font-size:12px;color:#8b7e6e;margin-top:4px}
.btn{display:inline-block;padding:8px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.btn-primary{background:#1e5b8a;color:white}
.btn-primary:hover{background:#164a6e}
.btn-success{background:#3d7246;color:white}
.btn-danger{background:#c23b22;color:white}
.btn-sm{padding:4px 12px;font-size:12px}
.mt-8{margin-top:8px}
.mb-8{margin-bottom:8px}
.flex{display:flex;align-items:center;gap:8px}
.flex-wrap{flex-wrap:wrap}
.justify-between{justify-content:space-between}
.text-dim{color:#8b7e6e;font-size:13px}
.text-sm{font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #e8dfd0}
th{color:#8b7e6e;font-weight:600;font-size:11px;text-transform:uppercase}
.tag{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.tag-used{background:#e8f5e9;color:#2e7d32}
.tag-active{background:#fff3e0;color:#e65100}
.tag-expired{background:#fbe9e7;color:#c62828}
#new-code-area{margin-top:12px;padding:16px;background:#e8f5e9;border-radius:8px;display:none}
#new-code-area .code{font-size:24px;font-weight:700;letter-spacing:2px;color:#1e5b8a;text-align:center;padding:12px;font-family:'Courier New',monospace;user-select:all}
.copy-btn{background:white;border:1px solid #d4c9b8;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px}
.copy-btn:hover{background:#f5efe6}
.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#3d7246;color:white;padding:10px 24px;border-radius:8px;font-size:14px;z-index:999;opacity:0;transition:opacity 0.3s;pointer-events:none}
.toast.show{opacity:1}
</style>
</head>
<body>
<div class="container">
<div class="flex justify-between mb-8">
<h1>📋 证从刷题 · 管理面板</h1>
<a href="/admin/logout" style="color:#8b7e6e;font-size:13px;text-decoration:none">退出</a>
</div>

<div class="stat-row">
<div class="stat"><div class="num blue">{{ stats.total }}</div><div class="lbl">总生成码</div></div>
<div class="stat"><div class="num green">{{ stats.available }}</div><div class="lbl">可用码</div></div>
<div class="stat"><div class="num red">{{ stats.used }}</div><div class="lbl">已使用</div></div>
<div class="stat"><div class="num blue">{{ stats.members }}</div><div class="lbl">激活用户</div></div>
</div>

<div class="card">
<h2>🎫 生成新激活码</h2>
<div class="flex flex-wrap">
<button class="btn btn-primary" onclick="generateCode(1)">生成 1 个</button>
<button class="btn btn-primary" onclick="generateCode(5)" style="margin-left:8px">生成 5 个</button>
<button class="btn btn-primary" onclick="generateCode(10)" style="margin-left:8px">生成 10 个</button>
</div>
<div id="new-code-area"></div>
</div>

<div class="card">
<div class="flex justify-between">
<h2>📜 激活码列表</h2>
<button class="btn btn-sm" onclick="window.location.reload()">🔄 刷新</button>
</div>
<div style="overflow-x:auto">
<table>
<thead><tr><th>代码 (前4位)</th><th>状态</th><th>生成时间</th><th>使用者</th></tr></thead>
<tbody>
{% for code in codes %}
<tr>
<td><code style="font-family:monospace;background:#f5efe6;padding:2px 6px;border-radius:4px">{{ code.code_prefix }}</code></td>
<td>
{% if code.is_used %}
<span class="tag tag-used">已使用</span>
{% else %}
<span class="tag tag-active">可用</span>
{% endif %}
</td>
<td>{{ code.created_at[:16] }}</td>
<td>{{ code.used_by or '-' }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% if codes|length == 0 %}
<div class="text-dim" style="text-align:center;padding:16px">暂无激活码数据</div>
{% endif %}
</div>
</div>

</div>

<script>
async function generateCode(n) {
  const area = document.getElementById('new-code-area');
  area.style.display = 'block';
  area.innerHTML = '<div class="text-dim">⏳ 生成中...</div>';
  try {
    const r = await fetch('/api/admin/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer {{ token }}'},
      body: JSON.stringify({count: n})
    });
    const data = await r.json();
    if (data.codes) {
      let html = '<div class="text-sm text-dim" style="margin-bottom:8px">✅ 生成成功！请复制激活码发给买家：</div>';
      data.codes.forEach((c, i) => {
        html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <div class="code" style="flex:1">${c}</div>
          <button class="copy-btn" onclick="copyCode('${c}', this)">📋 复制</button>
        </div>`;
      });
      html += '<div class="text-sm text-dim" style="margin-top:8px">提示：代码已存入数据库，买家可直接使用</div>';
      area.innerHTML = html;
    } else {
      area.innerHTML = `<div class="text-sm" style="color:#c23b22">❌ ${data.error || '生成失败'}</div>`;
    }
  } catch(e) {
    area.innerHTML = `<div class="text-sm" style="color:#c23b22">❌ 请求失败: ${e.message}</div>`;
  }
}

async function copyCode(code, btn) {
  try {
    await navigator.clipboard.writeText(code);
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = '📋 复制', 2000);
  } catch {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = code;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = '📋 复制', 2000);
  }
}

// Auto-reload every 60s
setTimeout(() => window.location.reload(), 60000);
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

    # 统计
    stats = {}
    stats["total"] = conn.execute("SELECT COUNT(*) FROM activation_codes").fetchone()[0]
    stats["used"] = conn.execute("SELECT COUNT(*) FROM activation_codes WHERE is_used=1").fetchone()[0]
    stats["available"] = stats["total"] - stats["used"]
    stats["members"] = conn.execute("SELECT COUNT(*) FROM members WHERE is_member=1").fetchone()[0]

    # 所有码
    rows = conn.execute(
        "SELECT code_prefix, is_used, created_at, used_by FROM activation_codes ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()

    codes = [dict(r) for r in rows]

    return render_template_string(
        ADMIN_DASHBOARD_HTML,
        stats=stats,
        codes=codes,
        token=load_admin_token()
    )


# ─── 管理 API ─────────────────────────────────────────────
@app.route("/api/admin/generate", methods=["POST"])
@admin_required
def api_generate():
    data = request.get_json(silent=True) or {}
    count = min(int(data.get("count", 1)), 50)
    if count < 1:
        return jsonify({"error": "count must be >= 1"}), 400

    conn = get_db()
    new_codes = []
    for _ in range(count):
        code = generate_code()
        code_hash = sha256(code)
        prefix = code[:7]  # "ZC-XXX" 前7位用于展示
        expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO activation_codes (code_hash, code_prefix, expires_at) VALUES (?, ?, ?)",
            (code_hash, prefix, expires)
        )
        new_codes.append(code)
    conn.commit()
    conn.close()

    return jsonify({"codes": new_codes, "count": len(new_codes)})


@app.route("/api/admin/codes", methods=["GET"])
@admin_required
def api_list_codes():
    conn = get_db()
    rows = conn.execute(
        "SELECT code_prefix, is_used, created_at, used_by, used_at FROM activation_codes ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    conn.close()
    return jsonify({"codes": [dict(r) for r in rows]})


# ─── 用户 API ─────────────────────────────────────────────
@app.route("/api/user/status", methods=["GET"])
def api_user_status():
    """查询用户会员状态"""
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
    """
    激活会员
    Body: {"code": "ZC-XXXX-XXXX-XXXX", "username": "xxx"}
    """
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip().upper()
    username = data.get("username", "").strip()

    if not code or not username:
        return jsonify({"success": False, "error": "code and username required"}), 400

    code_hash = sha256(code)

    conn = get_db()

    # 查码
    row = conn.execute("SELECT * FROM activation_codes WHERE code_hash=?", (code_hash,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "激活码无效"}), 404

    if row["is_used"]:
        conn.close()
        return jsonify({"success": False, "error": "激活码已被使用"}), 409

    # 查用户
    user = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    if user and user["is_member"]:
        # 已经是会员，看是否过期
        expires = user["expires_at"]
        if expires and expires > datetime.now(timezone.utc).isoformat():
            conn.close()
            return jsonify({"success": False, "error": "该账号已是会员"}), 409

    # 开始激活（事务）
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
    """
    接收闲鱼/三方平台的订单通知，自动生成激活码并返回。
    期望格式：
    {
      "platform": "xianyu",        // 平台标识
      "order_id": "1234567890",    // 订单号
      "buyer": "buyer_nickname",   // 买家昵称(optional)
      "secret": "shared_secret"    // 鉴权密钥
    }
    返回：
    {
      "success": true,
      "activation_code": "ZC-XXXX-XXXX-XXXX"
    }
    """
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-in-production")

    data = request.get_json(silent=True) or {}
    secret = data.get("secret", "")
    if secret != WEBHOOK_SECRET:
        return jsonify({"error": "invalid secret"}), 401

    # 生成一个激活码
    code = generate_code()
    code_hash = sha256(code)
    prefix = code[:7]
    expires = (datetime.now(timezone.utc) + timedelta(days=CODE_EXPIRY_DAYS)).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO activation_codes (code_hash, code_prefix, expires_at) VALUES (?, ?, ?)",
        (code_hash, prefix, expires)
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
    print(f"📚 证从刷题 · 会员系统")
    print(f"   DB:     {DB_PATH}")
    print(f"   Token:  {load_admin_token()[:16]}...")
    print(f"   管理面板: http://localhost:{port}/admin")
    print(f"   激活API:  POST /api/activate")
    print(f"   状态API:  GET  /api/user/status?username=xxx")
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
