# Food_Porn → OmniFactory CRM: Bot Swarm heartbeat

The existing OmniFactory CRM signed ingest endpoint is reused. This is an
**outbound, opt-in heartbeat only**; no Telegram token, client records or
payment details are sent. No remote management commands are enabled.

1. In OmniFactory CRM, create or locate the existing `food_porn` bot record.
2. Register its **actual Telegram Bot ID** using the owner-only Fleet API.
   This is the numeric Bot ID, **not** a Telegram chat ID or API token.
3. Set the **same secret** in CRM `BOT_INGEST_SECRETS` (key `food_porn`) and
   Food_Porn's Railway service secret `OMNIFACTORY_CRM_INGEST_SECRET`.
4. Configure Food_Porn Railway service variables:

   - `OMNIFACTORY_CRM_URL=https://<your-crm-host>`
   - `OMNIFACTORY_CRM_BOT_KEY=food_porn`
   - `OMNIFACTORY_CRM_INGEST_SECRET=<shared-secret-minimum-24-chars>`
   - `OMNIFACTORY_CRM_HEARTBEAT_SECONDS=60` (optional, 30–3600)
   - `OMNIFACTORY_RUNTIME_VERSION=<release-version>` (optional)

5. Deploy after CRM Bot Swarm v1 and v2 migrations are installed, then check
   `GET /api/fleet/overview` while authenticated as CRM admin.

Expected: instance transitions from `unconnected` to `running`; if no
heartbeat arrives for >5 minutes, the overview reports `offline`. A signed
`bot.error` event reports `degraded`. Signed event IDs are unique per send.

**Roll back:** remove the three required Food_Porn variables and redeploy.
The agent is disabled by default and never affects Telegram polling if CRM
becomes unavailable.

**Do not enable until** OmniFactory CRM has a reachable HTTPS endpoint and
its ingest secret is configured. This PR does not configure production Railway,
and it does not claim that Food_Porn is already connected.
