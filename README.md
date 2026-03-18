# AntropicCource

Локальный архив публично доступного контента Anthropic Academy с сохранёнными оригиналами, логами, состоянием выгрузки и русскими переводами.

## Структура

- `Catalog/` — сырые HTML-снимки каталога и страниц курсов
- `Courses/` — выгруженные курсы, preview-видео, субтитры и переводы
- `Logs/` — логи сессий, ошибки и session summary
- `State/manifest.json` — основной реестр состояния
- `Scripts/` — локальные утилиты экспорта и синхронизации

## Возобновление

Следующая сессия должна читать:

1. `State/manifest.json`
2. последний `Logs/session-*.log`
3. `Logs/session-2026-03-17-1628-summary.md`

## Авторизация

Если курс или урок упирается в логин, экспортер помечает объект как `blocked_auth` и пишет URL в логи, не прерывая остальную выгрузку.

## Курсы

### Переведённые

1. `Claude Code in Action` — статус `translated`
   Контент курса: [course.ru.md](Courses/claude-code-in-action/course.ru.md)
   Русское описание: [course-description.ru.md](Courses/claude-code-in-action/course-description.ru.md)
   Русские субтитры: [captions_ru.srt](Courses/claude-code-in-action/Assets/captions_ru.srt)
   Оригинальные субтитры: [captions_en.srt](Courses/claude-code-in-action/Assets/captions_en.srt)
   Видео preview: [video_1080p.mp4](Courses/claude-code-in-action/Assets/video_1080p.mp4)

2. `Claude with Amazon Bedrock` — статус `translated`
   Русское описание: [course-description.ru.md](Courses/claude-in-amazon-bedrock/course-description.ru.md)
   Видео preview: [video_1080p.mp4](Courses/claude-in-amazon-bedrock/Assets/video_1080p.mp4)

3. `Claude with Google Cloud's Vertex AI` — статус `translated`
   Русское описание: [course-description.ru.md](Courses/claude-with-google-vertex/course-description.ru.md)
   Видео preview: [video_1080p.mp4](Courses/claude-with-google-vertex/Assets/video_1080p.mp4)

4. `Building with the Claude API` — статус `translated`
   Русское описание: [course-description.ru.md](Courses/claude-with-the-anthropic-api/course-description.ru.md)
   Видео preview: [video_1080p.mp4](Courses/claude-with-the-anthropic-api/Assets/video_1080p.mp4)

5. `Introduction to Model Context Protocol` — статус `translated`
   Русское описание: [course-description.ru.md](Courses/introduction-to-model-context-protocol/course-description.ru.md)
   Русские субтитры: [captions_ru.srt](Courses/introduction-to-model-context-protocol/Assets/captions_ru.srt)
   Оригинальные субтитры: [captions_en.srt](Courses/introduction-to-model-context-protocol/Assets/captions_en.srt)
   Видео preview: [video_1080p.mp4](Courses/introduction-to-model-context-protocol/Assets/video_1080p.mp4)

6. `Model Context Protocol: Advanced Topics` — статус `translated`
   Русское описание: [course-description.ru.md](Courses/model-context-protocol-advanced-topics/course-description.ru.md)
   Русские субтитры: [captions_ru.srt](Courses/model-context-protocol-advanced-topics/Assets/captions_ru.srt)
   Оригинальные субтитры: [captions_en.srt](Courses/model-context-protocol-advanced-topics/Assets/captions_en.srt)
   Видео preview: [video_1080p.mp4](Courses/model-context-protocol-advanced-topics/Assets/video_1080p.mp4)

### Скачанные, но ещё не переведённые полностью

1. `AI Fluency for educators` — статус `downloaded`
   Описание: [course-description.en.md](Courses/ai-fluency-for-educators/course-description.en.md)

2. `AI Fluency for nonprofits` — статус `downloaded`
   Описание: [course-description.en.md](Courses/ai-fluency-for-nonprofits/course-description.en.md)

3. `AI Fluency for students` — статус `downloaded`
   Описание: [course-description.en.md](Courses/ai-fluency-for-students/course-description.en.md)

4. `AI Fluency: Framework & Foundations` — статус `downloaded`
   Описание: [course-description.en.md](Courses/ai-fluency-framework-foundations/course-description.en.md)

5. `Claude 101` — статус `downloaded`
   Описание: [course-description.en.md](Courses/claude-101/course-description.en.md)

6. `Introduction to agent skills` — статус `downloaded`
   Описание: [course-description.en.md](Courses/introduction-to-agent-skills/course-description.en.md)

7. `Teaching AI Fluency` — статус `downloaded`
   Описание: [course-description.en.md](Courses/teaching-ai-fluency/course-description.en.md)
