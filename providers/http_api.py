from typing import Any, Dict
import httpx
from logger import logger
from services.provider_base import BaseProviderAdapter, MediaMetadata, VideoFormatOption


class GenericHttpApiAdapter(BaseProviderAdapter):
    def __init__(self, provider_id: str, config: Dict[str, Any]):
        self.provider_id = provider_id
        self.endpoint = config.get("endpoint_url", "")
        self.method = config.get("http_method", "GET").upper()
        self.headers = config.get("headers", {})
        self.timeout = config.get("timeout_seconds", 15)
        self.response_mapping = config.get("response_mapping", {})

    async def health_check(self) -> Dict[str, Any]:
        if not self.endpoint:
            return {"status": "down", "error": "No endpoint configured"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.head(self.endpoint, headers=self.headers)
                return {"status": "healthy" if res.status_code < 500 else "degraded", "code": res.status_code}
        except Exception as e:
            return {"status": "down", "error": str(e)}

    def _resolve_json_path(self, data: dict, path: str, default: Any = None) -> Any:
        try:
            parts = path.split(".")
            curr = data
            for p in parts:
                curr = curr[p]
            return curr
        except Exception:
            return default

    async def extract_info(self, url: str) -> MediaMetadata:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if self.method == "POST":
                    resp = await client.post(self.endpoint, json={"url": url}, headers=self.headers)
                else:
                    resp = await client.get(self.endpoint, params={"url": url}, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"HTTP API provider {self.provider_id} extraction failed: {e}")
                raise RuntimeError(f"Provider error: {e}")

        direct_url_key = self.response_mapping.get("direct_url_path", "download_url")
        title_key = self.response_mapping.get("title_path", "title")

        direct_url = self._resolve_json_path(data, direct_url_key)
        title = self._resolve_json_path(data, title_key, "Extracted Video")

        if not direct_url or not isinstance(direct_url, str):
            raise ValueError(f"Provider {self.provider_id} returned invalid direct media URL.")

        return MediaMetadata(
            platform=self.provider_id,
            video_id="ext_vid",
            title=str(title),
            thumbnail_url=self._resolve_json_path(data, "thumbnail"),
            duration_seconds=self._resolve_json_path(data, "duration"),
            available_formats=[
                VideoFormatOption("best", "Best Quality", "Auto", None, "mp4", direct_url)
            ],
            source_url=url
        )

    async def create_download_url(self, url: str, format_id: str) -> str:
        meta = await self.extract_info(url)
        return meta.available_formats[0].download_url
