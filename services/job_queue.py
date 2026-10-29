from database.firebase import firebase_manager
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