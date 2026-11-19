# Little Legend: legacy AI budget recovery

This is an **operator-only** maintenance operation. It does not call AI
providers, retry work, charge customers, or settle ambiguous charges.

## Before applying

1. Deploy all Alembic migrations and ensure the Little Legend budget tables exist.
2. Stop new Little Legend job creation and provider dispatch while reconciling
   legacy stories. The recovery function locks story rows but external code
   must also respect those locks.
3. Back up Neon PostgreSQL.
4. Check the configured ceiling
   `LITTLE_LEGEND_BOOK_AI_BUDGET_MICRO_USD` (default 5,000,000 = $5).
5. Run the preview:

```powershell
python -m app.little_legend.recover_budgets_cli --limit 100
```

For a single owner:

```powershell
python -m app.little_legend.recover_budgets_cli --owner-id 123 --limit 100
```

Only after inspecting the dry-run result, apply a bounded batch:

```powershell
python -m app.little_legend.recover_budgets_cli --apply --limit 100
```

## Safety rules

- Existing budgets are not reset or increased.
- Stories with any writer/illustration jobs, production effects, or budget
  reservations are excluded; a new zero balance would misrepresent history.
- Every inserted budget belongs to the original story owner.
- Dry-run is the default; `--apply` is required for changes.
- Batches are bounded and the oldest story rows are locked.
- `created` in dry-run means *eligible*, not persisted.
- If `skipped_financial_history` is nonzero, reconcile those books
  individually using provider evidence. Do not force-create empty budgets.
- This tool does not backfill missing provider receipts.

The read-only `audit_book_budgets(owner_id=..., limit=...)` service compares
stored held/spent totals against reservation rows and reports discrepancies.
It never adjusts balances automatically.
