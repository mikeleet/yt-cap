from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChannelAddRequest(BaseModel):
    url: str


class ChannelUpdateRequest(BaseModel):
    auto_update: Optional[bool] = None
    update_interval: Optional[int] = None


class ChannelResponse(BaseModel):
    channel_id: str
    name: str
    handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    auto_update: Optional[bool] = None
    update_interval: Optional[int] = None
    total_videos: int = 0
    captions_ok: int = 0
    captions_failed: int = 0
    last_scan_at: Optional[datetime] = None
    last_download_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    sync_status: str
    error_message: Optional[str] = None
    current_progress: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChannelStatusResponse(BaseModel):
    channel_id: str
    name: str
    sync_status: str
    total_videos: int = 0
    captions_ok: int = 0
    captions_failed: int = 0
    captions_pending: int = 0
    captions_skipped: int = 0
    last_scan_at: Optional[datetime] = None
    last_download_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    current_progress: Optional[dict] = None
    error_message: Optional[str] = None
    current_phase: Optional[str] = None


class VideoResponse(BaseModel):
    video_id: str
    channel_id: str
    title: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_sec: Optional[int] = None
    publish_date: Optional[datetime] = None
    caption_status: str
    caption_lang: Optional[str] = None
    caption_chars: Optional[int] = None
    never_download: bool
    retry_count: int
    last_error: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    caption_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VideoUpdateRequest(BaseModel):
    never_download: Optional[bool] = None


class CaptionResponse(BaseModel):
    video_id: str
    title: Optional[str] = None
    language: Optional[str] = None
    text: str
    chars: int


class SettingsResponse(BaseModel):
    max_concurrent_fetches: str
    min_interval_seconds: str
    max_per_hour: str
    max_per_day: str


class SettingsUpdateRequest(BaseModel):
    max_concurrent_fetches: Optional[str] = None
    min_interval_seconds: Optional[str] = None
    max_per_hour: Optional[str] = None
    max_per_day: Optional[str] = None


class SSEMessage(BaseModel):
    event: str
    data: dict
