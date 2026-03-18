from pathlib import Path
import unittest

from export_anthropic_courses import (
    extract_course_page_data,
    extract_lesson_page_data,
    extract_playback_url_from_player_js,
    is_valid_description_text,
    select_assets_for_download,
)


FIXTURE = Path(__file__).parent / "fixtures" / "course.html"


class CourseAssetsTest(unittest.TestCase):
    def test_extract_assets_and_lessons(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")

        course = extract_course_page_data(
            "https://anthropic.skilljar.com/claude-code-in-action",
            html,
        )

        self.assertEqual(course["title"], "Claude Code in Action")
        self.assertEqual(len(course["lesson_urls"]), 1)
        self.assertIn("playback_json", course["assets"])
        self.assertIn("captions_en", course["assets"])
        self.assertIn("attachment_handout_pdf", course["assets"])

    def test_extract_playback_url_from_player_js(self) -> None:
        player_js = """
        var jwConfig = {
          "playlist": "//cdn.jwplayer.com/v2/sites/Lc4Rn1s0/media/rLVnV1aS/playback.json?token=abc"
        };
        jwplayer("botr_rLVnV1aS_Akyo8gQO_div").setup(jwConfig);
        """

        playback_url = extract_playback_url_from_player_js(player_js)

        self.assertEqual(
            playback_url,
            "https://cdn.jwplayer.com/v2/sites/Lc4Rn1s0/media/rLVnV1aS/playback.json?token=abc",
        )

    def test_select_assets_for_download_prefers_best_video_only(self) -> None:
        assets = {
            "video_180p": {"kind": "video", "url": "https://example.com/180.mp4"},
            "video_720p": {"kind": "video", "url": "https://example.com/720.mp4"},
            "video_1080p": {"kind": "video", "url": "https://example.com/1080.mp4"},
            "audio_audio": {"kind": "audio", "url": "https://example.com/audio.m4a"},
            "captions_en": {"kind": "captions", "url": "https://example.com/en.srt"},
            "manifest_hls": {"kind": "video_manifest", "url": "https://example.com/main.m3u8"},
        }

        filtered = select_assets_for_download(assets, all_video_renditions=False)

        self.assertIn("video_1080p", filtered)
        self.assertNotIn("video_180p", filtered)
        self.assertNotIn("video_720p", filtered)
        self.assertIn("audio_audio", filtered)
        self.assertIn("captions_en", filtered)
        self.assertIn("manifest_hls", filtered)

    def test_select_assets_for_download_keeps_all_renditions_when_requested(self) -> None:
        assets = {
            "video_180p": {"kind": "video", "url": "https://example.com/180.mp4"},
            "video_1080p": {"kind": "video", "url": "https://example.com/1080.mp4"},
        }

        filtered = select_assets_for_download(assets, all_video_renditions=True)

        self.assertEqual(set(filtered), {"video_180p", "video_1080p"})

    def test_extract_course_description_from_embedded_course_object(self) -> None:
        html = """
        <html>
          <body>
            <h1>Wrong Visible Title</h1>
            <p>This video is still being processed. Please check back later and refresh the page.</p>
            <p>Already registered? Sign In</p>
            <script>
              const claudeCodeInActionData = {
                path: "/claude-code-in-action",
                title: "Claude Code in Action",
                subtitle:
                  "Practical walkthrough of using <a href='https://claude.com/product/claude-code'>Claude Code</a> to accelerate your development workflow",
                overview: {
                  description:
                    "This course covers <a href='https://claude.com/product/claude-code'>Claude Code</a>, a command-line AI assistant that uses language models to perform development tasks."
                }
              };
            </script>
          </body>
        </html>
        """

        course = extract_course_page_data(
            "https://anthropic.skilljar.com/claude-code-in-action",
            html,
        )

        self.assertEqual(course["title"], "Claude Code in Action")
        self.assertEqual(
            course["description_en"],
            "This course covers Claude Code, a command-line AI assistant that uses language models to perform development tasks.",
        )

    def test_extract_course_page_data_drops_placeholder_only_descriptions(self) -> None:
        html = """
        <html>
          <body>
            <h1>Claude Code in Action</h1>
            <p>This video is still being processed. Please check back later and refresh the page.</p>
            <p>Uh oh! Something went wrong, please try again.</p>
            <p>Already registered? Sign In</p>
          </body>
        </html>
        """

        course = extract_course_page_data(
            "https://anthropic.skilljar.com/claude-code-in-action",
            html,
        )

        self.assertEqual(course["description_en"], "")
        self.assertFalse(is_valid_description_text("Already registered? Sign In"))

    def test_extract_lesson_page_data_collects_nav_player_and_notes(self) -> None:
        html = """
        <html>
          <body>
            <nav>
              <a href="/claude-code-in-action/303233">Introduction</a>
              <a href="/claude-code-in-action/303235">What is a coding assistant?</a>
            </nav>
            <h2>Introduction</h2>
            <script src="//content.jwplatform.com/players/rLVnV1aS-Akyo8gQO.js"></script>
            <script>
              window.__chatData = {
                "claudecode": "<notes><note title=\\"What is a Coding Assistant?\\">Summary</note></notes>"
              };
            </script>
          </body>
        </html>
        """

        lesson = extract_lesson_page_data(
            "https://anthropic.skilljar.com/claude-code-in-action/303233",
            html,
            "claude-code-in-action",
        )

        self.assertEqual(lesson["title"], "Introduction")
        self.assertIn("jwplayer_script", lesson["assets"])
        self.assertEqual(
            lesson["assets"]["jwplayer_script"]["url"],
            "https://content.jwplatform.com/players/rLVnV1aS-Akyo8gQO.js",
        )
        self.assertEqual(len(lesson["metadata"]["nav_lessons"]), 2)
        self.assertIn("What is a Coding Assistant?", lesson["notes_raw"])

    def test_extract_lesson_page_data_prefers_embedded_lesson_title(self) -> None:
        html = """
        <html>
          <body>
            <h2>Header Navigation</h2>
            <script>
              var skilljarCourse = {
                lesson: {
                  title: "Introduction"
                }
              };
            </script>
          </body>
        </html>
        """

        lesson = extract_lesson_page_data(
            "https://anthropic.skilljar.com/claude-code-in-action/303233",
            html,
            "claude-code-in-action",
        )

        self.assertEqual(lesson["title"], "Introduction")


if __name__ == "__main__":
    unittest.main()
