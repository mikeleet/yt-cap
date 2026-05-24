import time
import tempfile
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

WEBSITE_URL = "https://www.downloadyoutubesubtitles.com"


class RateLimitError(Exception):
    """Site is rate-limiting us. Contains cooldown seconds if known."""
    def __init__(self, msg: str, cooldown: int = 0):
        super().__init__(msg)
        self.cooldown = cooldown


class CaptionResult:
    def __init__(self, text: str, language: str, is_generated: bool = True,
                 publish_date: str = "", duration_sec: int = 0):
        self.text = text
        self.language = language
        self.is_generated = is_generated
        self.publish_date = publish_date
        self.duration_sec = duration_sec


def is_rate_limited() -> bool:
    """Quick check: can we reach the site?"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(WEBSITE_URL, timeout=15000)
            browser.close()
        return False
    except Exception:
        return True


def _parse_page_meta(body_text: str) -> tuple[str, int]:
    """Extract publish_date and duration_sec from the page body.
    Returns (date_string_iso, duration_seconds). If missing, returns ('', 0)."""
    publish_date = ""
    duration_sec = 0

    # Date: "Date:  25 Oct 2009"
    m = re.search(r"Date:\s*(\d{1,2}\s+\w{3}\s+\d{4})", body_text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d %b %Y")
            publish_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Duration: "Duration:  00:03:33"
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})", body_text)
    if m:
        duration_sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))

    return publish_date, duration_sec


def fetch_caption(video_id: str) -> tuple[CaptionResult | None, str | None]:
    """Fetch transcript via downloadyoutubesubtitles.com.

    Returns (CaptionResult, None) on success or (None, error_string) on failure.
    Raises RateLimitError if the site asks us to wait.
    CaptionResult includes free metadata (publish_date, duration) from the page.
    """
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    page_url = f"{WEBSITE_URL}/?u={youtube_url}"
    result_text: list[str] = []

    def handle_download(download):
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="ytcap_")
        os.close(fd)
        download.save_as(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                result_text.append(f.read())
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("download", handle_download)

            try:
                page.goto(page_url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                for attempt in range(3):
                    page.wait_for_timeout(2000)

                    body_text = page.evaluate("() => document.body.innerText")

                    # Site says we need to wait
                    if "Please allow your previous download" in body_text:
                        m = re.search(r"after (\d+) seconds", body_text)
                        wait = int(m.group(1)) if m else 10
                        raise RateLimitError(f"site_cooldown:{wait}", cooldown=wait)

                    # Video genuinely has no subtitles
                    body_lower = body_text.lower()
                    if any(phrase in body_lower for phrase in [
                        "there is no subtitle",
                        "no subtitle in this video",
                        "no subtitles available",
                        "no transcript",
                    ]):
                        m = re.search(r'(no (subtitle|transcript)[^.?!]*[.?!])', body_lower)
                        reason = m.group(1).strip() if m else "no subtitle available"
                        return None, f"no_transcript:{reason}"

                    # Click TXT download button
                    links = page.query_selector_all(".butako")
                    for link in links:
                        label = (link.text_content() or "").strip()
                        if label.upper() == "TXT":
                            link.click()
                            page.wait_for_timeout(5000)
                            break

                    if result_text:
                        text = result_text[0].strip()
                        if len(text) >= 50:
                            body_final = page.evaluate("() => document.body.innerText")
                            pub_date, dur_sec = _parse_page_meta(body_final)
                            lang = "auto"
                            m = re.search(
                                r"Primary Subtitles[^:]*:\s*\n\s*SRT\s*\n\s*VTT\s*\n\s*TXT\s*\n\s*([^(]+?)\s*\(",
                                body_final,
                            )
                            if m:
                                lang_name = m.group(1).strip().lower()
                                lang_map = {
                                    "korean": "ko", "english": "en", "japanese": "ja",
                                    "chinese": "zh", "spanish": "es", "french": "fr",
                                    "german": "de", "russian": "ru", "portuguese": "pt",
                                    "arabic": "ar", "hindi": "hi", "vietnamese": "vi",
                                    "thai": "th", "indonesian": "id", "turkish": "tr",
                                    "italian": "it", "dutch": "nl", "polish": "pl",
                                }
                                lang = lang_map.get(lang_name, lang_name[:2])
                            return CaptionResult(
                                text=text, language=lang, is_generated=True,
                                publish_date=pub_date, duration_sec=dur_sec,
                            ), None

                    if attempt < 2:
                        page.goto(page_url, timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=20000)

                if result_text and len(result_text[0].strip()) < 50:
                    return None, "no_transcript:empty or error"
                return None, "no_transcript:download failed"

            finally:
                browser.close()

    except RateLimitError:
        raise
    except PlaywrightTimeout:
        raise RateLimitError("Playwright timeout - likely rate limited", cooldown=180)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "blocked" in msg.lower():
            raise RateLimitError(msg, cooldown=180)
        return None, f"no_transcript:{msg[:200]}"
