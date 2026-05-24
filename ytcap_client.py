"""
yt-cap Python Client Library
=============================
Simple HTTP client for interacting with a yt-cap server.

Copy this file to your client app. Requires: pip install httpx

    Service URL: https://yt.15gva.duckdns.org (TrueNAS Nginx Proxy → MacBook)
    Local URL:   http://localhost:8506

Usage:
    from ytcap_client import YtCapClient

    yt = YtCapClient("https://yt.15gva.duckdns.org", api_key="12345")

    # List channels with status
    channels = yt.list_channels()

    # Add a new channel
    yt.add_channel("https://www.youtube.com/@channel/videos")
    yt.scan_channel("UC...")

    # Get new captions since last sync
    new = yt.get_videos(status="downloaded", since="2026-05-20T00:00:00")

    # Get caption text for a video
    text = yt.get_caption_text("jH4pZdrn-oU")

    # Batch get captions (efficient for RAG sync)
    captions = yt.get_captions_batch(["id1", "id2", "id3"])

    # Get download queue and analytics
    queue = yt.get_queue()

    # Trigger download
    yt.download_channel("UC...")

    # Check server health
    health = yt.health()
"""

import httpx
from typing import Optional


class YtCapClient:
    """Thin HTTP client for yt-cap REST API."""

    def __init__(self, base_url: str = "http://localhost:8506", api_key: str = "12345"):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict | list:
        r = httpx.get(f"{self.base_url}{path}", headers=self.headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict = None) -> dict:
        r = httpx.post(f"{self.base_url}{path}", headers=self.headers, json=body or {}, timeout=30)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict = None) -> dict:
        r = httpx.patch(f"{self.base_url}{path}", headers=self.headers, json=body or {}, timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> dict:
        r = httpx.delete(f"{self.base_url}{path}", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    # ── Health ────────────────────────────────────────────

    def health(self) -> dict:
        """GET /health — no auth needed."""
        r = httpx.get(f"{self.base_url}/health", timeout=5)
        r.raise_for_status()
        return r.json()

    # ── Channels ──────────────────────────────────────────

    def list_channels(self) -> list[dict]:
        """GET /api/channels — list all subscribed channels with status."""
        return self._get("/api/channels")

    def get_channel(self, channel_id: str) -> dict:
        """GET /api/channels/{id} — get single channel detail."""
        return self._get(f"/api/channels/{channel_id}")

    def get_channel_status(self, channel_id: str) -> dict:
        """GET /api/channels/{id}/status — detailed sync status with counts."""
        return self._get(f"/api/channels/{channel_id}/status")

    def add_channel(self, url: str) -> dict:
        """POST /api/channels — subscribe to a YouTube channel by URL or @handle."""
        return self._post("/api/channels", {"url": url})

    def update_channel(self, channel_id: str, auto_update: bool = None,
                       update_interval: int = None) -> dict:
        """PATCH /api/channels/{id} — toggle auto-update or change interval (seconds)."""
        body = {}
        if auto_update is not None:
            body["auto_update"] = auto_update
        if update_interval is not None:
            body["update_interval"] = update_interval
        return self._patch(f"/api/channels/{channel_id}", body)

    def delete_channel(self, channel_id: str) -> dict:
        """DELETE /api/channels/{id} — remove channel and all its data."""
        return self._delete(f"/api/channels/{channel_id}")

    # ── Scan / Download ───────────────────────────────────

    def scan_channel(self, channel_id: str) -> dict:
        """POST /api/channels/{id}/scan — discover videos (fast, no rate limit)."""
        return self._post(f"/api/channels/{channel_id}/scan")

    def download_channel(self, channel_id: str) -> dict:
        """POST /api/channels/{id}/download — download captions for pending videos."""
        return self._post(f"/api/channels/{channel_id}/download")

    def sync_channel(self, channel_id: str) -> dict:
        """POST /api/channels/{id}/sync — scan + download in sequence."""
        return self._post(f"/api/channels/{channel_id}/sync")

    # ── Videos ────────────────────────────────────────────

    def get_videos(self, channel_id: str = None, status: str = None,
                   since: str = None, days: int = None,
                   limit: int = 500, offset: int = 0) -> list[dict]:
        """GET /api/videos — list videos across all channels with filters.

        Args:
            channel_id: Filter to specific channel
            status: 'none', 'downloaded', 'failed', 'unavailable', 'skipped'
            since: ISO datetime string — captions downloaded after this time
            days: Videos from last N days
        """
        params = {"limit": limit, "offset": offset}
        if channel_id:
            params["channel_id"] = channel_id
        if status:
            params["status"] = status
        if since:
            params["since"] = since
        if days:
            params["days"] = days
        return self._get("/api/videos", params)

    def get_channel_videos(self, channel_id: str, status: str = None,
                           last_n: int = None, days: int = None,
                           limit: int = 500, offset: int = 0) -> list[dict]:
        """GET /api/channels/{id}/videos — list videos for a specific channel."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if last_n:
            params["last_n"] = last_n
        if days:
            params["days"] = days
        return self._get(f"/api/channels/{channel_id}/videos", params)

    def get_video(self, video_id: str) -> dict:
        """GET /api/videos/{id} — get single video metadata."""
        return self._get(f"/api/videos/{video_id}")

    def update_video(self, video_id: str, never_download: bool = None) -> dict:
        """PATCH /api/videos/{id} — mark video to skip."""
        body = {}
        if never_download is not None:
            body["never_download"] = never_download
        return self._patch(f"/api/videos/{video_id}", body)

    # ── Captions ───────────────────────────────────────────

    def get_caption(self, video_id: str, format: str = "json") -> dict | str:
        """GET /api/videos/{id}/caption — get caption text.

        format='json' returns {video_id, title, language, text, chars}
        format='txt' returns raw text string
        """
        r = httpx.get(
            f"{self.base_url}/api/videos/{video_id}/caption",
            headers=self.headers,
            params={"format": format},
            timeout=15,
        )
        r.raise_for_status()
        if format == "txt":
            return r.text
        return r.json()

    def get_caption_text(self, video_id: str) -> str:
        """Shorthand: get raw caption text for a single video."""
        return self.get_caption(video_id, format="txt")

    def get_captions_batch(self, video_ids: list[str]) -> list[dict]:
        """POST /api/captions/batch — efficient batch retrieval (max 100).

        Returns list of {video_id, title, language, text, chars}.
        """
        return self._post("/api/captions/batch", {"video_ids": video_ids})

    def redownload_caption(self, video_id: str) -> dict:
        """POST /api/videos/{id}/caption — force re-fetch caption."""
        return self._post(f"/api/videos/{video_id}/caption")

    def delete_caption(self, video_id: str) -> dict:
        """DELETE /api/videos/{id}/caption — remove stored caption."""
        return self._delete(f"/api/videos/{video_id}/caption")

    # ── Queue / Analytics ──────────────────────────────────

    def get_queue(self) -> dict:
        """GET /api/queue — download queue + recent downloads + failed list."""
        return self._get("/api/queue")

    def get_history(self, channel_id: str) -> dict:
        """GET /api/channels/{id}/history — per-channel download history."""
        return self._get(f"/api/channels/{channel_id}/history")

    # ── Settings ───────────────────────────────────────────

    def get_settings(self) -> dict:
        """GET /api/settings — rate limit settings."""
        return self._get("/api/settings")

    def update_settings(self, **kwargs) -> dict:
        """PATCH /api/settings — update rate limits (max_concurrent_fetches, etc.)."""
        return self._patch("/api/settings", kwargs)
