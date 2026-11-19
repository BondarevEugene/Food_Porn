# Little Legend — контракт выбора палитры

## Для клиентского интерфейса

Публичный `GET /little-legend/api/palettes` возвращает 3 группы
(`light`, `vivid`, `dark`) по 5 палитр. У каждой палитры есть
`id`, русское название и пять точных HEX-цветов. Источник цветов
один — PDF-рендерер, поэтому интерфейс не должен дублировать палитры
в шаблонах или Telegram-обработчиках.

Рекомендуемый сценарий Telegram: сначала три категории,
затем пять вариантов с понятными названиями, затем подтверждение
и сохранение `StoryDraft.palette` через существующий API истории.
Не показывать 15 кнопок одновременно.

Сохранённое поле `palette` уже используется paid worker при
генерации PDF. Если поле отсутствует, действует `lavender`.

**Этот PR добавляет каталог API, но не реализует Telegram-кнопки
и не меняет текущие пользовательские экраны.**

## Контроль качества

```powershell
python -m pytest -q tests/test_little_legend_palette_catalog.py tests/test_little_legend_story_palette.py
python -m pytest -q --tb=short -rs
python -m ruff check .
```
