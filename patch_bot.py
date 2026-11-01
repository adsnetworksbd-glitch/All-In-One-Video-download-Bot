import os

files = {
    "config.py": '''import re, os, json
from urllib.parse import urlparse
from typing import Any, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STRICT_FIREBASE_HOST_REGEX = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9](-default-rtdb)?\.(firebaseio\.com|[a-z0-9-]+\.firebasedatabase\.app)$",
    re.IGNORECASE
)

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
        if ":" not in v: raise ValueError("Invalid bot token.")
        return v

    @field_validator("FIREBASE_DATABASE_URL")
    @classmethod
    def validate_firebase_url(cls, v: str) -> str:
        cleaned = v.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() != "https": raise ValueError("Scheme must be HTTPS.")
        hostname = parsed.hostname
        if not hostname or not STRICT_FIREBASE_HOST_REGEX.match(hostname):
            raise ValueError(f"Untrusted host: {hostname}")
        if parsed.username or parsed.password or parsed.port is not None or parsed.query or parsed.fragment:
            raise ValueError("URL must not contain credentials, ports, query, or fragments.")
        if parsed.path not in ("", "/"): raise ValueError("URL must not contain custom paths.")
        return f"https://{hostname}/"

    def get_firebase_credentials(self) -> dict:
        if self.FIREBASE_CREDENTIALS_RAW_JSON: return json.loads(self.FIREBASE_CREDENTIALS_RAW_JSON)
        if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            with open(self.FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f: return json.load(f)
        raise ValueError("Firebase credentials missing.")

settings = None
def get_settings() -> AppSettings:
    global settings
    if settings is None: settings = AppSettings()
    return settings
''',

    "database/credit_repo.py": '''import hashlib, time
from typing import Optional
from database.firebase import firebase_manager, DatabaseReadError, DatabaseWriteError
from logger import logger

class InsufficientCreditsError(Exception): pass

class CreditRepository:
    def __init__(self): self.fb = firebase_manager

    def _get_safe_ref_key(self, reference_id: str) -> str:
        raw = str(reference_id).strip()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def record_transaction(self, telegram_user_id: int, amount: int, balance_after: int, tx_type: str, reference_id: str, reason: str, tx_id: Optional[str] = None) -> str:
        transaction_id = tx_id or f"tx_{int(time.time() * 1000)}_{telegram_user_id}"
        record = {
            "transaction_id": transaction_id, "telegram_user_id": int(telegram_user_id),
            "amount": int(amount), "balance_after": int(balance_after), "type": str(tx_type),
            "reference_id": str(reference_id), "reason": str(reason), "created_at": int(time.time() * 1000)
        }
        self.fb.safe_set(f"credit_transactions/{transaction_id}", record)
        return transaction_id

    def reserve_or_deduct_credits(self, telegram_user_id: int, amount: int, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Amount must be positive.")
        safe_op_key = self._get_safe_ref_key(f"debit_{reference_id}")
        deterministic_tx_id = f"tx_debit_{safe_op_key}"
        user_path = f"users/{telegram_user_id}"
        now = int(time.time() * 1000)
        state = {"already_debited": False, "err": None}

        def debit_txn(curr_user):
            if curr_user is None:
                state["err"] = "USER_NOT_FOUND"
                return None
            applied = curr_user.setdefault("applied_debits", {})
            if safe_op_key in applied:
                state["already_debited"] = True
                return curr_user
            curr_bal = curr_user.get("credit_balance")
            if curr_bal is None or curr_bal < amount:
                state["err"] = "INSUFFICIENT"
                state["val"] = curr_bal or 0
                return None
            curr_user["credit_balance"] = curr_bal - amount
            applied[safe_op_key] = {"amount": amount, "at": now, "tx_id": deterministic_tx_id, "ledger_written": False}
            return curr_user

        updated = self.fb.run_transaction(user_path, debit_txn)
        if state["err"]:
            if state["err"] == "INSUFFICIENT": raise InsufficientCreditsError(f"Required {amount}, available {state.get('val', 0)}")
            raise DatabaseWriteError(f"Transaction aborted: {state['err']}")

        final_bal = int(updated.get("credit_balance", 0))
        if not state["already_debited"]:
            self.record_transaction(telegram_user_id, -amount, final_bal, "DOWNLOAD_DEBIT", reference_id, reason, deterministic_tx_id)
            try: self.fb.safe_update(f"users/{telegram_user_id}/applied_debits/{safe_op_key}", {"ledger_written": True})
            except Exception: pass
        return final_bal

    def refund_credits(self, telegram_user_id: int, amount: int, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Amount must be positive.")
        safe_ref = self._get_safe_ref_key(reference_id)
        claim_path = f"refund_claims/{safe_ref}"
        now = int(time.time() * 1000)
        deterministic_tx_id = f"tx_refund_{safe_ref}"
        decision = {"action": "PROCEED"}

        def claim_txn(curr):
            if curr is None:
                return {"reference_id": str(reference_id), "telegram_user_id": int(telegram_user_id), "amount": int(amount), "status": "PENDING", "tx_id": deterministic_tx_id, "created_at": now}
            if curr.get("telegram_user_id") != telegram_user_id or curr.get("amount") != amount:
                decision["action"] = "MISMATCH"
                return curr
            if curr.get("status") == "COMPLETED":
                decision["action"] = "ALREADY_COMPLETED"
                return curr
            decision["action"] = "RECOVER_PENDING"
            return curr

        self.fb.run_transaction(claim_path, claim_txn)
        if decision["action"] == "MISMATCH": raise ValueError(f"Parameter mismatch for refund {reference_id}")
        if decision["action"] == "ALREADY_COMPLETED":
            bal = self.fb.safe_get(f"users/{telegram_user_id}/credit_balance")
            if bal is None: raise DatabaseReadError(f"Could not read balance for {telegram_user_id}")
            return int(bal)

        user_path = f"users/{telegram_user_id}"
        state = {"need_ledger": True}

        def balance_marker_txn(curr_user):
            if curr_user is None: raise DatabaseReadError(f"User {telegram_user_id} not found.")
            applied = curr_user.setdefault("applied_refunds", {})
            if safe_ref in applied:
                if applied[safe_ref].get("ledger_written") is True: state["need_ledger"] = False
                return curr_user
            curr_user["credit_balance"] = (curr_user.get("credit_balance") or 0) + amount
            applied[safe_ref] = {"amount": amount, "at": now, "tx_id": deterministic_tx_id, "ledger_written": False}
            return curr_user

        updated = self.fb.run_transaction(user_path, balance_marker_txn)
        final_bal = int(updated.get("credit_balance", 0))

        if state["need_ledger"]:
            self.record_transaction(telegram_user_id, amount, final_bal, "DOWNLOAD_REFUND", reference_id, reason, deterministic_tx_id)
            try: self.fb.safe_update(f"users/{telegram_user_id}/applied_refunds/{safe_ref}", {"ledger_written": True})
            except Exception: pass

        self.fb.safe_update(claim_path, {"status": "COMPLETED", "completed_at": int(time.time() * 1000), "balance_after": final_bal})
        return final_bal

    def add_reward_credits(self, telegram_user_id: int, amount: int, reward_type: str, reference_id: str, reason: str) -> int:
        if amount <= 0: raise ValueError("Reward amount must be positive.")
        safe_ref = self._get_safe_ref_key(f"reward_{reference_id}")
        user_path = f"users/{telegram_user_id}"
        state = {"already_rewarded": False, "err": None}
        now = int(time.time() * 1000)

        def reward_txn(curr_user):
            if curr_user is None:
                state["err"] = "USER_NOT_FOUND"
                return None
            applied = curr_user.setdefault("applied_rewards", {})
            if safe_ref in applied:
                state["already_rewarded"] = True
                return curr_user
            curr_user["credit_balance"] = (curr_user.get("credit_balance") or 0) + amount
            applied[safe_ref] = {"amount": amount, "at": now}
            return curr_user

        updated = self.fb.run_transaction(user_path, reward_txn)
        if state["err"] == "USER_NOT_FOUND":
            raise DatabaseReadError(f"User {telegram_user_id} not found.")

        new_bal = int(updated.get("credit_balance", 0))
        if not state["already_rewarded"]:
            self.record_transaction(telegram_user_id, amount, new_bal, reward_type, reference_id, reason, f"tx_reward_{safe_ref}")
        return new_bal

credit_repo = CreditRepository()
''',

    "services/api_registry.py": '''from typing import Dict
from database.firebase import firebase_manager, DatabaseReadError
from logger import logger
from providers.builtin.ytdlp_adapter import YtDlpAdapter
from providers.http_api import GenericHttpApiAdapter
from services.provider_base import BaseProviderAdapter

class ProviderRegistry:
    def __init__(self):
        self.builtin = YtDlpAdapter()
        self._custom: Dict[str, GenericHttpApiAdapter] = {}

    def get_provider_for_platform(self, plat: str) -> BaseProviderAdapter:
        try:
            db_p = firebase_manager.safe_get("api_providers")
            if db_p and isinstance(db_p, dict):
                for p_id, p_info in db_p.items():
                    if isinstance(p_info, dict) and p_info.get("is_enabled") and plat in p_info.get("supported_platforms", []):
                        if p_id not in self._custom:
                            self._custom[p_id] = GenericHttpApiAdapter(p_id, p_info.get("config", {}))
                        return self._custom[p_id]
        except DatabaseReadError as e:
            logger.error(f"Database read failure in ProviderRegistry: {e}")
            if plat not in ["youtube", "facebook", "instagram", "tiktok", "pinterest", "twitter"]:
                raise RuntimeError(f"Database unavailable and no fallback for '{plat}'")
        except Exception as e:
            logger.warning(f"Provider registry query warning: {e}")
        return self.builtin

provider_registry = ProviderRegistry()
''',

    "services/broadcast_worker.py": '''import asyncio, time
from database.firebase import firebase_manager
from logger import logger

class BroadcastWorker:
    def __init__(self, bot_app):
        self.bot_app = bot_app
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("BroadcastWorker started.")
        while self.is_running:
            try: await self._process_tasks()
            except Exception as e: logger.error(f"Broadcast loop error: {e}")
            await asyncio.sleep(5.0)

    def stop(self): self.is_running = False

    async def _process_tasks(self):
        tasks = firebase_manager.safe_get("broadcast_tasks")
        if not tasks or not isinstance(tasks, dict): return
        for task_id, task in tasks.items():
            if not isinstance(task, dict) or task.get("status") != "QUEUED": continue
            msg_text = task.get("message_text", "")
            target_filter = task.get("target_filter", "all")
            firebase_manager.safe_update(f"broadcast_tasks/{task_id}", {"status": "IN_PROGRESS", "started_at": int(time.time() * 1000)})
            all_users = firebase_manager.safe_get("users") or {}
            recipients = []
            now = int(time.time() * 1000)
            day_ago = now - (86400 * 1000)

            for u_id, u_data in all_users.items():
                if not isinstance(u_data, dict) or u_data.get("is_banned"): continue
                tg_id = u_data.get("telegram_id")
                if not tg_id: continue
                if target_filter == "active_today" and u_data.get("last_active_at", 0) < day_ago: continue
                if target_filter == "with_balance" and u_data.get("credit_balance", 0) <= 0: continue
                recipients.append(tg_id)

            sent, failed = 0, 0
            for recipient_id in recipients:
                fresh_status = firebase_manager.safe_get(f"broadcast_tasks/{task_id}/status")
                if fresh_status == "CANCELLED":
                    logger.info(f"Broadcast {task_id} cancelled mid-flight.")
                    return
                try:
                    await self.bot_app.bot.send_message(chat_id=recipient_id, text=msg_text, parse_mode="Markdown")
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.05)
                if (sent + failed) % 20 == 0:
                    firebase_manager.safe_update(f"broadcast_tasks/{task_id}/progress", {"sent_count": sent, "failed_count": failed, "total_recipients": len(recipients)})

            firebase_manager.safe_update(f"broadcast_tasks/{task_id}", {
                "status": "COMPLETED", "completed_at": int(time.time() * 1000),
                "progress": {"sent_count": sent, "failed_count": failed, "total_recipients": len(recipients)}
            })
''',

    "services/provider_test_worker.py": '''import asyncio, time
from database.firebase import firebase_manager
from logger import logger
from providers.http_api import GenericHttpApiAdapter

class ProviderTestWorker:
    def __init__(self): self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("ProviderTestWorker started.")
        while self.is_running:
            try: await self._process_tests()
            except Exception as e: logger.error(f"ProviderTest error: {e}")
            await asyncio.sleep(4.0)

    def stop(self): self.is_running = False

    async def _process_tests(self):
        tasks = firebase_manager.safe_get("provider_test_tasks")
        if not tasks or not isinstance(tasks, dict): return
        for task_id, task in tasks.items():
            if not isinstance(task, dict) or task.get("status") != "QUEUED": continue
            provider_id = task.get("provider_id")
            p_config = firebase_manager.safe_get(f"api_providers/{provider_id}/config") or {}
            adapter = GenericHttpApiAdapter(provider_id, p_config)
            t0 = time.time()
            check_result = await adapter.health_check()
            duration_ms = int((time.time() - t0) * 1000)
            health_payload = {
                "status": check_result.get("status", "down"),
                "checked_at": int(time.time() * 1000),
                "response_time_ms": duration_ms,
                "message": check_result.get("error") or f"HTTP {check_result.get('code', 200)}"
            }
            firebase_manager.safe_update(f"api_providers/{provider_id}/last_health_check", health_payload)
            firebase_manager.safe_update(f"provider_test_tasks/{task_id}", {
                "status": "COMPLETED", "result": health_payload, "completed_at": int(time.time() * 1000)
            })
''',

    "services/credit_adjustment_worker.py": '''import asyncio, time
from database.credit_repo import credit_repo
from database.firebase import firebase_manager
from logger import logger

class CreditAdjustmentWorker:
    def __init__(self): self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("CreditAdjustmentWorker started.")
        while self.is_running:
            try: await self._process_requests()
            except Exception as e: logger.error(f"CreditAdjustment error: {e}")
            await asyncio.sleep(3.0)

    def stop(self): self.is_running = False

    async def _process_requests(self):
        requests = firebase_manager.safe_get("credit_adjustment_requests")
        if not requests or not isinstance(requests, dict): return
        for req_id, req in requests.items():
            if not isinstance(req, dict) or req.get("status") != "PENDING": continue
            user_id = req.get("telegram_user_id")
            delta = req.get("delta_amount", 0)
            reason = req.get("reason", "Admin manual adjustment")
            creator = req.get("created_by_uid", "admin")

            if not user_id or delta == 0:
                firebase_manager.safe_update(f"credit_adjustment_requests/{req_id}", {"status": "REJECTED"})
                continue
            try:
                if delta > 0:
                    new_bal = credit_repo.add_reward_credits(user_id, delta, "ADMIN_ADJUSTMENT", req_id, f"[{creator}]: {reason}")
                else:
                    new_bal = credit_repo.reserve_or_deduct_credits(user_id, abs(delta), req_id, f"[{creator}]: {reason}")

                firebase_manager.safe_update(f"credit_adjustment_requests/{req_id}", {
                    "status": "PROCESSED", "processed_at": int(time.time() * 1000), "balance_after": new_bal
                })
            except Exception as ex:
                firebase_manager.safe_update(f"credit_adjustment_requests/{req_id}", {"status": "FAILED", "error": str(ex)})
''',

    "handlers/downloads.py": '''import os, tempfile, httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database.job_repo import job_repo
from database.user_repo import user_repo
from services.download_service import download_service, get_credit_price_for_quality
from logger import logger

def format_file_size(size_bytes: int) -> str:
    if not size_bytes or size_bytes <= 0: return ""
    mb = size_bytes / (1024 * 1024)
    if mb >= 1000: return f" (~{mb / 1024:.1f} GB)"
    return f" (~{mb:.1f} MB)"

async def handle_video_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or not msg.text.strip().startswith("http"): return
    text = msg.text.strip()
    user = update.effective_user
    if user_repo.is_user_banned(user.id):
        await msg.reply_text("⛔ Your account has been suspended from downloading.")
        return

    status = await msg.reply_text("🔎 **Analyzing video link & checking qualities...**", parse_mode="Markdown")
    try:
        j_id, meta = await download_service.prepare_video_options(text, user.id)
    except Exception as e:
        await status.edit_text(f"❌ **Error:** {e}")
        return

    context.user_data[f"job_{j_id}"] = {"url": text, "platform": meta.platform, "title": meta.title}
    kb = []
    for f in meta.available_formats[:6]:
        cost = get_credit_price_for_quality(f.format_id)
        size_str = format_file_size(f.file_size_bytes)
        label = f"🎬 {f.label}{size_str} — 💰 {cost} Cr"
        kb.append([InlineKeyboardButton(label, callback_data=f"dl_select:{j_id}:{f.format_id}")])

    await status.delete()
    summary = f"📹 **Title:** *{meta.title}*\\n🌐 **Platform:** `{meta.platform.title()}`\\n\\n👇 **Select download quality:**"
    if meta.thumbnail_url:
        try:
            await msg.reply_photo(photo=meta.thumbnail_url, caption=summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return
        except Exception: pass
    await msg.reply_text(summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def download_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, j_id, fmt = q.data.split(":")
    cached = context.user_data.get(f"job_{j_id}")
    if not cached:
        persisted = job_repo.get_job(j_id)
        if persisted:
            cached = {"url": persisted.get("sanitized_url"), "platform": persisted.get("category_slug"), "title": persisted.get("original_url")}
    if not cached:
        await q.edit_message_text("⚠️ Download session expired. Please resend the video link.")
        return

    await q.edit_message_text(f"⏳ **Reserving credits & generating download for {fmt}...**", parse_mode="Markdown")
    try:
        direct = await download_service.process_and_deliver_download(
            j_id, q.from_user.id, fmt, cached["url"], cached["platform"], cached["title"]
        )
        delivered_in_chat = False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                head_resp = await client.head(direct)
                content_len = int(head_resp.headers.get("content-length", 0))
                if 0 < content_len <= (20 * 1024 * 1024):
                    dl_resp = await client.get(direct)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tf:
                        tf.write(dl_resp.content)
                        temp_p = tf.name
                    with open(temp_p, "rb") as vf:
                        await q.message.reply_video(video=vf, caption=f"🎬 {cached['title']}\\nQuality: {fmt}")
                    os.remove(temp_p)
                    delivered_in_chat = True
        except Exception: pass

        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ Download Video to Phone", url=direct)]])
        status_txt = "✅ **Video sent above!** You can also tap below to save directly:" if delivered_in_chat else "✅ **Download Link Ready!**\\nTap below to download directly to your mobile device:"
        await q.edit_message_text(status_txt, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}")
''',

    "bot.py": '''import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from config import get_settings
from database.firebase import firebase_manager
from logger import logger
from services.broadcast_worker import BroadcastWorker
from services.credit_adjustment_worker import CreditAdjustmentWorker
from services.job_queue import job_recovery_manager
from services.provider_test_worker import ProviderTestWorker
from handlers.categories import category_callback_handler, show_categories
from handlers.downloads import download_quality_callback, handle_video_url_message
from handlers.history import show_history
from handlers.referrals import show_referrals
from handlers.search import handle_search_query, prompt_search
from handlers.settings import show_settings
from handlers.start import start_command
from handlers.support import show_statistics, show_support

async def main_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    try:
        if firebase_manager.safe_get("bot_settings/maintenance_mode") is True and text.startswith("http"):
            await update.message.reply_text("🚧 **Maintenance Mode:** Video downloads are temporarily paused. Please check back shortly.")
            return
    except Exception: pass

    if text == "📥 Download Categories": await show_categories(update, context)
    elif text == "🔍 Search": await prompt_search(update, context)
    elif text == "📜 My History": await show_history(update, context)
    elif text == "⚙️ Settings": await show_settings(update, context)
    elif text == "📊 My Statistics": await show_statistics(update, context)
    elif text == "💬 Support": await show_support(update, context)
    elif context.user_data.get("awaiting_search"): await handle_search_query(update, context)
    elif text.startswith("http"): await handle_video_url_message(update, context)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Global exception: {context.error}", exc_info=context.error)

async def post_init(app):
    job_recovery_manager.reconcile_stranded_jobs()
    asyncio.create_task(BroadcastWorker(app).start())
    asyncio.create_task(ProviderTestWorker().start())
    asyncio.create_task(CreditAdjustmentWorker().start())
    logger.info("Background workers started successfully.")

def main():
    settings = get_settings()
    firebase_manager.initialize()
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(category_callback_handler, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(download_quality_callback, pattern="^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_router))
    app.add_error_handler(global_error_handler)
    logger.info("Bot is polling updates...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
'''
}

for path, content in files.items():
    folder = os.path.dirname(path)
    if folder: os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"Updated: {path}")

os.system("git add . && git commit -m 'feat: complete production bot with crash recovery and background workers' && git push origin main")
print("\n✅ SUCCESS: Bot repository updated and pushed to GitHub!")
