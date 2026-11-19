# Little Legend: fenced Telegram PDF delivery

`dispatch_release_pdf` verifies a sealed `ReleasePackage` and reserves a
`TELEGRAM_PDF` production effect in PostgreSQL. It commits the DISPATCHED
marker **before** calling the sender. A second invocation for the same
owner/story/PDF hash fails closed. An ambiguous Telegram exception marks the
effect UNCERTAIN; a successful Telegram message ID confirms the effect.

`AiogramPDFSender` is the real Telegram adapter and sends a private PDF
document using aiogram's `BufferedInputFile`.

The dispatcher deliberately does **not** load story data, assemble the PDF,
or autonomously retry uncertain sends. A live customer-facing handler still
needs to retrieve the current approved release from private storage, persist
its lifecycle and invoke this dispatcher. Because effect transitions and
network calls are separate, a crash after Telegram acceptance but before
CONFIRMED leaves DISPATCHED and requires manual reconciliation.

The current PDF is an editorial proof, not print-ready output.
