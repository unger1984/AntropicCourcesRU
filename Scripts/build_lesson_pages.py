#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SKILLJAR_BASE = "https://anthropic.skilljar.com"


@dataclass
class Cue:
    start: float
    end: float
    text: str


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_srt(path: Path) -> list[Cue]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").replace("\r", "")
    blocks = [block.strip() for block in content.split("\n\n") if block.strip()]
    cues: list[Cue] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        timing = lines[1] if "-->" in lines[1] else lines[0]
        match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            timing,
        )
        if not match:
            continue
        nums = [int(part) for part in match.groups()]
        start = nums[0] * 3600 + nums[1] * 60 + nums[2] + nums[3] / 1000
        end = nums[4] * 3600 + nums[5] * 60 + nums[6] + nums[7] / 1000
        text = " ".join(line.strip() for line in lines[2:] if line.strip())
        if text:
            cues.append(Cue(start, end, text))
    return cues


def parse_vtt(path: Path) -> list[Cue]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").replace("\r", "")
    blocks = [block.strip() for block in content.split("\n\n") if block.strip()]
    cues: list[Cue] = []
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip() and line.strip() != "WEBVTT"]
        if not lines:
            continue
        timing = lines[0]
        match = re.match(
            r"(\d{2}):(\d{2})[:](\d{2})[.,](\d{3})\s+-->\s+(\d{2}):(\d{2})[:](\d{2})[.,](\d{3})",
            timing,
        )
        if not match:
            continue
        nums = [int(part) for part in match.groups()]
        start = nums[0] * 3600 + nums[1] * 60 + nums[2] + nums[3] / 1000
        end = nums[4] * 3600 + nums[5] * 60 + nums[6] + nums[7] / 1000
        text = " ".join(line.strip() for line in lines[1:] if line.strip())
        if text:
            cues.append(Cue(start, end, text))
    return cues


def write_srt(path: Path, cues: list[Cue]) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        def fmt(value: float) -> str:
            total_ms = int(round(value * 1000))
            hours = total_ms // 3_600_000
            total_ms %= 3_600_000
            minutes = total_ms // 60_000
            total_ms %= 60_000
            seconds = total_ms // 1000
            millis = total_ms % 1000
            return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

        lines.append(str(index))
        lines.append(f"{fmt(cue.start)} --> {fmt(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_asset(source: Optional[Path], destination: Path) -> bool:
    if not source or not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def find_matching_div_end(source: str, start_index: int) -> int:
    token_re = re.compile(r"<div\b|</div>", re.IGNORECASE)
    depth = 0
    end_index = -1
    for match in token_re.finditer(source, start_index):
        token = match.group(0).lower()
        if token.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                closing_bracket = source.find(">", match.start())
                end_index = closing_bracket + 1
                break
    if end_index == -1:
        raise ValueError("Failed to find matching </div>")
    return end_index


def replace_div_by_marker(source: str, marker: str, replacement: str) -> str:
    start = source.find(marker)
    if start == -1:
        return source
    end = find_matching_div_end(source, start)
    return source[:start] + replacement + source[end:]


def strip_scripts(source: str) -> str:
    return re.sub(r"<script\b[^>]*>.*?</script>\s*", "", source, flags=re.DOTALL | re.IGNORECASE)


def normalize_head(source: str, assets_prefix: str, page_title: str) -> str:
    source = re.sub(r'lang="en-US"', 'lang="ru"', source)
    source = re.sub(r"<title>.*?</title>", f"<title>{html.escape(page_title)}</title>", source, count=1, flags=re.DOTALL)
    source = re.sub(r'<link[^>]+rel="stylesheet"[^>]*>\s*', "", source, flags=re.IGNORECASE)
    head_close = "</head>"
    injection = (
        f'    <link rel="stylesheet" href="{assets_prefix}/sj_course_platform_v2.css"/>\n'
        f'    <link rel="stylesheet" href="{assets_prefix}/prism.css"/>\n'
        f'    <link rel="stylesheet" href="{assets_prefix}/anthropic-theme.css"/>\n'
        f'    <link rel="stylesheet" href="{assets_prefix}/lesson-local.css"/>\n'
    )
    return source.replace(head_close, injection + head_close, 1)


def sanitize_js_hooks(source: str) -> str:
    source = re.sub(r'\s(onmouseup|onkeydown|onclick)="[^"]*"', "", source)
    return source


def translate_exact_text(source: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        source = source.replace(old, new)
    return source


def translate_visible_anchor_text(source: str, english: str, russian: str) -> str:
    return re.sub(
        rf"(>)(\s*){re.escape(english)}(\s*)(<)",
        rf"\1\2{russian}\3\4",
        source,
    )


def localize_titles(source: str, translations: dict) -> str:
    course_title = translations.get("course_title", "Claude Code in Action")
    source = re.sub(
        r'(<h1 class="course-title break-word">\s*)Claude Code in Action(\s*<span class="sj-course-time"></span>\s*</h1>)',
        rf"\1{course_title}\2",
        source,
    )
    source = source.replace('title: \'Claude Code in Action\'', f"title: '{course_title}'")

    for en, ru in translations.get("sections", {}).items():
        source = source.replace(f">{en}</h3>", f">{ru}</h3>")

    for en, ru in translations.get("lessons", {}).items():
        source = source.replace(f'title="{en}"', f'title="{ru}"')
        source = source.replace(f">{en}</h2>", f">{ru}</h2>")
        source = source.replace(f">{en}</span>", f">{ru}</span>")
        source = source.replace(f"Previous - {en}", f"Предыдущий — {ru}")
        source = source.replace(f"Lesson,Prev,{en},0", f"Lesson,Prev,{ru},0")
        source = source.replace(f"Lesson,Next,{en},0", f"Lesson,Next,{ru},0")
        source = source.replace(f">- {en}</span>", f">- {ru}</span>")
        source = re.sub(
            rf'(<div class="title">\s*){re.escape(en)}(\s*<span class="sj-lesson-time"></span>)',
            rf"\1{ru}\2",
            source,
        )

    return source


def load_lessons(course_dir: Path) -> list[dict]:
    lessons: list[dict] = []
    for lesson_dir in sorted((course_dir / "Lessons").glob("*")):
        if not lesson_dir.is_dir():
            continue
        lesson_json = lesson_dir / "lesson.json"
        if not lesson_json.exists():
            continue
        data = read_json(lesson_json)
        data["slug"] = lesson_dir.name
        data["dir"] = lesson_dir
        lessons.append(data)
    return lessons


def build_local_href_map(lessons: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for lesson in lessons:
        remote_path = urlparse(lesson["url"]).path
        mapping[remote_path] = lesson["slug"]
    return mapping


def rel_link(from_slug: str, to_slug: str) -> str:
    if from_slug == to_slug:
        return "index.html"
    return f"../{to_slug}/index.html"


def rewrite_navigation_links(source: str, local_slug_by_remote_path: dict[str, str], current_slug: str) -> str:
    source = source.replace('href="/claude-code-in-action"', 'href="../../index.html"')

    def replace_href(match: re.Match[str]) -> str:
        path = match.group(1)
        slug = local_slug_by_remote_path.get(path)
        if not slug:
            return f'href="{SKILLJAR_BASE}{path}"'
        return f'href="{rel_link(current_slug, slug)}"'

    source = re.sub(r'href="(/claude-code-in-action/\d+)"', replace_href, source)

    def replace_next_prev(match: re.Match[str]) -> str:
        path = match.group(1)
        slug = local_slug_by_remote_path.get(path)
        if not slug:
            return f'href="{SKILLJAR_BASE}{path}"'
        return f'href="{rel_link(current_slug, slug)}"'

    next_match = re.search(r"onNextLessonClick\('(/claude-code-in-action/\d+)'\)", source)
    next_href = "#"
    if next_match:
        next_slug = local_slug_by_remote_path.get(next_match.group(1))
        if next_slug:
            next_href = rel_link(current_slug, next_slug)
        else:
            next_href = f"{SKILLJAR_BASE}{next_match.group(1)}"
    source = re.sub(r'onmouseup="onNextLessonClick\(\'(/claude-code-in-action/\d+)\'\)"', "", source)
    source = re.sub(r'onkeydown="onNextLessonClick\(\'(/claude-code-in-action/\d+)\'\)"', "", source)
    if 'class="small button next-lesson-link"' in source:
        source = source.replace('class="small button next-lesson-link"', f'href="{next_href}" class="small button next-lesson-link"', 1)
    return source


def build_player_markup(audio_sources: list[str], subtitle_payload: dict, poster_src: str) -> str:
    source_tags: list[str] = []
    audio_buttons: list[str] = []

    if len(audio_sources) == 2:
        source_tags.append(f'                    <source src="{audio_sources[0]}" type="video/mp4" data-audio="ru">')
        source_tags.append(f'                    <source src="{audio_sources[1]}" type="video/mp4" data-audio="original">')
        audio_buttons.append('                      <button type="button" class="media-option" data-audio-option="ru">RU</button>')
        audio_buttons.append('                      <button type="button" class="media-option" data-audio-option="original">EN</button>')
        default_audio = "ru"
    else:
        source_tags.append(f'                    <source src="{audio_sources[0]}" type="video/mp4" data-audio="original">')
        audio_buttons.append('                      <button type="button" class="media-option" data-audio-option="original">EN</button>')
        default_audio = "original"

    subtitle_buttons = ['                      <button type="button" class="media-option" data-subtitle="off">Off</button>']
    if "ru" in subtitle_payload:
        subtitle_buttons.insert(0, '                      <button type="button" class="media-option" data-subtitle="ru">RU</button>')
    if "en" in subtitle_payload:
        subtitle_buttons.insert(-1, '                      <button type="button" class="media-option" data-subtitle="en">EN</button>')

    subtitles_json = json.dumps(subtitle_payload, ensure_ascii=False, indent=2)
    return f"""
<div class="course-fixed-content-video">
    <div class="video-max">
        <div class="video-player flex-video widescreen">
            <div class="media-player skilljar-local-player" data-player-root data-default-audio="{default_audio}" data-default-subtitle="off">
                <video controls preload="metadata" playsinline poster="{poster_src}">
{chr(10).join(source_tags)}
                </video>
                <script type="application/json" data-subtitles-json>
{subtitles_json}
                </script>
            </div>
        </div>
        <div class="media-toolbar">
            <div class="media-group">
                <div class="media-menu">
                    <span class="media-label">Аудио</span>
{chr(10).join(audio_buttons)}
                </div>
            </div>
            <div class="media-group">
                <div class="media-menu">
                    <span class="media-label">CC</span>
{chr(10).join(subtitle_buttons)}
                </div>
            </div>
        </div>
    </div>
</div>
""".strip()


def build_subtitles_payload(lesson_dir: Path, assets_dir: Path, fallback_ru_srt: Optional[Path]) -> dict:
    payload: dict[str, dict] = {}
    ru_srt = lesson_dir / "Assets" / "captions_ru.srt"
    if not ru_srt.exists() and fallback_ru_srt and fallback_ru_srt.exists():
        copy_asset(fallback_ru_srt, ru_srt)
    if ru_srt.exists():
        payload["ru"] = {"label": "Русские", "cues": [cue.__dict__ for cue in parse_srt(ru_srt)]}
    en_srt = lesson_dir / "Assets" / "captions_en.srt"
    if en_srt.exists():
        payload["en"] = {"label": "English", "cues": [cue.__dict__ for cue in parse_srt(en_srt)]}
    return payload


def ensure_intro_ru_assets(course_dir: Path, lesson_dir: Path) -> None:
    ru_srt = lesson_dir / "Assets" / "captions_ru.srt"
    if not ru_srt.exists():
        course_ru_srt = course_dir / "Assets" / "captions_ru.srt"
        if course_ru_srt.exists():
            copy_asset(course_ru_srt, ru_srt)
        else:
            vtt = ROOT / "docs" / "courses" / "claude-code-in-action" / "assets" / "captions_ru.vtt"
            if vtt.exists():
                write_srt(ru_srt, parse_vtt(vtt))


def prepare_media_assets(course_dir: Path, lesson: dict, site_assets_dir: Path) -> tuple[list[str], dict]:
    lesson_dir = lesson["dir"]
    assets_dir = lesson_dir / "Assets"
    site_assets_dir.mkdir(parents=True, exist_ok=True)

    copy_asset(assets_dir / "video_1080p.mp4", site_assets_dir / "video_1080p.mp4")
    copy_asset(assets_dir / "poster_image.jpg", site_assets_dir / "poster_image.jpg")

    audio_sources = ["assets/video_1080p.mp4"]
    if lesson["slug"] == "001-introduction":
        ensure_intro_ru_assets(course_dir, lesson_dir)
        site_course_assets = ROOT / "docs" / "courses" / "claude-code-in-action" / "assets"
        intro_ru = site_course_assets / "video_ru_v2.mp4"
        if not intro_ru.exists():
            intro_ru = site_course_assets / "video_ru.mp4"
        if intro_ru.exists():
            copy_asset(intro_ru, site_assets_dir / "video_ru.mp4")
            audio_sources = ["assets/video_ru.mp4", "assets/video_1080p.mp4"]
    else:
        ru_video = assets_dir / "video_ru.mp4"
        if ru_video.exists():
            copy_asset(ru_video, site_assets_dir / "video_ru.mp4")
            audio_sources = ["assets/video_ru.mp4", "assets/video_1080p.mp4"]

    subtitles = build_subtitles_payload(lesson_dir, site_assets_dir, course_dir / "Assets" / "captions_ru.srt" if lesson["slug"] == "001-introduction" else None)
    return audio_sources, subtitles


def replace_summary_html(source: str, summary_html: str) -> str:
    marker = '<div class="lesson-description-content">'
    if marker not in source:
        return source
    replacement = f'{marker}\n{summary_html}\n                            </div>'
    return replace_div_by_marker(source, marker, replacement)


def replace_modular_lesson_html(source: str, summary_html: str) -> str:
    marker = '<sjwc-lesson-content-item class="course-text-content course-scrollable-content">'
    start = source.find(marker)
    if start == -1:
        return source
    end_marker = "</sjwc-lesson-content-item>"
    end = source.find(end_marker, start)
    if end == -1:
        return source
    end += len(end_marker)
    replacement = f"{marker}\n            \n                    {summary_html}\n            \n        </sjwc-lesson-content-item>"
    return source[:start] + replacement + source[end:]


def build_page(course_dir: Path, lesson: dict, lessons: list[dict], translations: dict) -> str:
    lesson_dir = lesson["dir"]
    site_lesson_dir = ROOT / "docs" / "courses" / course_dir.name / "lessons" / lesson["slug"]
    site_assets_dir = site_lesson_dir / "assets"
    assets_prefix = "../../../../assets"

    source_path = lesson_dir / "Source" / "lesson-page.html"
    source = source_path.read_text(encoding="utf-8")
    source = strip_scripts(source)
    source = normalize_head(
        source,
        assets_prefix,
        f'{translations.get("lessons", {}).get(lesson["title"], lesson["title"])} | {translations.get("course_title", "Claude Code в действии")}',
    )

    replacements = {
        ">Course Overview<": ">Обзор курса<",
        ">Anthropic Academy<": ">Академия Anthropic<",
        ">Courses<": ">Курсы<",
        ">Summary<": ">Конспект<",
        ">Downloads<": ">Загрузки<",
        ">Previous<": ">Предыдущий<",
        ">Next<": ">Следующий<",
        ">details<": ">детали<",
        ">Open in Claude<": ">Открыть в Claude<",
        ">Complete<": ">Завершить<",
    }
    source = translate_exact_text(source, replacements)
    source = translate_visible_anchor_text(source, "Anthropic Academy", "Академия Anthropic")
    source = translate_visible_anchor_text(source, "Courses", "Курсы")
    source = translate_visible_anchor_text(source, "My Profile", "Профиль")
    source = translate_visible_anchor_text(source, "Sign Out", "Выйти")
    source = translate_visible_anchor_text(source, "Header Navigation", "Навигация")
    source = localize_titles(source, translations)
    source = rewrite_navigation_links(source, build_local_href_map(lessons), lesson["slug"])
    source = sanitize_js_hooks(source)

    audio_sources, subtitles = prepare_media_assets(course_dir, lesson, site_assets_dir)
    source = replace_div_by_marker(
        source,
        '<div class="course-fixed-content-video">',
        build_player_markup(audio_sources, subtitles, "assets/poster_image.jpg"),
    )

    summary_ru_path = lesson_dir / "Source" / "summary_ru.html"
    if summary_ru_path.exists():
        summary_html = summary_ru_path.read_text(encoding="utf-8").strip()
        updated = replace_summary_html(source, summary_html)
        if updated == source:
            updated = replace_modular_lesson_html(source, summary_html)
        source = updated

    body_close = "</body>"
    source = source.replace(body_close, f'    <script src="{assets_prefix}/site.js"></script>\n{body_close}', 1)
    return source


def build_course(course_slug: str) -> int:
    course_dir = ROOT / "Courses" / course_slug
    translations = read_json(course_dir / "translations_ru.json")
    lessons = load_lessons(course_dir)
    if not lessons:
        raise SystemExit(f"No lesson.json files found in {course_dir / 'Lessons'}")

    for lesson in lessons:
        site_lesson_dir = ROOT / "docs" / "courses" / course_slug / "lessons" / lesson["slug"]
        site_lesson_dir.mkdir(parents=True, exist_ok=True)
        page_html = build_page(course_dir, lesson, lessons, translations)
        (site_lesson_dir / "index.html").write_text(page_html, encoding="utf-8")
    return 0


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local lesson pages from original Skilljar lesson HTML.")
    parser.add_argument("--course-slug", required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    return build_course(args.course_slug)


if __name__ == "__main__":
    raise SystemExit(main())
