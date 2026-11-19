# Little Legend — доставка после рестарта Railway

Worker сначала выбирает готовые PDF (`ready`, `asset_key` заполнен,
`delivery_started_at IS NULL`) и только затем новые оплаченные заказы.

## Безопасность

- Сначала фиксируется попытка отправки в Neon; затем вызывается Telegram.
- После сбоя до фиксации попытки готовый PDF будет отправлен worker.
- После фиксации попытки автоматический повтор **запрещён**: Telegram мог
  принять документ до потери соединения.
- Если `delivered_at` пустой при заполненном `delivery_started_at`,
  требуется ручная сверка. Клиент может получить PDF через защищённый
  endpoint `/little-legend/api/order-quotes/{quote_id}/book.pdf`.
- Повторное получение файла не вызывает платный AI и не меняет квитанцию.

## Проверки

```powershell
python -m ruff check app src tests alembic main.py
python -m pytest -q
```

В staging проверьте перезапуск Railway до Telegram send и после фиксации
`delivery_started_at`. Никаких автоматических повторов при
неоднозначном результате доставки.
