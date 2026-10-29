from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class VideoFormatOption:
    format_id: str
    label: str
    resolution: Optional[str]
    file_size_bytes: Optional[int]
    extension: str
    download_url: Optional[str] = None

@dataclass
class MediaMetadata:
    platform: str
    video_id: str
    title: str
    thumbnail_url: Optional[str]
    duration_seconds: Optional[int]
    available_formats: List[VideoFormatOption]
    source_url: str

class BaseProviderAdapter(ABC):
    @abstractmethod
    async def extract_info(self, url: str) -> MediaMetadata: pass
    @abstractmethod
    async def create_download_url(self, url: str, format_id: str) -> str: pass