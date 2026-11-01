from typing import Dict
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