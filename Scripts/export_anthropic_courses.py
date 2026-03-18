#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://anthropic.skilljar.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)
DEFAULT_FETCH_TIMEOUT = 180
DEFAULT_DOWNLOAD_TIMEOUT = 600
DEFAULT_RETRIES = 2
ASSET_EXTENSIONS = (".pdf", ".zip", ".pptx", ".docx", ".txt", ".md")
STATUS_PRIORITY = {
    "failed": 0,
    "discovered": 1,
    "blocked_auth": 2,
    "downloaded": 3,
    "translated": 4,
}
DERIVED_FILE_SUFFIXES = (
    "course-description.en.md",
    "course-description.ru.md",
    "playback.json",
)
INVALID_DESCRIPTION_PATTERNS = (
    "already registered",
    "sign in",
    "rate limit code not recognized",
    "this video is still being processed",
    "uh oh! something went wrong",
)
COURSE_CHATDATA_ALIASES = {
    "claude-code-in-action": "claudecode",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.replace("/", "--") or "root"


def safe_name(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return cleaned or "item"


def normalize_language_label(label: str) -> str:
    normalized = safe_name(label)
    aliases = {
        "english": "en",
        "english_captions": "en",
        "french": "fr",
        "german": "de",
        "japanese": "ja",
        "korean": "ko",
        "portuguese": "pt",
        "spanish": "es",
        "russian": "ru",
    }
    return aliases.get(normalized, normalized)


def make_request_headers(cookie_header: Optional[str] = None) -> Dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def html_to_text(value: str) -> str:
    text = re.sub(r"</p\s*>", "\n\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r", "")
    paragraphs = [
        " ".join(line.split())
        for line in re.split(r"\n{2,}", text)
        if " ".join(line.split())
    ]
    return "\n\n".join(paragraphs).strip()


def is_valid_description_text(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    return not any(pattern in normalized for pattern in INVALID_DESCRIPTION_PATTERNS)


def extract_js_string(field_name: str, text: str) -> Optional[str]:
    match = re.search(
        rf"{re.escape(field_name)}\s*:\s*(?P<quote>[\"`])(?P<value>.*?)(?P=quote)",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return None
    return match.group("value")


def extract_object_block(source: str, start_index: int) -> Optional[str]:
    brace_start = source.find("{", start_index)
    if brace_start == -1:
        return None
    depth = 0
    in_string = False
    quote_char = ""
    escaped = False
    for index in range(brace_start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                in_string = False
            continue
        if char in {'"', "'", "`"}:
            in_string = True
            quote_char = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start : index + 1]
    return None


def extract_course_metadata_from_embedded_data(course_slug: str, html_source: str) -> Dict[str, str]:
    path_match = re.search(rf'path:\s*"/{re.escape(course_slug)}"', html_source)
    if not path_match:
        return {}
    object_start = html_source.rfind("const ", 0, path_match.start())
    if object_start == -1:
        object_start = path_match.start()
    object_block = extract_object_block(html_source, object_start)
    if not object_block:
        return {}

    title = html_to_text(extract_js_string("title", object_block) or "")
    subtitle = html_to_text(extract_js_string("subtitle", object_block) or "")

    overview_match = re.search(r"overview\s*:\s*\{", object_block)
    description = ""
    if overview_match:
        overview_block = extract_object_block(object_block, overview_match.start())
        if overview_block:
            description = html_to_text(extract_js_string("description", overview_block) or "")

    metadata = {}
    if title:
        metadata["title"] = title
    if subtitle and is_valid_description_text(subtitle):
        metadata["subtitle"] = subtitle
    if description and is_valid_description_text(description):
        metadata["description_en"] = description
    return metadata


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ensure_dirs(root: Path) -> Dict[str, Path]:
    paths = {
        "root": root,
        "catalog": root / "Catalog",
        "courses": root / "Courses",
        "logs": root / "Logs",
        "state": root / "State",
        "scripts": root / "Scripts",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "updated_at": None, "courses": {}, "errors": []}


def save_manifest(path: Path, manifest: dict) -> None:
    manifest["updated_at"] = now_iso()
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def merge_status(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    if existing is None:
        return new
    if new is None:
        return existing
    if STATUS_PRIORITY.get(new, -1) > STATUS_PRIORITY.get(existing, -1):
        return new
    return existing


def merge_asset_entry(existing: dict, discovered: dict) -> dict:
    merged = dict(existing)
    for key, value in discovered.items():
        if key == "status":
            merged[key] = merge_status(existing.get(key), value)
        else:
            merged[key] = value if value is not None else existing.get(key)
    return merged


def merge_course_entry(existing: dict, discovered: dict) -> dict:
    merged = dict(existing)
    for key, value in discovered.items():
        if key == "status":
            merged[key] = merge_status(existing.get(key), value)
        elif key == "assets":
            merged_assets = dict(existing.get("assets", {}))
            for asset_key, asset_value in value.items():
                merged_assets[asset_key] = merge_asset_entry(
                    merged_assets.get(asset_key, {}),
                    asset_value,
                )
            merged["assets"] = merged_assets
        elif key == "lesson_urls":
            merged["lesson_urls"] = ordered_unique(
                list(value or []) + list(existing.get("lesson_urls", []))
            )
        elif key == "lessons":
            merged_lessons = dict(existing.get("lessons", {}))
            for lesson_key, lesson_value in value.items():
                merged_lessons[lesson_key] = {**merged_lessons.get(lesson_key, {}), **lesson_value}
            merged["lessons"] = merged_lessons
        elif key == "derived_files":
            merged_files = dict(existing.get("derived_files", {}))
            for file_key, file_value in value.items():
                merged_files[file_key] = {**merged_files.get(file_key, {}), **file_value}
            merged["derived_files"] = merged_files
        else:
            merged[key] = value if value not in (None, "", []) else existing.get(key)
    return merged


def parse_video_rank(asset_key: str, asset: dict) -> int:
    label = asset.get("label") or asset_key
    match = re.search(r"(\d{3,4})p", label)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d{3,4})p", asset_key)
    if match:
        return int(match.group(1))
    return -1


def select_assets_for_download(
    assets: Dict[str, dict],
    all_video_renditions: bool,
) -> Dict[str, dict]:
    if all_video_renditions:
        return assets
    filtered: Dict[str, dict] = {}
    best_video_key = None
    best_video_rank = -1
    for asset_key, asset in assets.items():
        if asset.get("kind") != "video":
            filtered[asset_key] = asset
            continue
        rank = parse_video_rank(asset_key, asset)
        if rank > best_video_rank:
            best_video_key = asset_key
            best_video_rank = rank
    if best_video_key:
        filtered[best_video_key] = assets[best_video_key]
    return filtered


def derive_course_status(course: dict) -> str:
    status = course.get("status") or "discovered"
    for asset in course.get("assets", {}).values():
        status = merge_status(status, asset.get("status")) or status
    for derived in course.get("derived_files", {}).values():
        status = merge_status(status, derived.get("status")) or status
    return status


def should_process_details(
    slug: str,
    course: dict,
    target_slug: Optional[str],
    refresh_details: bool,
) -> bool:
    if target_slug and slug == target_slug:
        return True
    if course.get("details_fetched_at") and not refresh_details:
        return False
    return True


def sync_course_files_from_disk(course_dir: Path, course_entry: dict) -> dict:
    assets = dict(course_entry.get("assets", {}))
    assets_dir = course_dir / "Assets"
    if assets_dir.exists():
        for asset_key, asset in assets.items():
            local_path = asset.get("local_path")
            if local_path and Path(local_path).exists():
                asset["status"] = merge_status(asset.get("status"), "downloaded")
        for file_path in assets_dir.iterdir():
            if not file_path.is_file():
                continue
            matching_key = next(
                (key for key in assets if safe_name(file_path.stem) == key),
                None,
            )
            if matching_key:
                assets[matching_key]["local_path"] = str(file_path)
                assets[matching_key]["status"] = merge_status(
                    assets[matching_key].get("status"),
                    "downloaded",
                )
    course_entry["assets"] = assets
    derived_files = dict(course_entry.get("derived_files", {}))
    for suffix in DERIVED_FILE_SUFFIXES:
        path = course_dir / suffix
        if path.exists():
            key = safe_name(path.name.replace(".", "_"))
            derived_files[key] = {
                "path": str(path),
                "status": "translated" if path.name.endswith(".ru.md") else "downloaded",
            }
    ru_caption = course_dir / "Assets" / "captions_ru.srt"
    if ru_caption.exists():
        derived_files["captions_ru_srt"] = {
            "path": str(ru_caption),
            "status": "translated",
        }
        if "captions_en" in course_entry.get("assets", {}):
            course_entry["assets"]["captions_en"]["status"] = merge_status(
                course_entry["assets"]["captions_en"].get("status"),
                "translated",
            )
    course_entry["derived_files"] = derived_files
    course_entry["status"] = derive_course_status(course_entry)
    return course_entry


def collect_existing_course_slugs(courses_root: Path) -> List[str]:
    if not courses_root.exists():
        return []
    return sorted(
        child.name
        for child in courses_root.iterdir()
        if child.is_dir()
    )


def write_course_description_file(
    course_dir: Path,
    title: str,
    description: str,
) -> Dict[str, dict]:
    description_path = course_dir / "course-description.en.md"
    if description:
        description_path.write_text(
            f"# {title}\n\n{description}\n",
            encoding="utf-8",
        )
        return {
            "course_description_en_md": {
                "path": str(description_path),
                "status": "downloaded",
            }
        }
    if description_path.exists():
        description_path.unlink()
    return {}


def log_line(log_path: Path, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def fetch_url(
    url: str,
    timeout: int = DEFAULT_FETCH_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    cookie_header: Optional[str] = None,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        request = Request(url, headers=make_request_headers(cookie_header))
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (URLError, socket.timeout, TimeoutError) as error:
            last_error = error
            if attempt == retries:
                raise
            time.sleep(min(2 * (attempt + 1), 5))
    raise last_error or RuntimeError(f"failed to fetch {url}")


def download_binary(
    url: str,
    destination: Path,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
    cookie_header: Optional[str] = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers=make_request_headers(cookie_header))
    with urlopen(request, timeout=timeout) as response:
        destination.write_bytes(response.read())


@dataclass
class AnchorRecord:
    href: str
    text: str
    headings: List[str]


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_anchor = False
        self.current_href = ""
        self.current_text: List[str] = []
        self.current_headings: List[str] = []
        self.current_heading_depth = 0
        self.anchors: List[AnchorRecord] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a":
            self.in_anchor = True
            self.current_href = attrs_dict.get("href") or ""
            self.current_text = []
            self.current_headings = []
        elif self.in_anchor and re.fullmatch(r"h[1-6]", tag):
            self.current_heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.in_anchor:
            text = " ".join(" ".join(self.current_text).split())
            headings = [" ".join(item.split()) for item in self.current_headings if item.strip()]
            self.anchors.append(AnchorRecord(self.current_href, text, headings))
            self.in_anchor = False
            self.current_href = ""
            self.current_text = []
            self.current_headings = []
        elif self.in_anchor and re.fullmatch(r"h[1-6]", tag) and self.current_heading_depth > 0:
            self.current_heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.in_anchor:
            return
        self.current_text.append(data)
        if self.current_heading_depth > 0:
            self.current_headings.append(data)


def extract_catalog_courses(html: str) -> List[dict]:
    parser = AnchorParser()
    parser.feed(html)
    courses: List[dict] = []
    for anchor in parser.anchors:
        href = urljoin(BASE_URL, anchor.href)
        if not href.startswith(BASE_URL):
            continue
        parsed = urlparse(href)
        if parsed.path in {"/", ""}:
            continue
        if any(prefix in parsed.path for prefix in ("/auth/", "/checkout/", "/saved-content")):
            continue
        slug = parsed.path.strip("/")
        if "/" in slug:
            continue
        title = anchor.headings[0] if anchor.headings else anchor.text
        subtitle = anchor.text.replace(title, "", 1).strip(" -")
        if not title:
            continue
        courses.append(
            {
                "slug": slug,
                "title": title,
                "subtitle": subtitle,
                "url": href,
                "status": "discovered",
                "assets": {},
                "lesson_urls": [],
            }
        )
    unique = {}
    for course in courses:
        unique[course["slug"]] = course
    return list(unique.values())


def extract_course_page_data(url: str, html: str) -> dict:
    parser = AnchorParser()
    parser.feed(html)
    course_slug = slugify_from_url(url)
    metadata = extract_course_metadata_from_embedded_data(course_slug, html)
    title_match = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    fallback_title = html_to_text(title_match.group(1)) if title_match else course_slug
    text_blocks = re.findall(r"<p[^>]*>\s*(.*?)\s*</p>", html, flags=re.IGNORECASE | re.DOTALL)
    fallback_description = html_to_text("".join(f"<p>{block}</p>" for block in text_blocks[:3]))
    description = metadata.get("description_en", "")
    if not description and is_valid_description_text(fallback_description):
        description = fallback_description

    lesson_urls = []
    assets: Dict[str, dict] = {}
    player_urls = sorted(
        {
            player_url.replace("//", "https://", 1)
            if player_url.startswith("//")
            else player_url
            for player_url in re.findall(
                r"""(?:(?:https?:)?//content\.jwplatform\.com/players/[^"' ]+\.js)""",
                html,
            )
        }
    )
    for anchor in parser.anchors:
        href = urljoin(url, anchor.href)
        if not href.startswith("http"):
            continue
        parsed = urlparse(href)
        if (
            parsed.netloc == "anthropic.skilljar.com"
            and parsed.path.startswith(f"/{course_slug}/")
            and parsed.path.count("/") >= 2
            and not parsed.path.endswith("/resume")
        ):
            lesson_urls.append(href)
            continue
        if "playback.json" in href:
            assets["playback_json"] = {"url": href, "status": "discovered", "kind": "metadata"}
        elif href.endswith(".srt") or ".srt?" in href:
            label = anchor.text or parsed.path.rsplit("/", 1)[-1]
            asset_key = f"captions_{normalize_language_label(label)}"
            assets[asset_key] = {"url": href, "status": "discovered", "kind": "captions"}
        elif href.endswith(".m3u8") or ".m3u8?" in href:
            assets["manifest_hls"] = {"url": href, "status": "discovered", "kind": "video_manifest"}
        elif href.endswith(".mp4") or ".mp4?" in href:
            label = anchor.text or parsed.path.rsplit("/", 1)[-1]
            asset_key = f"video_{safe_name(label)}"
            assets[asset_key] = {"url": href, "status": "discovered", "kind": "video"}
        elif parsed.path.lower().endswith(ASSET_EXTENSIONS):
            label = anchor.text or parsed.path.rsplit("/", 1)[-1]
            suffix = parsed.path.rsplit(".", 1)[-1].lower()
            asset_key = f"attachment_{safe_name(label)}_{suffix}"
            assets[asset_key] = {"url": href, "status": "discovered", "kind": "attachment"}
    for index, player_url in enumerate(player_urls, start=1):
        key = "jwplayer_script" if len(player_urls) == 1 else f"jwplayer_script_{index}"
        assets[key] = {"url": player_url, "status": "discovered", "kind": "player_script"}

    return {
        "slug": course_slug,
        "title": metadata.get("title", fallback_title),
        "subtitle": metadata.get("subtitle", description),
        "url": url,
        "status": "discovered",
        "assets": assets,
        "lesson_urls": ordered_unique(lesson_urls),
        "description_en": description,
    }


def extract_playback_url_from_player_js(player_js: str) -> Optional[str]:
    match = re.search(r'''"playlist"\s*:\s*"([^"]+playback\.json[^"]*)"''', player_js)
    if not match:
        return None
    playback_url = match.group(1)
    if playback_url.startswith("//"):
        return "https:" + playback_url
    return playback_url


def enrich_assets_from_playback(assets: Dict[str, dict], playback: dict) -> Dict[str, dict]:
    playlist = playback.get("playlist") or []
    if not playlist:
        return assets
    item = playlist[0]
    for source in item.get("sources", []):
        source_url = source.get("file")
        if not source_url:
            continue
        source_type = source.get("type")
        label = source.get("label") or source_type or Path(urlparse(source_url).path).name
        if source_type == "application/vnd.apple.mpegurl":
            key = "manifest_hls"
            kind = "video_manifest"
        elif source_type == "audio/mp4":
            key = f"audio_{safe_name(label)}"
            kind = "audio"
        else:
            key = f"video_{safe_name(label)}"
            kind = "video"
        assets[key] = merge_asset_entry(
            assets.get(key, {}),
            {"url": source_url, "status": "discovered", "kind": kind, "label": label},
        )
    for track in item.get("tracks", []):
        track_url = track.get("file")
        if not track_url:
            continue
        if track.get("kind") == "captions":
            label = normalize_language_label(track.get("label") or "captions")
            key = f"captions_{label}"
            kind = "captions"
        elif track.get("kind") == "thumbnails":
            key = "thumbnails_vtt"
            kind = "thumbnails"
        else:
            key = f"track_{safe_name(track.get('label') or track.get('kind') or 'track')}"
            kind = track.get("kind") or "track"
        assets[key] = merge_asset_entry(
            assets.get(key, {}),
            {"url": track_url, "status": "discovered", "kind": kind},
        )
    image_url = item.get("image")
    if image_url:
        assets["poster_image"] = merge_asset_entry(
            assets.get("poster_image", {}),
            {"url": image_url, "status": "discovered", "kind": "image"},
        )
    return assets


def maybe_download_asset(asset_key: str, asset: dict, course_dir: Path, log_path: Path) -> dict:
    url = asset["url"]
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".bin"
    filename = f"{asset_key}{suffix}"
    destination = course_dir / "Assets" / filename
    if destination.exists():
        asset["local_path"] = str(destination)
        asset["status"] = merge_status(asset.get("status"), "downloaded")
        return asset
    try:
        download_binary(url, destination)
        asset["local_path"] = str(destination)
        asset["status"] = "downloaded"
        log_line(log_path, f"downloaded asset {asset_key}: {url}")
    except HTTPError as error:
        if error.code in (401, 403):
            asset["status"] = merge_status(asset.get("status"), "blocked_auth")
            asset["error"] = f"http_{error.code}"
            log_line(log_path, f"blocked auth for asset {asset_key}: {url}")
        else:
            asset["status"] = "failed"
            asset["error"] = f"http_{error.code}"
            log_line(log_path, f"failed asset {asset_key}: {url} ({error.code})")
    except URLError as error:
        asset["status"] = "failed"
        asset["error"] = str(error.reason)
        log_line(log_path, f"network failure for asset {asset_key}: {url} ({error.reason})")
    return asset


def maybe_download_asset_with_auth(
    asset_key: str,
    asset: dict,
    course_dir: Path,
    log_path: Path,
    cookie_header: Optional[str],
) -> dict:
    url = asset["url"]
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".bin"
    filename = f"{asset_key}{suffix}"
    destination = course_dir / "Assets" / filename
    if destination.exists():
        asset["local_path"] = str(destination)
        asset["status"] = merge_status(asset.get("status"), "downloaded")
        return asset
    try:
        download_binary(url, destination, cookie_header=cookie_header)
        asset["local_path"] = str(destination)
        asset["status"] = "downloaded"
        log_line(log_path, f"downloaded asset {asset_key}: {url}")
    except HTTPError as error:
        if error.code in (401, 403):
            asset["status"] = merge_status(asset.get("status"), "blocked_auth")
            asset["error"] = f"http_{error.code}"
            log_line(log_path, f"blocked auth for asset {asset_key}: {url}")
        else:
            asset["status"] = "failed"
            asset["error"] = f"http_{error.code}"
            log_line(log_path, f"failed asset {asset_key}: {url} ({error.code})")
    except URLError as error:
        asset["status"] = "failed"
        asset["error"] = str(error.reason)
        log_line(log_path, f"network failure for asset {asset_key}: {url} ({error.reason})")
    return asset


def extract_window_json_object(source: str, variable_name: str) -> Optional[dict]:
    marker = f"{variable_name} ="
    start = source.find(marker)
    if start == -1:
        return None
    object_block = extract_object_block(source, start)
    if not object_block:
        return None
    try:
        return json.loads(object_block)
    except json.JSONDecodeError:
        return None


def lesson_slug(index: int, title: str) -> str:
    return f"{index:03d}-{safe_name(title).replace('_', '-')}"


def extract_lesson_page_data(url: str, html: str, course_slug: str) -> dict:
    html_module = __import__("html")
    title = ""
    skilljar_title_match = re.search(
        r"""var\s+skilljarCourse\s*=\s*\{[\s\S]*?lesson\s*:\s*\{[\s\S]*?title\s*:\s*['"]([^'"]+)['"]""",
        html,
    )
    if skilljar_title_match:
        title = html_module.unescape(skilljar_title_match.group(1)).strip()
    if not title:
        lesson_args_match = re.search(
            r"""var\s+lessonJsArgs\s*=\s*\{[\s\S]*?lessonTitle\s*:\s*['"]([^'"]+)['"]""",
            html,
        )
        if lesson_args_match:
            title = html_module.unescape(lesson_args_match.group(1)).strip()
    if not title:
        title_match = re.search(
            r"<h2[^>]*>\s*(.*?)\s*</h2>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        title = html_to_text(title_match.group(1)) if title_match else slugify_from_url(url)

    nav_lessons = []
    parser = AnchorParser()
    parser.feed(html)
    for anchor in parser.anchors:
        href = urljoin(url, anchor.href)
        parsed = urlparse(href)
        if parsed.netloc != urlparse(BASE_URL).netloc:
            continue
        if not parsed.path.startswith(f"/{course_slug}/"):
            continue
        if parsed.path.count("/") < 2:
            continue
        label = anchor.text.strip()
        if not label or label == title:
            nav_lessons.append({"title": label or title, "url": href})
            continue
        nav_lessons.append({"title": label, "url": href})

    deduped_nav = []
    seen_urls = set()
    for lesson in nav_lessons:
        if lesson["url"] in seen_urls:
            continue
        seen_urls.add(lesson["url"])
        deduped_nav.append(lesson)

    assets: Dict[str, dict] = {}
    player_urls = sorted(
        {
            player_url.replace("//", "https://", 1)
            if player_url.startswith("//")
            else player_url
            for player_url in re.findall(
                r"""(?:(?:https?:)?//content\.jwplatform\.com/players/[^"' ]+\.js)""",
                html,
            )
        }
    )
    for index, player_url in enumerate(player_urls, start=1):
        key = "jwplayer_script" if len(player_urls) == 1 else f"jwplayer_script_{index}"
        assets[key] = {"url": player_url, "status": "discovered", "kind": "player_script"}

    chat_data = extract_window_json_object(html, "window.__chatData") or {}
    chat_key = COURSE_CHATDATA_ALIASES.get(course_slug)
    notes_raw = chat_data.get(chat_key) if chat_key else None

    metadata = {
        "title": title,
        "url": url,
        "nav_lessons": deduped_nav,
    }
    if notes_raw:
        metadata["notes_key"] = chat_key
        metadata["notes_length"] = len(notes_raw)

    return {
        "title": title,
        "url": url,
        "assets": assets,
        "metadata": metadata,
        "notes_raw": notes_raw,
    }


def export_lesson_pages(
    course_slug: str,
    course_entry: dict,
    course_dir: Path,
    log_path: Path,
    cookie_header: Optional[str],
    all_video_renditions: bool,
) -> dict:
    lessons = dict(course_entry.get("lessons", {}))
    lesson_urls = course_entry.get("lesson_urls", [])
    for index, lesson_url in enumerate(lesson_urls, start=1):
        html = fetch_url(lesson_url, cookie_header=cookie_header)
        lesson_data = extract_lesson_page_data(lesson_url, html, course_slug)
        lesson_dir = course_dir / "Lessons" / lesson_slug(index, lesson_data["title"])
        source_dir = lesson_dir / "Source"
        source_dir.mkdir(parents=True, exist_ok=True)
        lesson_html_path = source_dir / "lesson-page.html"
        lesson_html_path.write_text(html, encoding="utf-8")

        if lesson_data.get("notes_raw"):
            (source_dir / "notes.xml").write_text(
                lesson_data["notes_raw"],
                encoding="utf-8",
            )

        for asset_key, asset in list(lesson_data["assets"].items()):
            if asset.get("kind") != "player_script":
                continue
            try:
                player_js = fetch_url(asset["url"], cookie_header=cookie_header)
                playback_url = extract_playback_url_from_player_js(player_js)
                if playback_url:
                    lesson_data["assets"]["playback_json"] = merge_asset_entry(
                        lesson_data["assets"].get("playback_json", {}),
                        {
                            "url": playback_url,
                            "status": "discovered",
                            "kind": "metadata",
                        },
                    )
                    playback_json = fetch_url(playback_url, cookie_header=cookie_header)
                    playback_data = json.loads(playback_json)
                    lesson_data["assets"] = enrich_assets_from_playback(
                        lesson_data["assets"],
                        playback_data,
                    )
                    (source_dir / "playback.json").write_text(
                        json.dumps(playback_data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception as error:
                lesson_data["assets"][asset_key]["status"] = "failed"
                lesson_data["assets"][asset_key]["error"] = str(error)
                log_line(log_path, f"failed to expand lesson player for {lesson_url}: {error}")

        selected_assets = select_assets_for_download(
            lesson_data["assets"],
            all_video_renditions=all_video_renditions,
        )
        for asset_key, asset in selected_assets.items():
            lesson_data["assets"][asset_key] = maybe_download_asset_with_auth(
                asset_key,
                asset,
                lesson_dir,
                log_path,
                cookie_header,
            )

        metadata = dict(lesson_data["metadata"])
        metadata["source_html_path"] = str(lesson_html_path)
        metadata["source_dir"] = str(source_dir)
        metadata["assets"] = lesson_data["assets"]
        metadata["status"] = "downloaded"
        if lesson_data.get("notes_raw"):
            metadata["notes_path"] = str(source_dir / "notes.xml")
        metadata_path = lesson_dir / "lesson.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        metadata["metadata_path"] = str(metadata_path)
        lessons[lesson_dir.name] = metadata
        log_line(log_path, f"exported lesson {lesson_dir.name}")
    return lessons


def export_catalog(
    root: Path,
    course_url: Optional[str] = None,
    catalog_only: bool = False,
    refresh_details: bool = False,
    all_video_renditions: bool = False,
    sync_from_disk_only: bool = False,
    cookie_header: Optional[str] = None,
    export_lessons: bool = False,
) -> int:
    paths = ensure_dirs(root)
    manifest_path = paths["state"] / "manifest.json"
    manifest = load_manifest(manifest_path)
    session_log = paths["logs"] / f"session-{datetime.now().strftime('%Y-%m-%d-%H%M')}.log"
    errors_log = paths["logs"] / "errors.log"

    if sync_from_disk_only:
        for slug in collect_existing_course_slugs(paths["courses"]):
            course = manifest["courses"].get(
                slug,
                {
                    "slug": slug,
                    "url": urljoin(BASE_URL, slug),
                    "title": slug.replace("-", " "),
                    "status": "discovered",
                    "assets": {},
                    "lesson_urls": [],
                },
            )
            course_dir = paths["courses"] / slug
            manifest["courses"][slug] = sync_course_files_from_disk(course_dir, course)
        save_manifest(manifest_path, manifest)
        return 0

    target_urls = [course_url] if course_url else [BASE_URL]
    discovered_courses: List[dict] = []
    for target_url in target_urls:
        try:
            html = fetch_url(target_url, cookie_header=cookie_header)
        except Exception as error:  # pragma: no cover - network branch
            message = f"failed to fetch {target_url}: {error}"
            manifest["errors"].append({"url": target_url, "error": str(error), "at": now_iso()})
            log_line(session_log, message)
            log_line(errors_log, message)
            save_manifest(manifest_path, manifest)
            return 1

        snapshot_name = slugify_from_url(target_url) or "catalog"
        snapshot_path = paths["catalog"] / f"{snapshot_name}.html"
        snapshot_path.write_text(html, encoding="utf-8")
        log_line(session_log, f"saved snapshot {snapshot_path}")

        if target_url == BASE_URL:
            catalog_courses = extract_catalog_courses(html)
            log_line(session_log, f"discovered {len(catalog_courses)} courses from catalog")
            discovered_courses.extend(catalog_courses)
        else:
            discovered_courses.append(extract_course_page_data(target_url, html))

    for course in discovered_courses:
        slug = course["slug"]
        manifest["courses"][slug] = merge_course_entry(manifest["courses"].get(slug, {}), course)

    target_slug = slugify_from_url(course_url) if course_url else None
    if not catalog_only:
        course_items = list(manifest["courses"].items())
        if target_slug:
            course_items = [
                (slug, course)
                for slug, course in course_items
                if slug == target_slug
            ]
        for slug, course in course_items:
            if not should_process_details(slug, course, target_slug, refresh_details):
                continue
            try:
                html = fetch_url(course["url"], cookie_header=cookie_header)
                detail_path = paths["catalog"] / f"{slug}.html"
                detail_path.write_text(html, encoding="utf-8")
                discovered = extract_course_page_data(course["url"], html)
                discovered["details_fetched_at"] = now_iso()
                course_dir = paths["courses"] / slug
                course_dir.mkdir(parents=True, exist_ok=True)
                description = discovered.get("description_en", "")
                derived_files = write_course_description_file(
                    course_dir,
                    discovered["title"],
                    description,
                )
                if derived_files:
                    discovered["derived_files"] = derived_files
                for asset_key, asset in list(discovered["assets"].items()):
                    if asset.get("kind") != "player_script":
                        continue
                    try:
                        player_js = fetch_url(asset["url"], cookie_header=cookie_header)
                        playback_url = extract_playback_url_from_player_js(player_js)
                        if playback_url:
                            discovered["assets"]["playback_json"] = merge_asset_entry(
                                discovered["assets"].get("playback_json", {}),
                                {
                                    "url": playback_url,
                                    "status": "discovered",
                                    "kind": "metadata",
                                },
                            )
                            playback_json = fetch_url(playback_url, cookie_header=cookie_header)
                            playback_data = json.loads(playback_json)
                            discovered["assets"] = enrich_assets_from_playback(
                                discovered["assets"],
                                playback_data,
                            )
                            (course_dir / "playback.json").write_text(
                                json.dumps(playback_data, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                            discovered.setdefault("derived_files", {})["playback_json"] = {
                                "path": str(course_dir / "playback.json"),
                                "status": "downloaded",
                            }
                    except Exception as error:  # pragma: no cover - network branch
                        discovered["assets"][asset_key]["status"] = "failed"
                        discovered["assets"][asset_key]["error"] = str(error)
                        log_line(
                            session_log,
                            f"failed to expand player script for {slug}: {asset['url']} ({error})",
                        )
                selected_assets = select_assets_for_download(
                    discovered["assets"],
                    all_video_renditions=all_video_renditions,
                )
                for asset_key, asset in selected_assets.items():
                    discovered["assets"][asset_key] = maybe_download_asset_with_auth(
                        asset_key,
                        asset,
                        course_dir,
                        session_log,
                        cookie_header,
                    )
                merged_course = merge_course_entry(course, discovered)
                if export_lessons and merged_course.get("lesson_urls"):
                    merged_course["lessons"] = export_lesson_pages(
                        slug,
                        merged_course,
                        course_dir,
                        session_log,
                        cookie_header,
                        all_video_renditions,
                    )
                merged_course = sync_course_files_from_disk(course_dir, merged_course)
                manifest["courses"][slug] = merged_course
                save_manifest(manifest_path, manifest)
                log_line(session_log, f"processed course {slug}")
            except HTTPError as error:  # pragma: no cover - network branch
                if error.code in (401, 403):
                    manifest["courses"][slug]["status"] = merge_status(
                        manifest["courses"][slug].get("status"),
                        "blocked_auth",
                    )
                    message = f"blocked auth for course {slug}: {course['url']}"
                else:
                    manifest["courses"][slug]["status"] = "failed"
                    message = f"http {error.code} for course {slug}: {course['url']}"
                log_line(session_log, message)
                log_line(errors_log, message)
                save_manifest(manifest_path, manifest)
            except Exception as error:  # pragma: no cover - network branch
                manifest["courses"][slug]["status"] = "failed"
                message = f"failed course {slug}: {error}"
                log_line(session_log, message)
                log_line(errors_log, message)
                save_manifest(manifest_path, manifest)

    save_manifest(manifest_path, manifest)
    return 0


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Anthropic Academy public course data.")
    parser.add_argument(
        "--output-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Root output directory for AntropicCource",
    )
    parser.add_argument("--course-url", help="Process one specific course URL")
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Only capture the catalog without processing each course page",
    )
    parser.add_argument(
        "--refresh-details",
        action="store_true",
        help="Re-fetch course pages even if details were already captured",
    )
    parser.add_argument(
        "--all-video-renditions",
        action="store_true",
        help="Download every MP4 rendition instead of only the best available one",
    )
    parser.add_argument(
        "--sync-from-disk-only",
        action="store_true",
        help="Do not fetch network resources, only reconcile manifest with files already on disk",
    )
    parser.add_argument(
        "--cookie-header",
        help="Raw Cookie header for authenticated Skilljar requests",
    )
    parser.add_argument(
        "--export-lessons",
        action="store_true",
        help="Export lesson pages and lesson assets for the selected course",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    return export_catalog(
        Path(args.output_root),
        course_url=args.course_url,
        catalog_only=args.catalog_only,
        refresh_details=args.refresh_details,
        all_video_renditions=args.all_video_renditions,
        sync_from_disk_only=args.sync_from_disk_only,
        cookie_header=args.cookie_header,
        export_lessons=args.export_lessons,
    )


if __name__ == "__main__":
    sys.exit(main())
