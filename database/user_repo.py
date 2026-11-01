import time
from typing import Any, Dict, Optional, Tuple
from database.firebase import firebase_manager


class UserRepository:
    def __init__(self):
        self.fb = firebase_manager

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return self.fb.safe_get(f"users/{telegram_id}")

    def is_user_banned(self, telegram_id: int) -> bool:
        u = self.get_user(telegram_id)
        return bool(u and u.get("is_banned", False))

    def update_last_active(self, telegram_id: int) -> None:
        now = int(time.time() * 1000)
        try:
            self.fb.safe_update(f"users/{telegram_id}", {"last_active_at": now})
        except Exception:
            pass

    def onboard_user_if_new(
        self,
        telegram_id: int,
        first_name: str,
        username: Optional[str] = None,
        last_name: Optional[str] = None,
        referred_by: Optional[int] = None,
        welcome_bonus: int = 50
    ) -> Tuple[Dict[str, Any], bool]:
        existing = self.get_user(telegram_id)
        if existing:
            self.update_last_active(telegram_id)
            return existing, False

        now = int(time.time() * 1000)
        valid_ref = referred_by if (referred_by and referred_by != telegram_id) else None
        new_user = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "credit_balance": int(welcome_bonus),
            "is_banned": False,
            "role": "user",
            "referred_by": valid_ref,
            "created_at": now,
            "last_active_at": now
        }
        self.fb.safe_set(f"users/{telegram_id}", new_user)
        return new_user, True


# Export singleton instance for handlers
user_repo = UserRepository()
