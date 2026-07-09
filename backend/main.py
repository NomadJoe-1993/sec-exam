#!/usr/bin/env python3
"""证从刷题 · 后端 API — FastAPI + SQLite + JWT 认证"""
import os, sqlite3, json, hashlib, secrets, string
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ── Config ──
DB_PATH = Path(__file__).parent / "data.db"
JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-to-a-random-secret-in-production")
JWT_ALGO = "HS256"
JWT_EXPIRE_DAYS = 30
ADMIN_KEY = os.environ.get("ADMIN_KEY", "admin888")
security = HTTPBearer(auto_error=False)


# ── Password helpers (SHA256 + salt, no bcrypt dependency) ──
def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


# ── DB Init ──
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_member INTEGER DEFAULT 0,
            member_expires TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS license_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            duration_days INTEGER NOT NULL DEFAULT 365,
            used_by INTEGER,
            used_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (used_by) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_license_code ON license_codes(code);
    """)
    conn.commit()
    conn.close()


# ── Models ──
class RegisterReq(BaseModel):
    username: str
    password: str

class LoginReq(BaseModel):
    username: str
    password: str

class ActivateReq(BaseModel):
    code: str

class GenCodeReq(BaseModel):
    admin_key: str
    count: int = 1
    duration_days: int = 365


# ── Auth ──
def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except Exception:
        raise HTTPException(status_code=401, detail="登录无效")


# ── App ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="证从刷题 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ──
@app.post("/api/register")
def register(req: RegisterReq):
    if len(req.username) < 2 or len(req.username) > 20:
        raise HTTPException(400, "用户名2-20个字符")
    if len(req.password) < 4:
        raise HTTPException(400, "密码至少4位")
    conn = get_db()
    try:
        pw_hash = hash_password(req.password)
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     (req.username, pw_hash))
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE username = ?", (req.username,)).fetchone()
        token = create_token(user["id"])
        return {"token": token, "user_id": user["id"], "username": req.username, "is_member": False}
    except sqlite3.IntegrityError:
        raise HTTPException(400, "用户名已被注册")
    finally:
        conn.close()


@app.post("/api/login")
def login(req: LoginReq):
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (req.username,)).fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "用户名或密码错误")
        is_member, expires = _check_member(user)
        token = create_token(user["id"])
        return {"token": token, "user_id": user["id"], "username": user["username"], "is_member": is_member}
    finally:
        conn.close()


@app.post("/api/activate")
def activate(req: ActivateReq, user_id: int = Depends(get_current_user)):
    conn = get_db()
    try:
        code = conn.execute("SELECT * FROM license_codes WHERE code = ?", (req.code,)).fetchone()
        if not code:
            raise HTTPException(404, "会员码不存在")
        if code["used_by"] is not None:
            raise HTTPException(400, "会员码已被使用")

        expires = (datetime.now() + timedelta(days=code["duration_days"])).isoformat()
        conn.execute("UPDATE license_codes SET used_by = ?, used_at = datetime('now') WHERE id = ?",
                     (user_id, code["id"]))
        conn.execute("UPDATE users SET is_member = 1, member_expires = ? WHERE id = ?",
                     (expires, user_id))
        conn.commit()
        return {"success": True, "member_expires": expires}
    finally:
        conn.close()


@app.get("/api/me")
def get_me(user_id: int = Depends(get_current_user)):
    conn = get_db()
    try:
        user = conn.execute("SELECT id, username, is_member, member_expires FROM users WHERE id = ?",
                          (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "用户不存在")
        is_member, expires = _check_member(user)
        return {"user_id": user["id"], "username": user["username"], "is_member": is_member,
                "member_expires": expires}
    finally:
        conn.close()


@app.get("/api/access")
def check_access(user_id: int = Depends(get_current_user)):
    conn = get_db()
    try:
        user = conn.execute("SELECT is_member, member_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "用户不存在")
        is_member, expires = _check_member(user)
        return {"is_member": is_member, "member_expires": expires}
    finally:
        conn.close()


@app.post("/api/admin/gen-codes")
def gen_codes(req: GenCodeReq):
    if req.admin_key != ADMIN_KEY:
        raise HTTPException(403, "管理员密钥错误")
    conn = get_db()
    codes = []
    try:
        for _ in range(req.count):
            code = "SEC-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            conn.execute("INSERT INTO license_codes (code, duration_days) VALUES (?, ?)",
                        (code, req.duration_days))
            codes.append(code)
        conn.commit()
        return {"codes": codes}
    finally:
        conn.close()


@app.get("/api/admin/codes")
def list_codes(admin_key: str):
    if admin_key != ADMIN_KEY:
        raise HTTPException(403, "管理员密钥错误")
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT c.code, c.duration_days, c.used_by, c.used_at, c.created_at, u.username
            FROM license_codes c LEFT JOIN users u ON c.used_by = u.id
            ORDER BY c.id DESC LIMIT 50
        """).fetchall()
        return {"codes": [dict(r) for r in rows]}
    finally:
        conn.close()


def _check_member(user):
    """Check if a user is currently an active member."""
    is_member = bool(user["is_member"])
    expires = user["member_expires"]
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.now():
                is_member = False
        except:
            is_member = False
    return is_member, expires


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
