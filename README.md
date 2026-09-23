# Food_Porn

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

- One order calls the image API 16 times. `IMAGE_CONCURRENCY=2` limits parallel requests.
- Successful images are cached by model, quality, size, and prompt, so repeated dishes can avoid duplicate spend.
- Failed image requests retry three times; an unavailable item is rendered with a branded placeholder instead of breaking the whole booklet.
- The included queue runs inside one Python process. Its job state is persisted in Neon and queued/generating menus resume after restart. For several bot replicas, replace it with Redis + ARQ/Celery and a distributed lock.
- Customer photos and generated files are stored locally. A single-server MVP is fine; production replicas should use S3-compatible object storage and store object keys in Neon.
- Telegram FSM state is in memory. For horizontal scaling, switch aiogram storage to Redis.

## Privacy and safety

- The phone button accepts only the current user's own Telegram contact.
- Uploaded files are size-limited and decoded/normalized by Pillow before storage.
- `.env`, customer uploads, generated images, and keys are excluded from Git.
- Add a privacy notice, consent checkbox/message, data-retention period, and delete-my-data command before public launch.
