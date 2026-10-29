import time
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