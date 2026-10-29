import time
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