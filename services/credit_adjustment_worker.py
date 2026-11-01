import asyncio, time
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