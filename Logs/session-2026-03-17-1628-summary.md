# Session Summary 2026-03-17 16:28

## What is already on disk

- The public Anthropic Academy catalog was fetched and stored in `Catalog/root.html`.
- `State/manifest.json` contains 13 discovered course entries.
- Course descriptions were written into `Courses/<slug>/course-description.en.md`.
- PDF attachments were downloaded for:
  - `ai-fluency-for-educators`
  - `ai-fluency-for-students`
  - `ai-fluency-framework-foundations`
  - `teaching-ai-fluency`
- `claude-code-in-action` has a full preview export on disk:
  - `playback.json`
  - `jwplayer_script.js`
  - `manifest_hls.m3u8`
  - `video_180p.mp4`
  - `video_270p.mp4`
  - `video_406p.mp4`
  - `video_720p.mp4`
  - `video_1080p.mp4`
  - `audio_audio.m4a`
  - caption tracks in `en`, `fr`, `de`, `ja`, `ko`, `pt`, `es`
  - `captions_ru.srt`
  - `poster_image.jpg`
  - `thumbnails_vtt.vtt`
  - `course-description.ru.md`

## Important caveat

The long-running command `python3 export_anthropic_courses.py --refresh-details` successfully processed `claude-code-in-action` but did not finish cleanly within the session window. Because of that, some on-disk progress existed before it was fully persisted back into `manifest.json`.

The `claude-code-in-action` entry was manually reconciled into `State/manifest.json`. Other courses may also have partial on-disk progress if later log lines appear in the future.

## Next session

1. Read `State/manifest.json`.
2. Read the latest `Logs/session-*.log`.
3. Compare on-disk files under `Courses/` against manifest entries before re-running the exporter.
4. Resume with targeted course runs instead of one full `--refresh-details` pass if another long hang appears.

## Additional findings after stabilization

- `manifest.json` now supports `derived_files` and was reconciled from disk with `--sync-from-disk-only`.
- The following public courses are now marked `translated` in the manifest:
  - `claude-code-in-action`
  - `introduction-to-model-context-protocol`
  - `model-context-protocol-advanced-topics`
  - `claude-in-amazon-bedrock`
  - `claude-with-the-anthropic-api`
  - `claude-with-google-vertex`
- Two `previewId` route hypotheses were tested for AI Fluency courses and returned `404`:
  - `https://anthropic.skilljar.com/ai-fluency-framework-foundations/preview/68809`
  - `https://anthropic.skilljar.com/preview/77953`

This means `previewId` exists in page data, but the obvious public URL patterns do not currently resolve to downloadable preview pages.
