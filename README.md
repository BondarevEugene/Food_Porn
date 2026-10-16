# Food_Porn

## Исправления для локального коммита `55ea199`

Бот собирает ровно пять фотографий (портрет и четыре сцены) и ровно пять целей. Коллаж компонуется из всех пяти исходных снимков в мобильный 1080 × 1920 и настольный 1920 × 1080 PNG. Надписи рисуются из текста пользователя; встроенных фраз нет. Текущий `ReplicateVisionBoardRenderer` работает локально через Pillow и **не обращается к Replicate**. Результат может отличаться от фотореалистичной генерации с переносом лица.

Цифровые меню и подарки внутри Telegram оплачиваются только Telegram Stars. Portmone подключён отдельным диагностическим sandbox-контуром для администраторов и VIP: он проверяет создание ссылки, тестовую карту и серверное подтверждение, но не разблокирует и не выдаёт цифровой товар. Для двух продуктов используются разные номера тестов: `sandbox_menu_…` и `sandbox_wallpaper_…`.

Перед запуском обновлённой версии сделайте резервную копию PostgreSQL и выполните `alembic upgrade head`. Оставлены ваши миграции `226c0d2b7f58`, `42fd32b02ed1`, `ffb74d9cb65b`, и добавлена следующая миграция `20260928_0003`. Файлы `.env`, пользовательские фото и каталоги `storage` не входят в пакет исправлений.

Настройки `.env` для цифровых продаж: `MENU_PRICE_STARS` и `GIFT_PRICE_STARS`. Для диагностики Portmone нужны индивидуальные `PORTMONE_PAYEE_ID`, `PORTMONE_LOGIN`, `PORTMONE_PASSWORD`, а также `PORTMONE_TEST_MODE=true`. Для защиты Telegram админки укажите `ADMIN_TELEGRAM_IDS`. Веб админку можно отдельно включить через `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SESSION_SECRET`.

Публичные `/portmone/callback` и `/api/portmone/webhook` не подтверждают платежи по неаутентифицированному POST. VIP-пользователь проверяет тест кнопкой в Telegram; бот сам опрашивает Portmone и сверяет магазин, номер заказа, сумму, статус, экспорт и отсутствие chargeback. Результат хранится в отдельной таблице `portmone_sandbox_payments` и не меняет коммерческий статус меню или подарка.

## Тест Portmone для VIP / admin

1. Получите у Portmone индивидуальные реквизиты магазина и попросите менеджера включить тестовый режим.
2. Добавьте в Railway Variables:

```env
PORTMONE_PAYEE_ID=ваш_id
PORTMONE_LOGIN=ваш_login
PORTMONE_PASSWORD=ваш_пароль
PORTMONE_TEST_MODE=true
PORTMONE_TEST_AMOUNT_UAH=1.00
```

3. Выполните миграцию `python -m alembic upgrade head` и перезапустите приложение.
4. Создайте меню или цифровой подарок под VIP/admin-пользователем. После бесплатной VIP-выдачи появится отдельная кнопка `🧪 Тест Portmone`.
5. На странице Portmone используйте только тестовые данные:

| Сценарий | Номер карты | Срок | CVV |
|---|---|---|---|
| Успех | `4444 3333 2222 1111` | любая будущая дата | любой |
| Отказ | `4111 1111 1111 1111` | любая будущая дата | любой |

После успешной оплаты вернитесь в Telegram и нажмите `🔄 Проверить тест`. Не вводите настоящую карту, пока у магазина включён тестовый режим. Перед коммерческим запуском обязательно установите `PORTMONE_TEST_MODE=false`.

`Food_Porn` is a Python Telegram bot for `@MenuBreakfastForLove_bot`. It registers a customer, recognizes repeat visits, collects a 9 + 3 + 4 menu, accepts two customer photos, creates 16 matching food images through the OpenAI Images API, and produces two previews plus a two-sided A3 print PDF.

## Implemented flow

1. `/start` checks the Telegram user ID in Neon.
2. A new customer enters a name, shares their own phone contact, chooses Ukrainian/Russian/English, country, and city.
3. The bot stores the profile in PostgreSQL/Neon; both Telegram ID and phone are unique.
4. The customer enters 9 main dishes, 3 salads, and 4 drinks.
5. The customer uploads one cover photo and one inside-spread photo.
6. The bot shows the complete list for confirmation.
7. A background pipeline creates 16 square food/drink images in one visual style.
8. The renderer creates:
   - outside preview (back cover + front cover);
   - inside preview (12 dishes/salads + 4 drinks + payment rules + second photo);
   - two-page A3 production PDF with 3 mm bleed and CMYK artwork.
9. The files are sent to the customer and recorded in Neon.

## Project map

```text
Food_Porn/
├── app/
│   ├── main.py                         # bot lifecycle and dependency composition
│   ├── config.py                       # validated .env settings
│   ├── bot/
│   │   ├── states.py                   # aiogram FSM
│   │   ├── keyboards.py                # localized keyboards
│   │   ├── helpers.py
│   │   └── handlers/
│   │       ├── start.py                # /start, /cancel, /help
│   │       ├── registration.py         # name/phone/language/country/city
│   │       └── menu.py                 # 9+3+4, photos, review, history
│   ├── database/
│   │   ├── base.py
│   │   ├── models.py                   # customers, menus, items, files, cache
│   │   ├── repositories.py
│   │   └── session.py
│   ├── locales/messages.py             # UK/RU/EN bot and print strings
│   ├── services/
│   │   ├── storage.py                  # Telegram photo validation
│   │   ├── prompt_builder.py           # consistent food-photo prompts
│   │   └── image_generation.py         # OpenAI + retry + cache
│   ├── render/booklet.py               # A3/CMYK/bleed/previews/PDF
│   └── workers/menu_pipeline.py         # background generation pipeline
├── alembic/versions/20260917_0001_initial.py
├── scripts/demo_render.py               # render demo without external services
├── tests/
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
└── run.py
```

## 1. Create the bot token

Open `@BotFather`, select your bot, and copy the token. Never commit this value to Git.

## 2. Create the Neon database

Create a Neon project and copy its connection string. The async Python URL should look like:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/DATABASE?ssl=require
```

If Neon gives `postgresql://`, replace the scheme with `postgresql+asyncpg://`. Remove provider-specific URL parameters that `asyncpg` does not understand; keep `ssl=require`.

## 3. Create the OpenAI API key

Create an API key in the OpenAI platform and fund/enable the project that will generate images. The key belongs only in `.env` on the server. The default model is configurable:

```env
OPENAI_IMAGE_MODEL=gpt-image-1.5
OPENAI_IMAGE_SIZE=1024x1024
OPENAI_IMAGE_QUALITY=medium
```

The integration uses `AsyncOpenAI().images.generate(...)` and decodes the base64 image returned by GPT Image models. Change the model in `.env` if your account uses another supported GPT Image model.

## 4. Local launch on Windows/WSL/Linux

```bash
cd Food_Porn
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Fill `BOT_TOKEN`, `DATABASE_URL`, and `OPENAI_API_KEY`, then run:

```bash
alembic upgrade head
python run.py
```

## 5. Docker launch

`docker-compose.yml` includes local PostgreSQL for development. For this mode use the following database URL inside `.env`:

```env
DATABASE_URL=postgresql+asyncpg://food_porn:food_porn@db:5432/food_porn
```

Then run migrations and the bot:

```bash
docker compose run --rm bot alembic upgrade head
docker compose up --build
```

For production with Neon, deploy only the `bot` service and put the Neon URL in the host's secret environment settings.

## 6. Test the renderer without tokens

```bash
python -m scripts.demo_render
```

It creates synthetic sample images and writes previews/PDF under `storage/generated/999/`.

Run automated checks:

```bash
pytest -q
ruff check .
```

## Print specification

| Property | Value |
|---|---|
| Trim size | 420 × 297 mm, A3 landscape |
| Panels | 210 × 297 mm + 210 × 297 mm |
| Pages | 2: outside and inside |
| Bleed | 3 mm on each side |
| PDF page size | 426 × 303 mm |
| Raster artwork | 300 dpi |
| Print images | CMYK JPEG embedded in PDF |
| Fold | center at 210 mm of trim area |

Before commercial printing, ask the chosen print shop for its required ICC profile, ink limit, PDF/X standard, crop-mark policy, and exact folding allowance. The bot produces CMYK artwork, but a press-specific ICC conversion cannot be guessed safely.

## Operational notes

- One menu makes one image call per non-skipped dish and one batched recipe call.
- Successful images are cached by model, quality, size, and prompt, so repeated dishes can avoid duplicate spend.
- Temporary image failures retry according to `IMAGE_RETRIES`; an incomplete order is never sold as finished.
- The included queue runs inside one Python process. Its job state is persisted in Neon and queued/generating menus resume after restart. For several bot replicas, replace it with Redis + ARQ/Celery and a distributed lock.
- Customer photos and generated files are stored locally. A single-server MVP is fine; production replicas should use S3-compatible object storage and store object keys in Neon.
- Telegram FSM state is in memory. For horizontal scaling, switch aiogram storage to Redis.

## Privacy and safety

- The phone button accepts only the current user's own Telegram contact.
- Uploaded files are size-limited and decoded/normalized by Pillow before storage.
- `.env`, customer uploads, generated images, and keys are excluded from Git.
- Add a privacy notice, consent checkbox/message, data-retention period, and delete-my-data command before public launch.

## Учёт OpenAI и корректная аналитика

В CRM используются два независимых источника:

1. локальный журнал связывает каждый AI-вызов с пользователем, продуктом и заказом;
2. OpenAI Organization Costs API импортирует фактически выставленную сумму.

До первой сверки CRM показывает локальную оценку. После импорта в финансовый
итог входит фактическая сумма OpenAI, чтобы один расход не посчитался дважды.
Обычный `OPENAI_API_KEY` не даёт доступ к расходам организации. Владелец
организации должен отдельно создать Admin API key и записать его только в
Railway Variables как `OPENAI_ADMIN_API_KEY`.

```env
OPENAI_ADMIN_API_KEY=
OPENAI_PROJECT_ID=
OPENAI_COST_SYNC_ENABLED=true
OPENAI_COST_SYNC_INTERVAL_MINUTES=60
```

`OPENAI_PROJECT_ID` настоятельно рекомендуется заполнить: без него Costs API
вернёт расходы всей API-организации, а не только Food_Porn.

После настройки владелец CRM может открыть раздел **Финансы** и нажать
**«Сверить OpenAI»**. Повторная сверка безопасна: одинаковые строки счёта
не дублируются. Для Railway также нужны публичный адрес и секрет ссылок:

```env
MINIAPP_URL=https://YOUR-SERVICE.up.railway.app/miniapp
CHANNEL_LINK_SECRET=СЛУЧАЙНАЯ_СТРОКА_НЕ_КОРОЧЕ_32_БАЙТ
```

Заказы считаются по `created_at`, выручка — по `paid_at`. Черновики и бесплатные
VIP-заказы исключены из знаменателя коммерческой конверсии. В карточке расходов
отдельно видны локальная оценка, фактический счёт OpenAI и источник итоговой цифры.

## Дополнительные мессенджеры

Один HTTP-контур поддерживает официальные webhook API:

| Канал | Webhook Railway | Обязательные переменные |
|---|---|---|
| WhatsApp Cloud API | `/channels/meta/webhook` | `META_*`, `WHATSAPP_*` |
| Facebook Messenger | `/channels/meta/webhook` | `META_*`, `MESSENGER_*` |
| Instagram Messaging | `/channels/meta/webhook` | `META_*`, `INSTAGRAM_*` |
| Viber | `/channels/viber/webhook` | `VIBER_AUTH_TOKEN` |
| Slack | `/channels/slack/events` | `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN` |
| Discord | `/channels/discord/interactions` | `DISCORD_PUBLIC_KEY` |

Каждый входящий callback проверяется подписью, дедублируется в Neon и получает
ссылку в общую Mini App. Ссылка подписана `CHANNEL_LINK_SECRET`, имеет ограниченный
срок действия и не содержит секретов провайдера. Доступность адаптеров можно
проверить по `/channels/health`.

Meta, Viber, Slack и Discord не выдают токены автоматически: сначала необходимо
создать и проверить бизнес-приложения в кабинетах соответствующих платформ.
Signal и обычный iMessage намеренно не подключены через неофициальные шлюзы.

## Пакет для романтического вечера

Для каждого блюда одним пакетным текстовым запросом формируются точные продукты
на две порции, пошаговый рецепт, время, сложность, оборудование, аллергены,
замены и структурированный список покупок по отделам магазина. Данные сохраняются
не только в PDF, но и в Neon. В Mini App доступны выбор блюд на конкретный вечер,
график приготовления, чек-лист покупок и пошаговый режим готовки.

Готовый оплаченный подарок можно отправить сразу или запланировать email на
выбранную дату. Фоновый worker доставляет вложения, делает до трёх попыток и
сохраняет результат доставки в базе.

После обновления кода обязательно примените миграцию:

```powershell
python -m alembic upgrade head
python -m pytest -q
```

На Railway миграция должна выполняться один раз перед запуском новой версии.
Если отдельной release-команды нет, откройте Railway Shell и выполните:

```bash
python -m alembic upgrade head
python -m alembic current
```

Ожидаемая вершина после этого обновления: `20261016_0006`. Затем выполните
Redeploy и проверьте `/channels/health`, Mini App и раздел CRM «Финансы».

Для файлов меню, изображений и отложенных писем подключите Railway Volume к
`/app/storage` и задайте `STORAGE_ROOT=/app/storage`. Без постоянного тома файлы
могут исчезнуть при redeploy, хотя записи о заказах останутся в Neon.
