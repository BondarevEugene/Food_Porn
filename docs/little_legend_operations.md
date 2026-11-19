# Little Legend — диагностика платных заказов

Запуск из защищённой консоли Railway с переменными проекта:

```powershell
python -m app.little_legend.fulfillment_ops --limit 100
```

Команда **только читает** Neon и возвращает JSON со статусами
`pending`, `processing`, `blocked`, `ready`, `failed`.
Она не читает детские фотографии, рукописи, токены, PDF и не отправляет
Telegram-сообщения.

## Как интерпретировать результат

- `waiting_for_worker`: проверьте отдельный Railway worker.
- `possibly_stalled_render`: задача в processing более 30 минут;
  проверьте логи, S3 и реальное состояние PDF.
- `review_story_illustrations_or_storage`: проверьте утверждение
  глав, иллюстрации, ревизии и приватное хранилище.
- `ready_for_telegram`: готовый PDF ожидает доставки.
- `telegram_delivery_requires_reconciliation`: попытка доставки уже
  зафиксирована; **не отправляйте повторно вслепую**.
- `delivered`: отправка подтверждена приложением.

Не изменяйте статусы напрямую в SQL без сверки квитанции, S3
и истории отправки Telegram. В частности, после сбоя сети Telegram
мог принять файл, хотя worker не записал `delivered_at`.

Следующий этап: защищённая административная панель с RBAC,
аудитом действий и отдельными операциями восстановления.
