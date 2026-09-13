# TG Archive Standalone Dashboard

Lightweight single-file monitoring dashboard for TG Archive workers.

## Features

- Real-time status monitoring (messages, media, bytes)
- Per-channel deduplicated upload tracking
- Transfer rate calculation (15s window)
- Stall detection (900s threshold)
- Event log tail (last 80 entries per channel)
- Disk usage monitoring
- Process PID tracking via systemd

## Usage

### Quick Start

```bash
python3 backend/dashboard/standalone_dashboard.py \
  --port 6186 \
  --status-dir /home/hermes \
  --log-root /data \
  --channels '[
    {"id": "gv", "name": "GV黄金时代", "tag": "archive", "unit": "tg-archive-batch-gv.service"},
    {"id": "danji", "name": "Beard Project", "tag": "completed", "unit": "tg-archive-batch-danji.service"}
  ]'
```

### Systemd Service

```ini
[Unit]
Description=TG Archive Dashboard
After=network.target

[Service]
Type=simple
User=hermes
WorkingDirectory=/home/hermes/tg-archive-repo
ExecStart=/usr/bin/python3 backend/dashboard/standalone_dashboard.py \
  --port 6186 \
  --status-dir /home/hermes \
  --log-root /data \
  --channels '[{"id":"gv","name":"GV","tag":"archive","unit":"tg-archive-batch-gv.service"}]'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Reverse Proxy (nginx)

```nginx
location ^~ /tg/ {
    proxy_pass http://127.0.0.1:6186/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## API

### `GET /api/status`

Returns real-time status for all channels:

```json
{
  "ts": 1726201234.5,
  "disk": {
    "path": "/home/hermes",
    "pct": 76.8,
    "used": 123456789,
    "total": 160000000000
  },
  "channels": [
    {
      "id": "gv",
      "name": "GV黄金时代",
      "tag": "archive",
      "state": "running",
      "phase_icon": "📤",
      "phase_label": "上传中",
      "messages_done": 603,
      "messages_total": 765,
      "media_uploaded": 587,
      "media_total": 756,
      "bytes_uploaded": 497234567890,
      "media_total_bytes": 698765432100,
      "run_transfer_bytes": 244123456789,
      "rate_bps": 5242880.0,
      "current_file": "DNJ153.mp4",
      "current_bytes": 123456789,
      "current_total": 1890123456,
      "pid": 885688,
      "stalled": false,
      "updated_age": 12,
      "updated_at_epoch": 1726201222.5
    }
  ],
  "events": {
    "gv": [
      {"t": "2026-09-13T05:18:42+08:00", "ts": 0, "m": "Uploaded DNJ152.mp4 → 123云盘"}
    ]
  }
}
```

### `GET /healthz`

Health check endpoint, returns `200 ok`.

## File Structure

```
backend/dashboard/
├── standalone_dashboard.py   # HTTP server + status aggregation
├── dashboard.html            # Single-page frontend
└── README.md                 # This file
```

## Status Files

The dashboard reads JSON status files written by TG Archive workers:

- **Status**: `{status_dir}/tg-archive-status-{channel_id}.json`
- **Events**: `{log_root}/tg-archive-{channel_id}/log.json`

Status schema:
```json
{
  "state": "running",
  "transfer_phase": "上传到123云盘",
  "messages_done": 603,
  "messages_total": 765,
  "bytes_uploaded": 497234567890,
  "run_transfer_bytes": 244123456789,
  "updated_at": "2026-09-13T05:18:34+08:00"
}
```

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | 6186 | HTTP listen port |
| `--status-dir` | `/home/hermes` | Directory containing status JSON files |
| `--log-root` | `/data` | Root directory for event logs |
| `--channels` | *required* | JSON array of channel configs |

Channel config schema:
```json
{
  "id": "gv",              // Unique channel ID (used in filenames)
  "name": "GV黄金时代",     // Display name
  "tag": "archive",        // Category tag (archive/completed/failed)
  "unit": "tg-archive-batch-gv.service"  // systemd unit name for PID tracking
}
```

## Metrics

- **bytes_uploaded**: Deduplicated real storage (excludes re-uploads)
- **run_transfer_bytes**: Total flow counter (resets on restart)
- **media_total_bytes**: Declared total from message metadata
- **rate_bps**: Transfer rate (bytes/sec, 15s window)
- **stalled**: True if running but no update for 900s

## Troubleshooting

**Dashboard shows "数据缺失"**
- Check status file exists: `ls -la /home/hermes/tg-archive-status-*.json`
- Verify worker is writing status: `tail -f /home/hermes/tg-archive-status-gv.json`

**Transfer rate is 0**
- Rate requires 15s of updates to stabilize
- Check `run_transfer_bytes` is incrementing in status file

**PID is null**
- Verify systemd unit name matches: `systemctl show -p MainPID tg-archive-batch-gv.service`
- Check service is running: `systemctl status tg-archive-batch-gv.service`
