# Portfolio Notifications (Email + Telegram)

This feature adds configurable portfolio notifications with:
- one or more notification configs
- one or more recipients per config
- channel per config (`email` or `telegram`)
- schedule per config (`inherit` from Automatic Sync Schedule, or custom)
- message content with total portfolio, variation vs last sent, top 5 up and top 5 down movers (coins + NFTs)

## SQL Schema (logical)

```sql
CREATE TABLE notificationconfig (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  channel TEXT NOT NULL,                 -- email|telegram
  enabled BOOLEAN NOT NULL DEFAULT 1,
  schedule_mode TEXT NOT NULL DEFAULT 'inherit', -- inherit|custom
  interval_value INTEGER NOT NULL DEFAULT 1,
  interval_unit TEXT NOT NULL DEFAULT 'days',    -- minutes|hours|days|weeks
  time_of_day TEXT NOT NULL DEFAULT '00:00',
  day_of_week TEXT NOT NULL DEFAULT 'monday',
  timezone TEXT NOT NULL DEFAULT 'UTC',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE notificationrecipient (
  id INTEGER PRIMARY KEY,
  notification_id INTEGER NOT NULL,
  type TEXT NOT NULL,                    -- email|telegram_chat
  value TEXT NOT NULL,                   -- email address or telegram chat_id
  enabled BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL
);

CREATE TABLE notificationanchor (
  notification_id INTEGER PRIMARY KEY,
  last_snapshot_id INTEGER,
  last_sent_at DATETIME
);

CREATE TABLE notificationsnapshot (
  id INTEGER PRIMARY KEY,
  notification_id INTEGER NOT NULL,
  captured_at DATETIME NOT NULL,
  total_eur REAL NOT NULL,
  total_usd REAL,
  base_snapshot_id INTEGER
);

CREATE TABLE notificationassetsnapshot (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL,
  asset_type TEXT NOT NULL,              -- coin|nft
  asset_key TEXT NOT NULL,
  asset_label TEXT NOT NULL,
  value_eur REAL NOT NULL,
  value_usd REAL
);

CREATE TABLE notificationrun (
  id INTEGER PRIMARY KEY,
  notification_id INTEGER NOT NULL,
  status TEXT NOT NULL,                  -- running|sent|partial|failed
  reason TEXT NOT NULL DEFAULT 'scheduled', -- scheduled|manual
  scheduled_for DATETIME,
  started_at DATETIME NOT NULL,
  finished_at DATETIME,
  sent_recipients INTEGER NOT NULL DEFAULT 0,
  failed_recipients INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT,
  error TEXT
);
```

## Admin API

Base path: `/admin/notifications`

- `GET /` -> list notification configs with recipients, `last_sent_at`, `next_run_at`, `is_due`
- `POST /` -> create notification config
- `GET /{notification_id}` -> get one config
- `PUT /{notification_id}` -> update config
- `DELETE /{notification_id}` -> delete config and related rows
- `PUT /{notification_id}/recipients` -> replace all recipients
- `GET /{notification_id}/preview` -> build message preview without sending
- `POST /{notification_id}/run` -> execute now (manual run)

## Scheduler/Algorithm

1. Notification loop runs every 10s.
2. For each enabled config, resolve schedule:
- `inherit`: uses current Automatic Sync Schedule values
- `custom`: uses values stored in the notification config
3. If due:
- Build current portfolio snapshot from assets + NFTs
- Load `notificationanchor` base snapshot (if any)
- Compute total variation vs last successful notification
- Compute top 5 positive and top 5 negative movers by percentage (coins + NFTs)
- Render message
- Dispatch to all enabled recipients for that config
- Persist run in `notificationrun`
- Persist snapshot in `notificationsnapshot` + `notificationassetsnapshot`
- Update `notificationanchor` only if at least one recipient succeeded

## Message format

```text
Portfolio total: 125,430.00 EUR (135,901.00 USD)
Variation vs last notification: +2.14% (+2,626.00 EUR)

Top 5 up:
1. BTC +4.20%
2. ETH +3.70%
...

Top 5 down:
1. SOL -5.10%
2. NFT: BAYC #1234 -3.40%
...
```

## Required environment variables

- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, optional `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`
- Telegram: `TELEGRAM_BOT_TOKEN`

If channel credentials are missing, runs are recorded as `failed`.
