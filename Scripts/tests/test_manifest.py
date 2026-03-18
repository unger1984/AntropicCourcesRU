import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from export_anthropic_courses import (
    collect_existing_course_slugs,
    merge_course_entry,
    should_process_details,
    sync_course_files_from_disk,
)


class MergeManifestTest(unittest.TestCase):
    def test_merge_keeps_existing_asset_status(self) -> None:
        existing = {
            "title": "Claude Code in Action",
            "status": "downloaded",
            "assets": {
                "captions_en": {
                    "url": "https://cdn.jwplayer.com/tracks/2WoI1d71.srt",
                    "status": "translated",
                }
            },
        }
        discovered = {
            "title": "Claude Code in Action",
            "status": "discovered",
            "assets": {
                "captions_en": {
                    "url": "https://cdn.jwplayer.com/tracks/2WoI1d71.srt",
                    "status": "downloaded",
                },
                "video_1080p": {
                    "url": "https://cdn.jwplayer.com/videos/example.mp4",
                    "status": "discovered",
                },
            },
        }

        merged = merge_course_entry(existing, discovered)

        self.assertEqual(merged["status"], "downloaded")
        self.assertEqual(merged["assets"]["captions_en"]["status"], "translated")
        self.assertIn("video_1080p", merged["assets"])

    def test_targeted_course_should_process_even_with_existing_details(self) -> None:
        course = {"url": "https://anthropic.skilljar.com/claude-code-in-action", "details_fetched_at": "2026-03-17T13:00:00+00:00"}

        self.assertTrue(
            should_process_details(
                slug="claude-code-in-action",
                course=course,
                target_slug="claude-code-in-action",
                refresh_details=False,
            )
        )

    def test_sync_course_files_from_disk_adds_derived_files_and_aggregates_status(self) -> None:
        with TemporaryDirectory() as tmp:
            course_dir = Path(tmp)
            (course_dir / "Assets").mkdir()
            (course_dir / "course-description.en.md").write_text("# Test\n", encoding="utf-8")
            (course_dir / "course-description.ru.md").write_text("# Тест\n", encoding="utf-8")
            (course_dir / "playback.json").write_text("{}", encoding="utf-8")
            (course_dir / "Assets" / "captions_ru.srt").write_text("1\n", encoding="utf-8")

            course = {
                "status": "discovered",
                "assets": {
                    "captions_en": {
                        "status": "downloaded",
                        "local_path": str(course_dir / "Assets" / "captions_en.srt"),
                    }
                },
            }

            synced = sync_course_files_from_disk(course_dir, course)

            self.assertIn("course_description_en_md", synced["derived_files"])
            self.assertIn("course_description_ru_md", synced["derived_files"])
            self.assertIn("playback_json", synced["derived_files"])
            self.assertEqual(synced["assets"]["captions_en"]["status"], "translated")
            self.assertEqual(synced["status"], "translated")

    def test_collect_existing_course_slugs_from_disk(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "claude-code-in-action").mkdir()
            (root / "README.md").write_text("ignore", encoding="utf-8")

            slugs = collect_existing_course_slugs(root)

            self.assertEqual(slugs, ["claude-code-in-action"])


if __name__ == "__main__":
    unittest.main()
