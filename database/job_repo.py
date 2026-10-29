import time, uuid
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