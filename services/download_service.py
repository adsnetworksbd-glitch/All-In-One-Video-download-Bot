from services.url_validator import validate_and_sanitize_url
from services.api_registry import provider_registry
from database.firebase import firebase_manager
from database.credit_repo import credit_repo, InsufficientCreditsError
from database.job_repo import job_repo
from logger import logger

def get_credit_price_for_quality(format_id: str) -> int:
    try:
        pricing = firebase_manager.safe_get("bot_settings/credits/pricing_by_quality")
        if pricing and isinstance(pricing, dict):
            if format_id in pricing:
                return int(pricing[format_id])
            for k, v in pricing.items():
                if k in format_id:
                    return int(v)
    except Exception:
        pass
    fallback = {"audio": 5, "360p": 5, "480p": 8, "720p": 10, "1080p": 20}
    for k, v in fallback.items():
        if k in format_id:
            return v
    return 10

# Alias for backward compatibility
get_credit_price = get_credit_price_for_quality

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
        cost = get_credit_price_for_quality(format_id)
        credit_repo.reserve_or_deduct_credits(user_id, cost, job_id, f"Download {format_id}")
        provider = provider_registry.get_provider_for_platform(plat)
        try:
            direct_url = await provider.create_download_url(video_url, format_id)
            job_repo.record_history(user_id, job_id, plat, title, format_id, cost)
            job_repo.update_job_status(job_id, "COMPLETED")
            return direct_url
        except Exception as e:
            logger.error(f"Download failed for job {job_id}: {e}")
            credit_repo.refund_credits(user_id, cost, job_id, "Refund on link error")
            job_repo.update_job_status(job_id, "REFUNDED")
            raise e

download_service = DownloadService()
