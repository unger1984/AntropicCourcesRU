#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRUNABLE_FILES = {
    "video_1080p.mp4",
    "video_ru.mp4",
    "poster_image.jpg",
}


def iter_prunable_pairs(course_slug: str):
    course_dir = ROOT / "Courses" / course_slug
    docs_dir = ROOT / "docs" / "courses" / course_slug

    for lesson_dir in sorted((course_dir / "Lessons").glob("*")):
        if not lesson_dir.is_dir():
            continue
        source_assets = lesson_dir / "Assets"
        docs_assets = docs_dir / "lessons" / lesson_dir.name / "assets"
        for name in PRUNABLE_FILES:
            source_path = source_assets / name
            docs_path = docs_assets / name
            if source_path.exists() and docs_path.exists():
                yield source_path, docs_path

    course_source_assets = course_dir / "Assets"
    course_docs_assets = docs_dir / "assets"
    for name in PRUNABLE_FILES:
        source_path = course_source_assets / name
        docs_path = course_docs_assets / name
        if source_path.exists() and docs_path.exists():
            yield source_path, docs_path


def prune_course_media(course_slug: str, dry_run: bool) -> int:
    removed = 0
    for source_path, docs_path in iter_prunable_pairs(course_slug):
        print(f"{'WOULD REMOVE' if dry_run else 'REMOVE'} {source_path} (published copy: {docs_path})")
        if not dry_run:
            source_path.unlink()
        removed += 1
    print(f"Total {'candidate' if dry_run else 'removed'} files: {removed}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove duplicated published media from Courses/ after docs/ is verified."
    )
    parser.add_argument("--course-slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return prune_course_media(args.course_slug, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
