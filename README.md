# OMLY Data Download

Python tools to download IoT telemetry data from the OMLY platform (iot.omly.co).

## Features

- **GUI Application** (`omly_gui.py`) - Tkinter interface for manual data export
- **Headless Script** (`omly_headless.py`) - Command-line tool for scheduled downloads
- **Cloud Deployment** (`omly_cloud.py`) - Flask app for Google Cloud Run with Teams upload
- **Data Conversion** - Export to CSV and JSON formats

## Prerequisites

**Important**: This application requires `omly_api.py` to be placed in a parallel `instructions/` folder:

```
parent_folder/
├── instructions/
│   └── omly_api.py          # Required API module (not included in repo)
└── omly_data_download/      # This repository
    ├── config/
    ├── omly_gui.py
    └── ...
```

### OMLY API Module (`omly_api.py`)

The `omly_api.py` module provides core functionality for interacting with the OMLY IoT platform. It includes:

**Authentication:**
- `omly_login(base_url, username, password)` - Returns JWT token for API access
- Username/password authentication only (JWT via `/api/auth/login`)

**Data Export:**
- `export_telemetry_json(cfg, entity_type, entity_id, start_ts, end_ts, ...)` - Export telemetry data
  - `entity_type`: Usually "DEVICE"
  - `entity_id`: Device UUID
  - `start_ts`, `end_ts`: Timestamps in epoch milliseconds
  - `keys`: Optional list of telemetry keys (auto-discovered if None)
  - `aggregated`: Enable data aggregation (default True)
  - `agg`: Aggregation method - "AVG", "MIN", "MAX", "SUM", "COUNT"
  - Returns JSON payload with metadata and telemetry data

**Helper Functions:**
- `epoch_ms_to_ddmmyy_hhmmss(epoch_ms)` - Convert timestamps to ddmmyy_hhmmss format
- `compute_interval_ms(start_ts, end_ts)` - Calculate optimal aggregation interval

**API Endpoints Used:**
- `/api/auth/login` - Authentication
- `/api/device/{id}` - Device information
- `/api/plugins/telemetry/{entityType}/{id}/keys/timeseries` - Available telemetry keys
- `/api/plugins/telemetry/{entityType}/{id}/values/timeseries` - Telemetry data

Contact the repository owner for access to `omly_api.py`.

### Complete `omly_api.py` Source Code

```python
"""
Omly telemetry export to JSON.

Auth mode:
- Username/password -> JWT via /api/auth/login (ONLY)

Time selection:
- startTs, endTs in epoch ms

Exports:
- keys in window via /api/plugins/telemetry/{entityType}/{id}/keys/timeseries
- values via /api/plugins/telemetry/{entityType}/{id}/values/timeseries

Outputs a JSON file with metadata + telemetry payload (includes device label).
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


# ----------------------------
# Config / helpers
# ----------------------------

@dataclass
class OMConfig:
    base_url: str
    token: str


def _join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def omly_login(base_url: str, username: str, password: str, timeout: int = 30) -> str:
    """
    Returns JWT token string.
    """
    url = _join_url(base_url, "/api/auth/login")
    r = requests.post(url, json={"username": username, "password": password}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Login failed: HTTP {r.status_code} - {r.text}")
    data = r.json()
    token = data.get("token")
    if not token:
        raise RuntimeError(f"Login response missing token: {data}")
    return token


def omly_get(cfg: OMConfig, path: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    url = _join_url(cfg.base_url, path)
    headers = {"X-Authorization": f"Bearer {cfg.token}"}
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"GET {path} failed: HTTP {r.status_code} - {r.text}")
    return r.json()


def sanitize_filename(s: str) -> str:
    out = []
    for ch in (s or ""):
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out) or "device"


def epoch_ms_to_ddmmyy_hhmmss(epoch_ms: int) -> str:
    """
    Convert epoch milliseconds to ddmmyy_hhmmss format.
    Example: 1766497475177 -> 230126_143755
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000)
    return dt.strftime('%d%m%y_%H%M%S')


def compute_interval_ms(start_ts: int, end_ts: int, max_intervals: int = 700) -> int:
    
    range_ms = end_ts - start_ts
    MIN = 60_000
    HOUR = 60 * MIN
    DAY = 24 * HOUR

    if range_ms <= DAY:
        interval = 5 * MIN
    elif range_ms <= 7 * DAY:
        interval = 15 * MIN
    elif range_ms <= 30 * DAY:
        interval = 30 * MIN
    else:
        interval = 1 * HOUR

    buckets = (range_ms + interval - 1) // interval
    if buckets > max_intervals:
        interval = (range_ms + max_intervals - 1) // max_intervals
        interval = ((interval + MIN - 1) // MIN) * MIN  # round up to whole minute

    return int(interval)


def _extract_device_label(device_obj: Dict[str, Any]) -> Optional[str]:

    if not isinstance(device_obj, dict):
        return None
    label = device_obj.get("label")
    if label:
        return str(label)

    add = device_obj.get("additionalInfo")
    if isinstance(add, dict):
        # Some Omly UI uses "description" as a human label
        desc = add.get("description") or add.get("label")
        if desc:
            return str(desc)

    return None


# ----------------------------
# Main export logic
# ----------------------------

def export_telemetry_json(
    cfg: OMConfig,
    entity_type: str,
    entity_id: str,
    start_ts: int,
    end_ts: int,
    keys: Optional[List[str]] = None,
    aggregated: bool = True,
    agg: str = "AVG",
    limit: int = 10000,
) -> Dict[str, Any]:

    # Device name + label (for output naming/meta)
    device = omly_get(cfg, f"/api/device/{entity_id}")
    device_name = device.get("name", entity_id)
    device_label = _extract_device_label(device)

    # Keys
    if keys is None:
        keys = omly_get(
            cfg,
            f"/api/plugins/telemetry/{entity_type}/{entity_id}/keys/timeseries",
            params={"startTs": start_ts, "endTs": end_ts},
        )
        if not keys:
            return {
                "meta": {
                    "entityType": entity_type,
                    "entityId": entity_id,
                    "deviceName": device_name,
                    "deviceLabel": device_label,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "aggregated": aggregated,
                    "agg": agg if aggregated else None,
                    "interval": None,
                    "exportedAtTs": int(time.time() * 1000),
                },
                "keys": [],
                "telemetry": {},
            }

    # Values
    params: Dict[str, Any] = {
        "keys": ",".join(keys),
        "startTs": start_ts,
        "endTs": end_ts,
        "orderBy": "ASC",
        "limit": limit,
    }

    interval = None
    if aggregated:
        interval = compute_interval_ms(start_ts, end_ts)
        params.update({"agg": agg, "interval": interval})

    telemetry = omly_get(
        cfg,
        f"/api/plugins/telemetry/{entity_type}/{entity_id}/values/timeseries",
        params=params,
    )

    return {
        "meta": {
            "entityType": entity_type,
            "entityId": entity_id,
            "deviceName": device_name,
            "deviceLabel": device_label,
            "startTs": start_ts,
            "endTs": end_ts,
            "aggregated": aggregated,
            "agg": agg if aggregated else None,
            "interval": interval,
            "exportedAtTs": int(time.time() * 1000),
        },
        "keys": keys,
        "telemetry": telemetry,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export Omly telemetry to JSON.")
    p.add_argument("--base-url", required=True, help="e.g. https://omly.example.com")
    p.add_argument("--entity-type", default="DEVICE", help="Usually DEVICE")
    p.add_argument("--entity-id", required=True, help="Device UUID")

    # Inputs you said you will pass in:
    p.add_argument("--startTs", type=int, required=True, help="Start timestamp (ms since epoch)")
    p.add_argument("--endTs", type=int, required=True, help="End timestamp (ms since epoch)")

    # Auth: username/password ONLY
    p.add_argument("--username", required=True, help="Omly username/email")
    p.add_argument("--password", required=True, help="Omly password")

    # Keys (optional)
    p.add_argument("--keys", help="Comma-separated keys. If omitted, keys are discovered from Omly in the window.")

    # Aggregation
    p.add_argument("--raw", action="store_true", help="Export raw points (no aggregation)")
    p.add_argument("--agg", default="AVG", help="Aggregation: AVG, MIN, MAX, SUM, COUNT (Omly dependent)")
    p.add_argument("--limit", type=int, default=10000, help="Omly limit param")

    # Output
    p.add_argument("--out", default="omly_telemetry.json", help="Output JSON file path")

    args = p.parse_args()

    if args.endTs < args.startTs:
        print("Error: endTs must be >= startTs", file=sys.stderr)
        return 2

    token = omly_login(args.base_url, args.username, args.password)
    cfg = OMConfig(base_url=args.base_url, token=token)

    keys_list = None
    if args.keys:
        keys_list = [k.strip() for k in args.keys.split(",") if k.strip()]

    payload = export_telemetry_json(
        cfg=cfg,
        entity_type=args.entity_type,
        entity_id=args.entity_id,
        start_ts=args.startTs,
        end_ts=args.endTs,
        keys=keys_list,
        aggregated=not args.raw,
        agg=args.agg,
        limit=args.limit,
    )

    out_path = Path(args.out)
    if out_path.is_dir():
        dn = sanitize_filename(payload["meta"]["deviceName"])
        start_str = epoch_ms_to_ddmmyy_hhmmss(args.startTs)
        end_str = epoch_ms_to_ddmmyy_hhmmss(args.endTs)
        out_path = out_path / f"{dn}_telemetry_{start_str}_to_{end_str}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Setup

1. Clone the repository
2. **Place `omly_api.py` in `../instructions/` relative to this folder**
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `config/secrets_example.py` to `config/secrets.py` and fill in your credentials:
   ```python
   BASE_URL = "https://iot.omly.co"
   USERNAME = "your_email@example.com"
   PASSWORD = "your_password"
   DEVICES = {
       "Device Name": "device-uuid-here"
   }
   ```

## Usage

### GUI Application
```bash
python omly_gui.py
```
Select time range and click "Download Both Sensors & Save to Excel".

### Headless (CLI)
```bash
python omly_headless.py
```
Downloads last 24 hours of data automatically.

### Cloud Deployment
Deploy to Google Cloud Run using the included `Dockerfile`. Set environment variables:
- `OMLY_BASE_URL`
- `OMLY_USERNAME`
- `OMLY_PASSWORD`
- `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` (for Teams upload)

## Output

Data is saved to:
- `csv/` - CSV files per device
- `json/` - JSON files with full telemetry payload

## License

GPL-3.0 - See [LICENSE](LICENSE) for details.
