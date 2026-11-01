import asyncio, time
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