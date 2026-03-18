# AntropicCource

Машинный перевод курсов Anthropic в виде статического сайта.

Сайт доступен здесь:

[https://unger1984.github.io/AntropicCourcesRU/index.html](https://unger1984.github.io/AntropicCourcesRU/index.html)

## Что сейчас готово

Сейчас полностью переведён только первый курс. Остальные курсы будут добавляться позже по мере перевода и сборки.

## Хранение медиа

После полной сборки и проверки курса в `docs/` дублирующиеся publish-ассеты можно удалять из `Courses/`, чтобы не хранить тяжёлые видео дважды.

Для этого есть скрипт:

```bash
python3 Scripts/prune_published_media.py --course-slug claude-code-in-action --dry-run
python3 Scripts/prune_published_media.py --course-slug claude-code-in-action
```

Скрипт удаляет только те бинарные файлы, которые уже существуют в `docs/`. Исходники перевода и структуры урока в `Courses/` не трогаются.

## Помощь проекту

Если хотите помочь с переводом остальных курсов, это будет очень полезно.
