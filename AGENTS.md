# AntropicCource

Respond to the user in Russian.
All instructions in this file must stay in English.

## Goal

This subtree is a local static mirror of Anthropic Skilljar courses.

The required end state is:
- a static HTML site;
- pages must stay as close as possible to the original Skilljar layout and structure;
- content may be translated to Russian;
- videos, subtitles, and audio may be localized;
- no invented UI, helper prose, summaries, or explanatory blocks may appear unless they also exist on the original page.

## Hard rules

1. Never invent page content.
   Allowed:
   - translated text that exists on the original Skilljar page;
   - localized media assets;
   - translated labels for original UI elements.
   Forbidden:
   - helper notes like "local page assembled from...";
   - status blurbs like "can be rebuilt later";
   - extra summaries from `notes.xml` when they are not visible on the original page;
   - extra navigation blocks, badges, or explanations not present in the original page.

2. Work lesson-by-lesson.
   Before scaling to more lessons or courses, fully finish the current lesson/page pair.

3. Use the original Skilljar page as the source of truth.
   Priority order:
   - original authenticated `lesson-page.html`;
   - visible original page text blocks like `lesson-description-content`;
   - original lesson navigation structure;
   - original media assets.
   `notes.xml` is fallback research material only and must not be rendered into the final lesson page unless the user explicitly asks for notes export.

4. "Translated" means all visible user-facing text on that page is translated.
   This includes:
   - course title;
   - lesson title;
   - left sidebar section titles;
   - left sidebar lesson titles;
   - visible lesson body text;
   - subtitles, if present;
   - audio track label/UI, if present.
   A page is not considered translated if only the shell is translated.

5. Preserve original structure 1:1 where possible.
   The final page should mirror:
   - layout;
   - visible sections;
   - sequence of blocks;
   - presence or absence of text under video;
   - images and their placement.

6. Do not add or keep stale manual edits when the generator should own the page.
   If a page is generator-owned, fix the generator or its source inputs instead of hand-editing the built HTML, unless the user asked for an emergency hotfix.

## Current implementation facts

- `docs/` contains the publishable static site.
- `Courses/<slug>/Lessons/<lesson>/Source/lesson-page.html` is the local source of truth for lesson structure.
- `Scripts/build_lesson_pages.py` must transform the original Skilljar `lesson-page.html` into the local page.
- The builder must preserve the original Skilljar DOM structure for the lesson page instead of rendering a custom shell.
- `Courses/claude-code-in-action/translations_ru.json` stores Russian labels for course title, lesson titles, and section titles.
- `Courses/<slug>/Lessons/<lesson>/Source/summary_ru.html` stores translated lesson body HTML for lessons that have visible summary text on the original page.
- `Courses/<slug>/Lessons/<lesson>/Assets/captions_ru.srt` stores translated subtitles.
- `Courses/<slug>/Lessons/<lesson>/Assets/video_ru.mp4` is the preferred per-lesson Russian dubbed video when available.
- `Courses/<slug>/Lessons/<lesson>/Assets/video_1080p.mp4` remains the original lesson video and must be preserved.
- `Scripts/build_ru_dub.py` generates Russian dubbing from `captions_ru.srt` and muxes `video_ru.mp4`.
- If a lesson has Russian dubbing, the final local page must expose both:
  - Russian dubbed media;
  - original English media.

## Builder contract

The lesson builder must do all of the following:

1. Start from `Courses/<slug>/Lessons/<lesson>/Source/lesson-page.html`.
2. Remove remote scripts and analytics, but keep the original visible page structure.
3. Keep:
   - original header;
   - original left navigation;
   - original `#lp-wrapper`, `#lesson-body`, `#lesson-main`, `#details-pane`, and `#lp-footer` structure.
4. Replace only:
   - visible text with Russian translations;
   - lesson video block with local player markup;
   - summary body with translated `summary_ru.html` when the original page has visible summary text;
   - local links for lessons that have already been built locally.
5. Do not generate a custom layout for lesson pages.
6. Do not inject helper sections or synthetic summaries.

## Local lesson CSS contract

`docs/assets/lesson-local.css` is allowed only for narrowly scoped local overrides that keep the page visually aligned with the original Skilljar lesson layout while supporting offline playback and localization.

It may be used for:
- the local video/audio/subtitle switcher overlay inside the original lesson video area;
- fixing overflow for translated summary images inside the original content column;
- sidebar lesson title wrapping when Russian text is longer than English;
- hiding the top Skilljar header on local lesson pages when the local mirror intentionally omits that header.

It must not be used to:
- replace the original page layout with a custom shell;
- restyle the whole page away from Skilljar proportions;
- inject new UI sections or explanatory panels;
- compensate for generator mistakes that should be fixed in `Scripts/build_lesson_pages.py`.

If a visual problem can be fixed by preserving the original DOM and adjusting a small local override, prefer that over rebuilding the page structure.

## Required workflow for each lesson

1. Open or inspect the original authenticated Skilljar lesson page.
2. Verify what actually exists on the original page:
   - title;
   - sidebar items;
   - video;
   - subtitles;
   - text under video or no text under video;
   - images in the summary body.
3. Export or confirm local source files for that lesson.
4. Translate only the content that is actually visible on the original page.
5. Save Russian lesson body into `Source/summary_ru.html` if the lesson has visible body text.
6. Save Russian subtitles into `Assets/captions_ru.srt` if subtitles exist.
7. Generate or attach Russian audio/video only after subtitles/text are settled.
8. Rebuild the page.
9. Compare local output against the original page before claiming success.

Before narrowing scope, explicitly classify the lesson as one of:
- video-backed lesson;
- text-only lesson;
- mixed lesson (text + downloads or text + media).

This classification must be based on the original authenticated page and the exported `lesson-page.html`, not on assumption or prior session memory.

If the lesson is text-only and has no original lesson media player, record that fact in the working context and treat \"no dubbing required\" as a verified conclusion, not as a shortcut.

If the lesson is video-backed or mixed with playable lesson media, do not allow the task to collapse into text-only translation. Media localization remains part of the same lesson task.

For the local mirrored lesson pages used in this subtree, keep these verified UI rules:
- the top Skilljar header is removed entirely;
- after removing the header, also remove all reserved top spacing so the page starts at the very top;
- left sidebar lesson titles must wrap to multiple lines when needed;
- left sidebar lesson rows must keep icon and title aligned on the same row structure while the title wraps;
- never truncate translated lesson titles with ellipsis if wrapping can preserve readability.

## Required workflow for each course

When working on a course, follow this order:

1. Confirm the original course page and lesson list from authenticated Skilljar pages.
2. Save or refresh local source data for the course page and lesson pages.
3. Translate the course page itself:
   - course title;
   - subtitle/description;
   - visible course overview text;
   - visible course stats if localized;
   - only original UI elements, no helper badges or invented notes.
4. Then work lesson-by-lesson in strict order.
5. For each lesson, fully finish translation and media localization before moving to the next lesson.
6. Do not declare the course translated until:
   - the course page is translated;
   - every intended lesson page is translated;
   - lesson media localization is complete where required;
   - navigation between local course and lesson pages works.

## Course-level anti-regression rules

- Do not skip ahead to later lessons while an earlier lesson in the current target range is still incomplete.
- Do not mix "course page complete" with "course complete".
- Do not mark a course complete because only the landing page and first lesson look correct.
- Always treat the course as a hierarchy:
  - course page;
  - lesson pages;
  - localized subtitles;
  - localized audio/video.
- Fix the pipeline on one lesson before scaling to the remaining lessons of the same course.

## Audio and video dubbing protocol

Voice gender must match the original speaker. If the original video has a male narrator, use a male Russian TTS voice (`Yuri (Enhanced)`). If the original has a female narrator, use a female Russian TTS voice (`Milena`). Do not mix genders between original and dubbed audio. The "Claude Code in Action" course has a male narrator — always use `Yuri (Enhanced)` for it.

When a lesson needs Russian dubbing, follow this order:

1. Start from the final translated subtitle file:
   - `Assets/captions_ru.srt`
2. Use subtitle timing as the timing source for dubbing.
3. Generate Russian speech per cue, then assemble a full lesson-length Russian audio track.
4. If a speech segment is longer than its cue window, compress it to fit that cue window.
5. The dubbed track must stay aligned to the original lesson duration.
6. Mux the dubbed Russian track with the original video into:
   - `Assets/video_ru.mp4`
7. Do not overwrite:
   - `Assets/video_1080p.mp4`
   - original English assets
8. The player must then expose:
   - `RU` audio from `video_ru.mp4`
   - `EN` audio from the original lesson video
9. If Russian dubbing is not finished yet, do not claim the lesson video is translated.

Required outputs for a fully localized lesson video:
- `Assets/captions_ru.srt`
- `Assets/video_ru.mp4`
- original `Assets/video_1080p.mp4`

Optional intermediate artifacts may exist temporarily, but the final lesson should rely on the outputs above.

## Definition of "lesson finished"

A lesson is finished only if all of the following are true:
- visible text matches the original page structure 1:1 but in Russian;
- no invented helper text is present;
- all visible navigation labels for that lesson page are translated;
- if the original lesson has visible body text, the translated body is present;
- if the original lesson has no visible body text, no extra body text is inserted;
- Russian subtitles exist and are wired into the player when subtitles are available;
- Russian audio exists and is wired into the player when dubbing is required for that lesson;
- English/original media is still available as an alternative in the same player;
- the page opens correctly from `file://`;
- the result has been compared against the original page, not only against generated files.
- the page has been visually verified using the Chrome DevTools MCP (navigate + screenshot), not just file inspection.

## Verification checklist

Before saying a lesson is ready, verify all of the following:
- the course title on the page is translated;
- the lesson title on the page is translated;
- the sidebar section titles are translated;
- the sidebar lesson titles are translated at least for visible/local lessons;
- no invented helper text remains;
- if the original page has no text under the video, the local page also has no text there;
- if the original page has summary text, the local page shows the translated version of that exact content;
- summary images fit inside the content column and do not overflow;
- if Russian subtitles exist, the player exposes `RU`;
- if Russian dubbed media exists, the player exposes `RU` audio;
- if the lesson is claimed fully translated, both the text and the media are translated;
- the page still opens locally via `file://`.
- the removed top header does not leave an empty top band or spacing reserve;
- long translated sidebar lesson titles wrap cleanly without clipping or broken icon alignment.
- always use Chrome DevTools MCP to open the built page and take a screenshot as the final verification step.

## Anti-regression notes

- Do not use `notes.xml` to fill lesson pages.
- Do not mark a lesson or course as translated when only partial elements are translated.
- Do not reinterpret a user request like \"translate lesson 4\" or \"translate lessons 4 and 5\" as \"translate only the visible text\".
- Do not stop after creating `summary_ru.html`, `lesson.json`, or translated UI labels and call the lesson translated.
- Do not report progress in a way that implies lesson completion when only one layer is done.
- Do not continue to later lessons while earlier target lessons still contain English visible text the user expects translated.
- Do not move to the next lesson until the current lesson is fully translated according to the definition above.
- Do not rely on browser state when verifying; inspect the generated files on disk too.
- When the user reports a mismatch, treat that as a process failure first and locate the exact source of the mismatch before making more changes.

## "Translate a lesson" means everything

When the user asks to translate a lesson, complete ALL steps as a single task without asking:
1. Translate subtitles (`captions_ru.srt`)
2. Translate summary body (`summary_ru.html`) if the original has visible body text
3. Create `lesson.json` if missing
4. Generate Russian dubbing (`video_ru.mp4`) via `build_ru_dub.py`
5. Rebuild the page via `build_lesson_pages.py`
6. Verify the result against the checklist

Do not stop after subtitles/text and ask whether to proceed with dubbing. Dubbing is not optional — it is part of translation.

Hard guard:
- Never break a \"translate lesson\" task into a text-only milestone for user-facing reporting.
- The only exception is a verified text-only lesson with no original playable media on the authenticated page.
- For that exception, the agent must explicitly verify and retain evidence that:
  - there is no original lesson video/audio player;
  - there are no original lesson subtitles to translate;
  - the final page still preserves any original non-media elements such as downloads.
- If media assets are missing locally but do exist on the original page, the lesson is still incomplete; fetch/export the assets instead of downgrading the task scope.
- If multiple lessons are requested together, each lesson may be worked on in parallel internally, but each one must still be finished end-to-end before being reported as translated.

## Parallelism with subagents

When translating a lesson, independent steps should run in parallel via subagents where possible. For example:
- Translating subtitles and translating summary body can run in parallel.
- Generating dubbing depends on subtitles being ready, so it runs after subtitles are done.
- Rebuilding the page depends on all assets being ready, so it runs last.

Use subagents to maximize throughput while respecting dependency order.

## Immediate priority

Lessons `001-introduction`, `002-what-is-a-coding-assistant`, and `003-claude-code-in-action` are fully translated (text, subtitles, dubbing with Yuri, pages built).

If a future session is asked to continue, the next priority is:
1. continue to lesson `004` and subsequent lessons of `claude-code-in-action`;
2. only after lesson quality is stable, scale to more courses.
