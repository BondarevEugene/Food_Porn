# Food_Porn architecture

```mermaid
flowchart TD
    U[Telegram customer] --> B[aiogram handlers]
    B --> N[(Neon PostgreSQL)]
    B --> S[Validated photo storage]
    B --> Q[Menu pipeline]
    Q --> O[OpenAI Images API]
    O --> C[Image cache]
    Q --> R[A3 booklet renderer]
    S --> R
    N --> R
    R --> P[Two previews + print PDF]
    P --> U
    P --> N
```

## State sequence

```mermaid
stateDiagram-v2
    [*] --> Registration
    Registration --> MainMenu
    MainMenu --> CollectItems: New menu
    CollectItems --> CoverPhoto: 3 + 3 + 3 + 3 complete
    CoverPhoto --> SpreadPhoto
    SpreadPhoto --> Review
    Review --> CollectItems: Re-enter items
    Review --> CoverPhoto: Replace photos
    Review --> Queued: Confirm
    Queued --> Generating
    Generating --> Rendering
    Rendering --> Complete
    Generating --> Failed
    Failed --> Queued: Retry missing images
    Rendering --> Failed
```

The worker processes image requests sequentially. A cache hit performs no API call. A quota-exhausted response opens a five-minute local circuit breaker and stops the current menu immediately; rendering starts only after every non-skipped item has a valid image file.

## Deployment boundary

The MVP is intentionally one process: Telegram polling and one durable-state pipeline. Database state makes restarts recoverable. When volume requires multiple replicas, split the worker into its own deployment, move media to object storage, and use a broker-backed queue with idempotency keyed by `menu_id`.
