# Little Legend — private media retention operations

This PR adds a manual, **opt-in** retention cycle, not an active production scheduler.

## Transaction boundaries

1. Queue expired records using PostgreSQL row locks, then commit.
2. Delete queued private objects using the existing guarded deletion worker, then commit.
3. Query aggregate health counts and the age of the oldest pending deletion.

Call `run_retention_cycle(session_factory, store)` only from a trusted
operator-controlled job after configuring a private bucket, IAM restrictions,
timeouts, monitoring and a vetted privacy policy. Never expose this function
as an unauthenticated HTTP endpoint.

## Owner deletion requests

`queue_story_deletion(session, owner_id=..., story_id=...)` queues matching
assets for deletion. It does not erase bytes by itself. Callers must commit
and ensure the deletion worker subsequently processes the queue.

## Known blockers

- No automatic scheduler, no retry cooldown timestamp and no dead-letter policy.
- Existing expiry queue can requeue failed rows immediately after expiry.
  The new `requeue_failed_deletions` deliberately does nothing until a
  timestamped retry/backoff migration exists.
- Object-store calls are synchronous and occur while DB row locks are held.
  Set strict network timeouts and keep batches small before production use.
- No upload endpoint or parent consent activation.
- Successful S3 DeleteObject does not by itself prove removal of object
  versions, replicas or provider backups; review bucket versioning and lifecycle.
- Metrics are aggregate-only and should be alerted on, not shown to customers
  as proof of erasure.

## Next implementation

Add `last_deletion_attempt_at` and `next_deletion_attempt_at` in Alembic,
exponential backoff, bounded attempts, version-aware deletion, durable consent
records, withdrawal-to-queue integration, and an operational scheduler.

## 2026-11-19: операторская команда и мониторинг

Новый однократный запуск:

```powershell
python -m app.little_legend.retention_operator --dry-run --fail-on-alert
```

Для физического удаления оператор отдельно задаёт переменные
`LITTLE_LEGEND_RETENTION_EXECUTE=YES` и `LITTLE_LEGEND_PRIVATE_BUCKET`,
настраивает стандартные boto3 IAM credentials и запускает:

```powershell
python -m app.little_legend.retention_operator --execute --batch-size 25 --fail-on-alert
```

Результат — JSON с агрегированными счётчиками, без детских фото, object keys,
owner IDs и story IDs. При `--fail-on-alert`: 0 — OK, 2 — backlog,
3 — физическое удаление не удалось или повторы исчерпаны.

**Railway:** после ручной проверки тестового S3/Neon создать отдельный Cron
Service с указанной командой и интервалом, например `*/30 * * * *`.
Переменную разрешения устанавливать **только** в cron-сервисе.
Подключить уведомления по ненулевому exit code через инфраструктурный
мониторинг. Не запускать второй scheduler в FastAPI или Telegram polling.

Этот пакет не включает автозапуск, Telegram-уведомления, upload фотографий,
распознавание лиц или передачу изображений AI-провайдеру. Перед запуском
проверить IAM, отсутствие versioning, сетевые таймауты, миграции и политику
родительского согласия. Успешный S3 DeleteObject сам по себе не доказывает
удаление всех реплик и резервных копий.

## Retention Operations v2: координация и bounded drain

CLI поддерживает `--max-cycles 4` (диапазон 1..20) в дополнение к
`--batch-size 25`. За один операторский запуск обрабатывается не более
`batch-size × max-cycles` удалений. Если прогресса нет, цикл останавливается
досрочно; при оставшейся работе JSON содержит `more_work_possible=true`.

При `--execute` используется PostgreSQL advisory lock, удерживаемый одним
соединением в течение всей операции. Параллельный экземпляр не удаляет
файлы, возвращает `drain.status=already_running` и с
`--fail-on-alert` завершает процесс кодом **4**. SQLite намеренно
не поддерживается для этой операции. Не отключайте блокировку в production.

**Важное ограничение:** advisory lock защищает только новый операторский
интерфейс. Старые внешние вызовы worker без этого lock могут продолжать
работать независимо; перед подключением cron убедитесь, что других
планировщиков нет. Права S3, сетевые таймауты, алерты и контроль повторов
должны быть проверены на тестовом окружении до включения расписания.
