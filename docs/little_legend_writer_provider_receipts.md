# Little Legend writer: provider usage settlement

The one-shot writer remains operator-controlled and disabled unless
`LL_WRITER_ENABLED=true` and the existing consent gates are configured.

The OpenAI adapter now captures the provider response ID and token usage.
To enable calculated settlement, configure **both** rates for the selected
`LL_WRITER_MODEL`:

```text
LL_WRITER_INPUT_USD_PER_MILLION=<verified current input token price>
LL_WRITER_OUTPUT_USD_PER_MILLION=<verified current output token price>
```

The values are **USD per 1,000,000 tokens**, not micro-USD. The worker
converts provider-reported token usage to integer micro-USD and rounds up.
Verify the model-specific prices and any cached/reasoning token billing rules
against the actual provider invoice before enabling these settings. The
calculation currently treats all reported prompt tokens at the configured
input rate and all completion tokens at the output rate; if your billing
differs, leave these rates unset and reconcile the charge manually.

On successful chapter generation the manuscript, queue completion, budget
reservation settlement and effect confirmation commit in one database
transaction. If rates, response ID or usage are missing, the chapter still
commits, but the held amount remains for reconciliation; no estimated charge
is invented.

This change does not start background workers, provision payment credentials,
or make provider calls automatically. Illustration receipt integration remains
a separate task.
