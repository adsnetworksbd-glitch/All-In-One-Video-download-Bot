import os, subprocess

files = {
    "requirements.txt": """python-telegram-bot==21.10
httpx==0.28.1
firebase-admin==6.6.0
yt-dlp>=2025.02.19
pydantic==2.10.6
pydantic-settings==2.8.1
python-dotenv==1.0.1
aiohttp==3.11.12
yarl==1.18.5
""",

    ".env.example": """TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567
BOT_USERNAME=AllInOneDownloaderBot
ADMIN_TELEGRAM_IDS=123456789
FIREBASE_DATABASE_URL=https://your-project-id-default-rtdb.firebaseio.com/
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
ENVIRONMENT=production
LOG_LEVEL=INFO
DEFAULT_REQUEST_TIMEOUT=15
MAX_CONCURRENT_JOBS_PER_USER=2
USER_RATE_LIMIT_PER_MINUTE=6
CACHE_TTL_SECONDS=60
""",

    ".gitignore": """__pycache__/
*.py[cod]
.env
firebase-credentials.json
venv/
*.log
""",

    "config.py": '''import os, json
from typing import List, Optional, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TELEGRAM_BOT_TOKEN: str = Field(..., description="Bot Token")
    BOT_USERNAME: str = Field("AllInOneDownloaderBot")
    ADMIN_TELEGRAM_IDS: List[int] = Field(default_factory=list)
    FIREBASE_DATABASE_URL: str = Field(...)
    FIREBASE_CREDENTIALS_PATH: Optional[str] = Field(None)
    FIREBASE_CREDENTIALS_RAW_JSON: Optional[str] = Field(None)
    ENVIRONMENT: str = Field("production")
    LOG_LEVEL: str = Field("INFO")
    DEFAULT_REQUEST_TIMEOUT: int = Field(15, ge=5, le=60)
    MAX_CONCURRENT_JOBS_PER_USER: int = Field(2, ge=1, le=5)
    USER_RATE_LIMIT_PER_MINUTE: int = Field(6, ge=1, le=60)
    CACHE_TTL_SECONDS: int = Field(60, ge=5, le=600)

    @field_validator("TELEGRAM_BOT_TOKEN")
    @classmethod
    def validate_token(cls, v: str) -> str:
        v = v.strip()
        if ":" not in v: raise ValueError("Invalid Telegram bot token format.")
        return v

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_admins(cls, v: Any) -> List[int]:
        if isinstance(v, list): return [int(x) for x in v]
        if isinstance(v, str): return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int): return [v]
        return []

    def get_firebase_credentials(self) -> dict:
        if self.FIREBASE_CREDENTIALS_RAW_JSON:
            return json.loads(self.FIREBASE_CREDENTIALS_RAW_JSON)
        if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            with open(self.FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        raise ValueError("Firebase credentials missing.")

settings = None
def get_settings() -> AppSettings:
    global settings
    if settings is None: settings = AppSettings()
    return settings
''',

    "logger.py": '''import logging, re, sys

class SensitiveDataFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.patterns = [
            re.compile(r"([0-9]{8,10}:[a-zA-Z0-9_-]{35})"),
            re.compile(r'(Bearer\\s+)([a-zA-Z0-9_\\-\\.]{20,})')
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for p in self.patterns: record.msg = p.sub("[REDACTED_SECRET]", record.msg)
        return True

def setup_logger(name: str = "downloader_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s - %(message)s"))
        h.addFilter(SensitiveDataFilter())
        logger.addHandler(h)
    return logger

logger = setup_logger()
''',

    "database/__init__.py": "",
    "database/firebase.py": '''import firebase_admin
from firebase_admin import credentials, db
from config import get_settings
from logger import logger

class FirebaseManager:
    _instance, _initialized = None, False

    def __new__(cls):
        if cls._instance is None: cls._instance = super(FirebaseManager, cls).__new__(cls)
        return cls._instance

    def initialize(self):
        if self._initialized: return
        settings = get_settings()
        cred = credentials.Certificate(settings.get_firebase_credentials())
        firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_DATABASE_URL})
        self._initialized = True
        logger.info("Connected to Firebase Realtime Database.")

    def get_ref(self, path: str):
        if not self._initialized: self.initialize()
        return db.reference(path)

    def safe_get(self, path: str):
        try: return self.get_ref(path).get()
        except Exception as e: raise RuntimeError(f"Read error: {e}")

    def safe_set(self, path: str, val):
        try: self.get_ref(path).set(val)
        except Exception as e: raise RuntimeError(f"Write error: {e}")

    def safe_update(self, path: str, val: dict):
        try: self.get_ref(path).update(val)
        except Exception as e: raise RuntimeError(f"Update error: {e}")

    def run_transaction(self, path: str, fn):
        try: return self.get_ref(path).transaction(fn)
        except Exception as e: raise RuntimeError(f"Transaction error: {e}")

firebase_manager = FirebaseManager()
''',

    "database/user_repo.py": '''import time
from database.firebase import firebase_manager

class UserRepository:
    def __init__(self): self.fb = firebase_manager
    def get_user(self, tg_id: int): return self.fb.safe_get(f"users/{tg_id}")
    def is_user_banned(self, tg_id: int) -> bool:
        u = self.get_user(tg_id)
        return bool(u and u.get("is_banned"))

    def onboard_user_if_new(self, tg_id: int, first_name: str, username=None, last_name=None, ref_by=None, welcome=50):
        existing = self.get_user(tg_id)
        if existing: return existing, False
        now = int(time.time() * 1000)
        user = {
            "telegram_id": tg_id, "first_name": first_name, "last_name": last_name,
            "username": username, "credit_balance": int(welcome), "is_banned": False,
            "referred_by": ref_by if (ref_by and ref_by != tg_id) else None,
            "created_at": now, "last_active_at": now
        }
        self.fb.safe_set(f"users/{tg_id}", user)
        return user, True
''',

    "database/credit_repo.py": '''import time, uuid
from database.firebase import firebase_manager

class CreditRepository:
    def __init__(self): self.fb = firebase_manager

    def record_tx(self, tg_id, amt, bal, t_type, r_id, reason):
        tx_id = str(uuid.uuid4())
        self.fb.safe_set(f"credit_transactions/{tx_id}", {
            "transaction_id": tx_id, "telegram_user_id": tg_id, "amount": amt,
            "balance_after": bal, "type": t_type, "reference_id": r_id, "reason": reason,
            "created_at": int(time.time() * 1000)
        })

    def reserve_or_deduct_credits(self, tg_id: int, amt: int, r_id: str, reason: str):
        path = f"users/{tg_id}/credit_balance"
        err = {}
        def txn(curr):
            if curr is None or curr < amt:
                err["err"] = curr or 0
                return None
            return curr - amt
        new_bal = self.fb.run_transaction(path, txn)
        if "err" in err: raise ValueError(f"Insufficient balance. Required: {amt}, Available: {err['err']}")
        self.record_tx(tg_id, -amt, new_bal, "DOWNLOAD_DEBIT", r_id, reason)
        return new_bal

    def refund_credits(self, tg_id: int, amt: int, r_id: str, reason: str):
        if amt <= 0: return 0
        new_bal = self.fb.run_transaction(f"users/{tg_id}/credit_balance", lambda c: (c or 0) + amt)
        self.record_tx(tg_id, amt, new_bal, "DOWNLOAD_REFUND", r_id, reason)
        return new_bal

    def add_reward_credits(self, tg_id: int, amt: int, r_type: str, r_id: str, reason: str):
        if amt <= 0: return 0
        new_bal = self.fb.run_transaction(f"users/{tg_id}/credit_balance", lambda c: (c or 0) + amt)
        self.record_tx(tg_id, amt, new_bal, r_type, r_id, reason)
        return new_bal
''',

    "database/category_repo.py": '''import time
from database.firebase import firebase_manager

DEFAULT_CATS = [
    {"id": "cat_yt", "name": "YouTube", "slug": "youtube", "icon": "▶️", "is_active": True, "display_order": 1},
    {"id": "cat_fb", "name": "Facebook", "slug": "facebook", "icon": "📘", "is_active": True, "display_order": 2},
    {"id": "cat_ig", "name": "Instagram", "slug": "instagram", "icon": "📸", "is_active": True, "display_order": 3},
    {"id": "cat_tt", "name": "TikTok", "slug": "tiktok", "icon": "🎵", "is_active": True, "display_order": 4},
    {"id": "cat_pin", "name": "Pinterest", "slug": "pinterest", "icon": "📌", "is_active": True, "display_order": 5},
    {"id": "cat_x", "name": "X / Twitter", "slug": "twitter", "icon": "🐦", "is_active": True, "display_order": 6},
]

class CategoryRepository:
    def __init__(self):
        self.fb = firebase_manager
        self._cache = None
        self._last_time = 0

    def get_active_categories(self, force=False):
        now = time.time()
        if not force and self._cache and (now - self._last_time < 60):
            return self._cache
        data = self.fb.safe_get("categories")
        cats = []
        if data and isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and v.get("is_active", True):
                    v["id"] = k; cats.append(v)
        else:
            for c in DEFAULT_CATS: self.fb.safe_set(f"categories/{c['id']}", c)
            cats = [c for c in DEFAULT_CATS if c["is_active"]]
        cats.sort(key=lambda x: x.get("display_order", 999))
        self._cache = cats
        self._last_time = now
        return cats

    def search_categories(self, q: str):
        q = q.lower().strip()
        return [c for c in self.get_active_categories() if q in c.get("name","").lower() or q in c.get("slug","").lower()]

category_repo = CategoryRepository()
''',

    "database/job_repo.py": '''import time, uuid
from database.firebase import firebase_manager

class JobRepository:
    def __init__(self): self.fb = firebase_manager

    def create_job(self, user_id: int, category_slug: str, original_url: str, sanitized_url: str):
        job_id = str(uuid.uuid4())
        self.fb.safe_set(f"download_jobs/{job_id}", {
            "job_id": job_id, "telegram_user_id": user_id, "category_slug": category_slug,
            "original_url": original_url, "sanitized_url": sanitized_url, "status": "CREATED",
            "created_at": int(time.time() * 1000)
        })
        return job_id

    def update_job_status(self, job_id: str, status: str, **kwargs):
        kwargs["status"] = status
        kwargs["updated_at"] = int(time.time() * 1000)
        self.fb.safe_update(f"download_jobs/{job_id}", kwargs)

    def record_history(self, user_id: int, job_id: str, platform: str, title: str, quality: str, cost: int):
        h_id = str(uuid.uuid4())
        self.fb.safe_set(f"download_history/{user_id}/{h_id}", {
            "job_id": job_id, "platform": platform, "title": title[:100],
            "selected_quality": quality, "credits_spent": cost, "created_at": int(time.time() * 1000)
        })

    def get_user_history(self, user_id: int, limit: int = 5):
        records = self.fb.safe_get(f"download_history/{user_id}")
        if not records or not isinstance(records, dict): return []
        h = list(records.values())
        h.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return h[:limit]

job_repo = JobRepository()
''',

    "services/__init__.py": "",
    "services/url_validator.py": '''import socket, ipaddress
from urllib.parse import urlparse

BLOCKED = [
    ipaddress.ip_network("0.0.0.0/8"), ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"), ipaddress.ip_network("fe80::/10")
]

PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "facebook": ["facebook.com", "fb.watch"],
    "instagram": ["instagram.com"],
    "tiktok": ["tiktok.com"],
    "pinterest": ["pinterest.com", "pin.it"],
    "twitter": ["twitter.com", "x.com"]
}

def validate_and_sanitize_url(url: str):
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ["http", "https"]: raise ValueError("Invalid scheme.")
    hostname = parsed.hostname
    if not hostname: raise ValueError("Invalid hostname.")
    addr_info = socket.getaddrinfo(hostname, None)
    for addr in addr_info:
        ip = ipaddress.ip_address(addr[4][0])
        for b in BLOCKED:
            if ip in b: raise ValueError(f"Restricted host: {ip}")
    plat = "custom"
    for p, domains in PLATFORMS.items():
        if any(hostname == d or hostname.endswith("." + d) for d in domains):
            plat = p; break
    return url.strip(), plat
''',

    "services/provider_base.py": '''from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class VideoFormatOption:
    format_id: str
    label: str
    resolution: Optional[str]
    file_size_bytes: Optional[int]
    extension: str
    download_url: Optional[str] = None

@dataclass
class MediaMetadata:
    platform: str
    video_id: str
    title: str
    thumbnail_url: Optional[str]
    duration_seconds: Optional[int]
    available_formats: List[VideoFormatOption]
    source_url: str

class BaseProviderAdapter(ABC):
    @abstractmethod
    async def extract_info(self, url: str) -> MediaMetadata: pass
    @abstractmethod
    async def create_download_url(self, url: str, format_id: str) -> str: pass
''',

    "providers/__init__.py": "",
    "providers/builtin/__init__.py": "",
    "providers/builtin/ytdlp_adapter.py": '''import asyncio, yt_dlp
from services.provider_base import BaseProviderAdapter, MediaMetadata, VideoFormatOption

class YtDlpAdapter(BaseProviderAdapter):
    def __init__(self):
        self.opts = {"quiet": True, "no_warnings": True, "skip_download": True, "simulate": True, "socket_timeout": 15}

    def _sync(self, url):
        with yt_dlp.YoutubeDL(self.opts) as ydl: return ydl.extract_info(url, download=False)

    async def extract_info(self, url: str) -> MediaMetadata:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._sync, url)
        formats = []
        for f in info.get("formats", []):
            u = f.get("url")
            if not u: continue
            h = f.get("height")
            if h:
                formats.append(VideoFormatOption(
                    format_id=f"{h}p", label=f"{h}p HD" if h >= 720 else f"{h}p",
                    resolution=f"{f.get('width', 0)}x{h}", file_size_bytes=f.get("filesize"),
                    extension=f.get("ext", "mp4"), download_url=u
                ))
        unique = {fmt.format_id: fmt for fmt in formats}
        return MediaMetadata(
            platform=info.get("extractor", "generic"), video_id=info.get("id", "vid"),
            title=info.get("title", "Video"), thumbnail_url=info.get("thumbnail"),
            duration_seconds=info.get("duration"), available_formats=list(unique.values()), source_url=url
        )

    async def create_download_url(self, url: str, format_id: str) -> str:
        meta = await self.extract_info(url)
        for f in meta.available_formats:
            if f.format_id == format_id and f.download_url: return f.download_url
        return meta.available_formats[0].download_url
''',

    "services/api_registry.py": '''from providers.builtin.ytdlp_adapter import YtDlpAdapter
class ProviderRegistry:
    def __init__(self): self.builtin = YtDlpAdapter()
    def get_provider_for_platform(self, plat: str): return self.builtin
provider_registry = ProviderRegistry()
''',

    "services/download_service.py": '''from services.url_validator import validate_and_sanitize_url
from services.api_registry import provider_registry
from database.firebase import firebase_manager
from database.credit_repo import CreditRepository
from database.job_repo import job_repo

credit_repo = CreditRepository()

def get_credit_price(fmt: str) -> int:
    try:
        p = firebase_manager.safe_get("bot_settings/credits/pricing_by_quality")
        if p and isinstance(p, dict):
            for k, v in p.items():
                if k in fmt: return int(v)
    except Exception: pass
    return 10

class DownloadService:
    @staticmethod
    async def prepare_video_options(url: str, user_id: int):
        s_url, plat = validate_and_sanitize_url(url)
        job_id = job_repo.create_job(user_id, plat, url, s_url)
        provider = provider_registry.get_provider_for_platform(plat)
        meta = await provider.extract_info(s_url)
        return job_id, meta

    @staticmethod
    async def process_and_deliver_download(job_id, user_id, format_id, video_url, plat, title):
        cost = get_credit_price(format_id)
        credit_repo.reserve_or_deduct_credits(user_id, cost, job_id, f"Download {format_id}")
        provider = provider_registry.get_provider_for_platform(plat)
        try:
            direct_url = await provider.create_download_url(video_url, format_id)
            job_repo.record_history(user_id, job_id, plat, title, format_id, cost)
            job_repo.update_job_status(job_id, "COMPLETED")
            return direct_url
        except Exception as e:
            credit_repo.refund_credits(user_id, cost, job_id, "Refund on link error")
            job_repo.update_job_status(job_id, "REFUNDED")
            raise e

download_service = DownloadService()
''',

    "services/job_queue.py": '''from database.firebase import firebase_manager
from database.credit_repo import CreditRepository
from database.job_repo import job_repo

class JobRecoveryManager:
    @staticmethod
    def reconcile_stranded_jobs():
        cr = CreditRepository()
        jobs = firebase_manager.safe_get("download_jobs")
        if not jobs or not isinstance(jobs, dict): return
        for j_id, j in jobs.items():
            if j.get("status") in ["CREDIT_RESERVED", "PROCESSING"]:
                u_id = j.get("telegram_user_id")
                c = j.get("credit_cost", 0)
                if c > 0 and u_id: cr.refund_credits(u_id, c, j_id, "Server restarted refund")
                job_repo.update_job_status(j_id, "REFUNDED")

job_recovery_manager = JobRecoveryManager()
''',

    "handlers/__init__.py": "",
    "handlers/start.py": '''from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from database.user_repo import UserRepository
from database.credit_repo import CreditRepository

user_repo = UserRepository()
credit_repo = CreditRepository()

MAIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("📥 Download Categories"), KeyboardButton("🔍 Search")],
    [KeyboardButton("📜 My History"), KeyboardButton("⚙️ Settings")],
    [KeyboardButton("📊 My Statistics"), KeyboardButton("💬 Support")]
], resize_keyboard=True, is_persistent=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_by = None
    if context.args and context.args[0].startswith("ref_"):
        try: ref_by = int(context.args[0].replace("ref_", ""))
        except: pass

    u, is_new = user_repo.onboard_user_if_new(user.id, user.first_name, user.username, user.last_name, ref_by)
    if is_new and ref_by:
        credit_repo.add_reward_credits(ref_by, 20, "REFERRAL_REWARD", f"ref_{user.id}", "Referral bonus")
        credit_repo.add_reward_credits(user.id, 10, "REFERRAL_REWARD", f"ref_by_{ref_by}", "Joining bonus")

    bal = u.get('credit_balance', 50)
    await update.message.reply_text(
        f"👋 **Welcome, {user.first_name}!**\\n\\n🎬 **All-in-One Video Downloader Bot**\\n💰 Balance: `{bal}` Credits\\n\\nSend any video link to begin!",
        parse_mode="Markdown", reply_markup=MAIN_MENU
    )
''',

    "handlers/categories.py": '''from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database.category_repo import category_repo

def build_kb(page=0):
    cats = category_repo.get_active_categories()
    items = cats[page*6 : (page+1)*6]
    kb, row = [], []
    for c in items:
        row.append(InlineKeyboardButton(f"{c.get('icon','📁')} {c['name']}", callback_data=f"cat_select:{c['slug']}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cat_page:{page-1}"))
    if (page+1)*6 < len(cats): nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"cat_page:{page+1}"))
    if nav: kb.append(nav)
    return InlineKeyboardMarkup(kb)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 **Select a Platform Category:**", parse_mode="Markdown", reply_markup=build_kb(0))

async def category_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("cat_page:"):
        await q.edit_message_reply_markup(reply_markup=build_kb(int(q.data.split(":")[1])))
    elif q.data.startswith("cat_select:"):
        await q.message.reply_text(f"🔗 **{q.data.split(':')[1].title()} Selected!** Send public video URL:")
''',

    "handlers/downloads.py": '''from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.download_service import download_service, get_credit_price
from database.user_repo import UserRepository

user_repo = UserRepository()
CACHE = {}

async def handle_video_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    if user_repo.is_user_banned(user.id):
        await update.message.reply_text("⛔ Account suspended.")
        return

    msg = await update.message.reply_text("🔎 Analyzing video...")
    try:
        j_id, meta = await download_service.prepare_video_options(text, user.id)
        CACHE[j_id] = {"meta": meta, "url": text, "plat": meta.platform}
        kb = [[InlineKeyboardButton(f"🎬 {f.label} ({get_credit_price(f.format_id)} Cr)", callback_data=f"dl_select:{j_id}:{f.format_id}")] for f in meta.available_formats[:6]]
        await msg.edit_text(f"📹 **Title:** *{meta.title}*\\nSelect quality:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def download_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, j_id, fmt = q.data.split(":")
    cached = CACHE.get(j_id)
    if not cached:
        await q.edit_message_text("Expired session. Please resend the link.")
        return

    await q.edit_message_text("⏳ Generating direct download link...")
    try:
        direct = await download_service.process_and_deliver_download(j_id, q.from_user.id, fmt, cached["url"], cached["plat"], cached["meta"].title)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ Download Video to Phone", url=direct)]])
        await q.edit_message_text("✅ Link Ready! Tap below to download:", reply_markup=kb)
    except Exception as e:
        await q.edit_message_text(f"❌ Error: {e}")
''',

    "handlers/history.py": '''from telegram import Update
from telegram.ext import ContextTypes
from database.job_repo import job_repo

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = job_repo.get_user_history(update.effective_user.id)
    if not records:
        await update.message.reply_text("📜 No downloads recorded yet.")
        return
    lines = ["📜 **Your Downloads:**\\n"]
    for i, r in enumerate(records, 1):
        lines.append(f"{i}. {r.get('title')} ({r.get('selected_quality')}) - {r.get('credits_spent')} Cr")
    await update.message.reply_text("\\n".join(lines))
''',

    "handlers/referrals.py": '''from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import get_settings

async def show_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = get_settings().BOT_USERNAME
    link = f"https://t.me/{b}?start=ref_{update.effective_user.id}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={link}")]])
    await update.message.reply_text(f"🤝 **Invite Friends & Earn Credits!**\\n\\nLink:\\n`{link}`", parse_mode="Markdown", reply_markup=markup)
''',

    "handlers/settings.py": '''from telegram import Update
from telegram.ext import ContextTypes
from database.user_repo import UserRepository

user_repo = UserRepository()
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_repo.get_user(update.effective_user.id) or {}
    await update.message.reply_text(f"⚙️ **Settings**\\nID: `{update.effective_user.id}`\\nBalance: `{u.get('credit_balance', 0)}` Credits", parse_mode="Markdown")
''',

    "handlers/support.py": '''from telegram import Update
from telegram.ext import ContextTypes
from database.user_repo import UserRepository
from database.job_repo import job_repo

user_repo = UserRepository()
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_repo.get_user(update.effective_user.id) or {}
    h = job_repo.get_user_history(update.effective_user.id, limit=50)
    spent = sum(x.get("credits_spent", 0) for x in h)
    await update.message.reply_text(f"📊 **Statistics**\\nDownloads: `{len(h)}`\\nSpent: `{spent}` Credits\\nBalance: `{u.get('credit_balance', 0)}` Credits", parse_mode="Markdown")

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 **Support:** Contact @admin for assistance.")
''',

    "handlers/search.py": '''from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database.category_repo import category_repo

async def prompt_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await update.message.reply_text("🔍 Type platform name to search (e.g. YouTube, TikTok):")

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_search"): return
    context.user_data["awaiting_search"] = False
    res = category_repo.search_categories(update.message.text.strip())
    if not res:
        await update.message.reply_text("❌ No platform found.")
        return
    btns = [[InlineKeyboardButton(f"{c.get('icon','📁')} {c['name']}", callback_data=f"cat_select:{c['slug']}")] for c in res]
    await update.message.reply_text("🎯 **Matching Platforms:**", reply_markup=InlineKeyboardMarkup(btns))
''',

    "bot.py": '''from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import get_settings
from database.firebase import firebase_manager
from services.job_queue import job_recovery_manager

from handlers.start import start_command
from handlers.categories import show_categories, category_callback_handler
from handlers.search import prompt_search, handle_search_query
from handlers.downloads import handle_video_url_message, download_quality_callback
from handlers.history import show_history
from handlers.settings import show_settings
from handlers.referrals import show_referrals
from handlers.support import show_statistics, show_support

async def main_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "📥 Download Categories": await show_categories(update, context)
    elif t == "🔍 Search": await prompt_search(update, context)
    elif t == "📜 My History": await show_history(update, context)
    elif t == "⚙️ Settings": await show_settings(update, context)
    elif t == "📊 My Statistics": await show_statistics(update, context)
    elif t == "💬 Support": await show_support(update, context)
    elif context.user_data.get("awaiting_search"): await handle_search_query(update, context)
    elif t.startswith("http"): await handle_video_url_message(update, context)

def main():
    settings = get_settings()
    firebase_manager.initialize()
    job_recovery_manager.reconcile_stranded_jobs()

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(category_callback_handler, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(download_quality_callback, pattern="^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_router))

    print("Bot polling started...")
    app.run_polling()

if __name__ == "__main__":
    main()
'''
}

for path, content in files.items():
    folder = os.path.dirname(path)
    if folder: os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"Created: {path}")

os.system("git add . && git commit -m 'feat: complete telegram video downloader bot' && git push origin main")
print("\n✅ SUCCESS: All Bot files created and pushed to GitHub successfully!")
