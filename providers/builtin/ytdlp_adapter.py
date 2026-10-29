import asyncio, yt_dlp
from services.provider_base import BaseProviderAdapter, MediaMetadata, VideoFormatOption

class YtDlpAdapter(BaseProviderAdapter):
    def __init__(self):
        self.opts = {"quiet": True, "no_warnings": True, "skip_download": True, "simulate": True, "socket_timeout": 15}

    def _sync(self, url):
        with yt_dlp.YoutubeDL(self.opts) as ydl: return ydl.extract_info(url, download=False)

    async def extract_info(self, url: str) -> MediaMetadata:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._sync, url)
        formats = []
        for f in info.get("formats", []):
            u = f.get("url")
            if not u: continue
            h = f.get("height")
            if h:
                formats.append(VideoFormatOption(
                    format_id=f"{h}p", label=f"{h}p HD" if h >= 720 else f"{h}p",
                    resolution=f"{f.get('width', 0)}x{h}", file_size_bytes=f.get("filesize"),
                    extension=f.get("ext", "mp4"), download_url=u
                ))
        unique = {fmt.format_id: fmt for fmt in formats}
        return MediaMetadata(
            platform=info.get("extractor", "generic"), video_id=info.get("id", "vid"),
            title=info.get("title", "Video"), thumbnail_url=info.get("thumbnail"),
            duration_seconds=info.get("duration"), available_formats=list(unique.values()), source_url=url
        )

    async def create_download_url(self, url: str, format_id: str) -> str:
        meta = await self.extract_info(url)
        for f in meta.available_formats:
            if f.format_id == format_id and f.download_url: return f.download_url
        return meta.available_formats[0].download_url