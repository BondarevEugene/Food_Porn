# Little Legend — Production & Delivery

## Deployment

Run `alembic upgrade head` before enabling the dedicated worker; the fulfillment schema includes migrations 0026 and 0029.
Create a **separate Railway service** from the same GitHub repository. Set its **Railway config file path** to `railway.little-legend-worker.toml`, and disable any HTTP healthcheck on that worker (it does not expose a port). Keep the existing bot/web service untouched. Deploy **one worker replica** with the same commit and environment variables. Its start command is:

```powershell
python -m app.little_legend.paid_book_worker
```

The worker does not run inside the web process. Configure the same Neon
`DATABASE_URL`, Telegram `BOT_TOKEN` / application bot configuration,
and the existing generated-illustration S3 credentials:

- `LITTLE_LEGEND_ART_S3_ENDPOINT`
- `LITTLE_LEGEND_ART_S3_BUCKET`
- `LITTLE_LEGEND_ART_S3_REGION`
- `LITTLE_LEGEND_ART_S3_ACCESS_KEY`
- `LITTLE_LEGEND_ART_S3_SECRET_KEY`

Add separate **private** finished-book storage:

- `LITTLE_LEGEND_S3_ENDPOINT`
- `LITTLE_LEGEND_S3_BUCKET`
- `LITTLE_LEGEND_S3_REGION`
- `LITTLE_LEGEND_S3_ACCESS_KEY_ID`
- `LITTLE_LEGEND_S3_SECRET_ACCESS_KEY`

The bucket must have no public access.

## Production contract

1. A verified real WayForPay approval creates one fulfillment job.
2. Worker claims a job in Neon before any external effects.
3. Approved manuscript and revision-matched, completed illustrations are
   mandatory. The existing structural PDF quality check runs.
4. PDF is stored in private S3 under a deterministic owner-scoped key.
5. Only after durable storage does the worker claim Telegram delivery.
6. Re-download is available at
   `GET /little-legend/api/order-quotes/{quote_id}/book.pdf`
   with Telegram Mini App authorization and verified entitlement.

## Operational safeguards

- **Do not** automatically retry a `processing` job after a Railway crash:
  reconcile its stored PDF first.
- **Do not** automatically retry Telegram delivery after
  `delivery_started_at`: the message may have reached the customer.
- `blocked` means the production preconditions or storage need manual
  review; do not mark it paid or ready manually.
- A paid order with missing approved art will be blocked until assets are
  approved; an operator must explicitly requeue after verifying the story.
- This is a **digital editorial PDF**, not a press-certified print edition.
- Validate Telegram file-size limits and S3 credentials in staging before
  enabling production traffic.

## Release checks

Run `ruff check .`, `pytest -q`, and `alembic upgrade head` against a
throwaway PostgreSQL database. Test signed real/sandbox callbacks, duplicate
callbacks, private download ownership, Railway restart between S3 upload
and Telegram delivery, and a deliberately incomplete manuscript.

## Финальная проверка перед продажами

1. Проверьте, что отдельный Railway worker запущен и пишет `Little Legend paid-book worker started`. Один только merge PR не создаёт сервис в Railway.
2. Установите одинаковый `DATABASE_URL` (Neon) для web и worker; секреты S3 и Telegram должны быть доступны worker.
3. Воспроизведите реальную подписанную оплату WayForPay в безопасном тестовом окружении. **Sandbox не создаёт entitlement и не запускает платное производство.** Для проверки полноценного заказа используйте согласованный небольшой реальный платёж с последующим возвратом, если это допускает ваш процесс.
4. Убедитесь, что в `little_legend_payment_receipts` ровно одна квитанция, в `little_legend_fulfillment_jobs` ровно одно задание и оно проходит `pending → processing → ready`.
5. Утверждённые текст и иллюстрации должны существовать **до** PDF-сборки. Worker не запускает AI-производство сцен.
6. Проверьте получение Telegram PDF, owner-only скачивание и повторный webhook (он не должен создать второе задание или отправку).
7. Прервите Railway worker после сохранения PDF: незавершённая доставка до claim может возобновиться; после claim Telegram автоматическая повторная отправка запрещена.

**Ограничение:** подключение нового Railway сервиса и его секретов требует действий владельца проекта в Railway; это нельзя выполнить одним GitHub PR. Полная коммерческая готовность подтверждается только после сквозного тестового заказа.
