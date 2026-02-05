"""
Headless script for Omly Telemetry Export - Google Cloud Version
Designed for Google Cloud Run with Cloud Scheduler.
Downloads last 24 hours of telemetry data and uploads to Microsoft Teams Shared Folder.

SELF-CONTAINED - does not require any other local modules.
"""

import os
import io
import json
import csv
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import sys
import requests

# Import defaults from config (used when env vars not set)
from config.secrets import (
    BASE_URL as CONFIG_BASE_URL,
    USERNAME as CONFIG_USERNAME,
    PASSWORD as CONFIG_PASSWORD,
    DEVICES as CONFIG_DEVICES
)

# =============================================================================
# CONFIGURATION - Environment variables with config fallback
# =============================================================================

BASE_URL = os.environ.get("OMLY_BASE_URL", CONFIG_BASE_URL)
USERNAME = os.environ.get("OMLY_USERNAME", CONFIG_USERNAME)
PASSWORD = os.environ.get("OMLY_PASSWORD", CONFIG_PASSWORD)
DEVICES = CONFIG_DEVICES

# Microsoft Teams / SharePoint Configuration
MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "YOUR_TENANT_ID")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "YOUR_CLIENT_ID")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
MS_SITE_ID = os.environ.get("MS_SITE_ID", "YOUR_SITE_ID")
MS_DRIVE_ID = os.environ.get("MS_DRIVE_ID", "YOUR_DRIVE_ID")
MS_FOLDER_PATH = os.environ.get("MS_FOLDER_PATH", "OMLY_Telemetry")


# =============================================================================
# OMLY API FUNCTIONS
# =============================================================================

@dataclass
class OMConfig:
    base_url: str
    token: str


def _join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def omly_login(base_url: str, username: str, password: str, timeout: int = 30) -> str:
    """Returns JWT token string."""
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


def epoch_ms_to_ddmmyy_hhmmss(epoch_ms: int) -> str:
    """Convert epoch milliseconds to ddmmyy_hhmmss format."""
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
        interval = ((interval + MIN - 1) // MIN) * MIN

    return int(interval)


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
    """Export telemetry data from Omly."""
    device = omly_get(cfg, f"/api/device/{entity_id}")
    device_name = device.get("name", entity_id)
    device_label = device.get("label")

    if keys is None:
        keys = omly_get(
            cfg,
            f"/api/plugins/telemetry/{entity_type}/{entity_id}/keys/timeseries",
            params={"startTs": start_ts, "endTs": end_ts},
        )
        if not keys:
            return {
                "meta": {
                    "entityType": entity_type, "entityId": entity_id,
                    "deviceName": device_name, "deviceLabel": device_label,
                    "startTs": start_ts, "endTs": end_ts,
                    "aggregated": aggregated, "agg": agg if aggregated else None,
                    "interval": None, "exportedAtTs": int(time.time() * 1000),
                },
                "keys": [],
                "telemetry": {},
            }

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
            "entityType": entity_type, "entityId": entity_id,
            "deviceName": device_name, "deviceLabel": device_label,
            "startTs": start_ts, "endTs": end_ts,
            "aggregated": aggregated, "agg": agg if aggregated else None,
            "interval": interval, "exportedAtTs": int(time.time() * 1000),
        },
        "keys": keys,
        "telemetry": telemetry,
    }


# =============================================================================
# DOWNLOAD FUNCTIONS
# =============================================================================

def calculate_time_range(time_range: str) -> tuple:
    """Calculate start and end timestamps for last 24 hours."""
    end_ts = int(datetime.now().timestamp() * 1000)
    
    if time_range == "all":
        install_date = datetime(2025, 12, 12, 0, 0, 0)
        start_ts = int(install_date.timestamp() * 1000)
    else:
        days = int(time_range)
        start_ts = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    
    return start_ts, end_ts


def download_all_devices(start_ts: int, end_ts: int, progress_callback=None) -> Dict[str, Any]:
    """Download telemetry data from all devices."""
    if progress_callback:
        progress_callback("Logging in to Omly...")
    
    token = omly_login(BASE_URL, USERNAME, PASSWORD)
    cfg = OMConfig(base_url=BASE_URL, token=token)
    
    payloads = {}
    for device_name, entity_id in DEVICES.items():
        if progress_callback:
            progress_callback(f"Downloading {device_name}...")
        
        payload = export_telemetry_json(
            cfg=cfg,
            entity_type="DEVICE",
            entity_id=entity_id,
            start_ts=start_ts,
            end_ts=end_ts,
            keys=None,
            aggregated=True,
            agg="AVG",
            limit=10000
        )
        payloads[device_name] = payload
    
    return payloads


# =============================================================================
# MICROSOFT TEAMS UPLOAD FUNCTIONS
# =============================================================================

def get_ms_access_token() -> str:
    """Get Microsoft Graph API access token."""
    url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"
    
    data = {
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


def ensure_folder_exists(token: str, folder_path: str):
    """Create folder structure if it doesn't exist."""
    headers = {"Authorization": f"Bearer {token}"}
    
    url = f"https://graph.microsoft.com/v1.0/drives/{MS_DRIVE_ID}/root:/{folder_path}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return
    
    parts = folder_path.split("/")
    current_path = ""
    
    for part in parts:
        parent_path = current_path if current_path else "root"
        current_path = f"{current_path}/{part}" if current_path else part
        
        check_url = f"https://graph.microsoft.com/v1.0/drives/{MS_DRIVE_ID}/root:/{current_path}"
        check_response = requests.get(check_url, headers=headers)
        
        if check_response.status_code != 200:
            if parent_path == "root":
                create_url = f"https://graph.microsoft.com/v1.0/drives/{MS_DRIVE_ID}/root/children"
            else:
                create_url = f"https://graph.microsoft.com/v1.0/drives/{MS_DRIVE_ID}/root:/{parent_path}:/children"
            
            folder_data = {
                "name": part,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail"
            }
            
            create_response = requests.post(create_url, headers=headers, json=folder_data)
            if create_response.status_code not in [200, 201, 409]:
                create_response.raise_for_status()
            print(f"  Created folder: {current_path}")


def upload_to_teams(token: str, folder_path: str, filename: str, data: bytes, content_type: str):
    """Upload file to Microsoft Teams / SharePoint."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type
    }
    
    url = f"https://graph.microsoft.com/v1.0/drives/{MS_DRIVE_ID}/root:/{folder_path}/{filename}:/content"
    
    response = requests.put(url, headers=headers, data=data)
    response.raise_for_status()
    
    result = response.json()
    print(f"  Uploaded: {filename}")
    return result.get("webUrl", "")


def payload_to_csv_bytes(payload: dict) -> bytes:
    """Convert telemetry payload to CSV bytes."""
    telemetry = payload.get('telemetry', {})
    keys = payload.get('keys', [])
    
    if not telemetry or not keys:
        return b"No telemetry data available\n"
    
    data_by_timestamp = {}
    for key in keys:
        if key in telemetry:
            for entry in telemetry[key]:
                ts = entry['ts']
                value = entry['value']
                if ts not in data_by_timestamp:
                    data_by_timestamp[ts] = {}
                data_by_timestamp[ts][key] = value
    
    sorted_timestamps = sorted(data_by_timestamp.keys())
    
    # Write to string buffer
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    header = ['timestamp'] + keys
    writer.writerow(header)
    
    # Data rows
    for ts in sorted_timestamps:
        dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
        row = [dt]
        for key in keys:
            row.append(data_by_timestamp[ts].get(key, ''))
        writer.writerow(row)
    
    return output.getvalue().encode('utf-8')


def save_to_teams(payloads: dict, start_str: str, end_str: str):
    """Save telemetry data to Microsoft Teams Shared Folder."""
    token = get_ms_access_token()
    today = datetime.now().strftime('%Y%m%d')
    
    json_folder = f"{MS_FOLDER_PATH}/json/{today}"
    csv_folder = f"{MS_FOLDER_PATH}/csv/{today}"
    
    ensure_folder_exists(token, json_folder)
    ensure_folder_exists(token, csv_folder)
    
    uploaded_files = []
    
    # Upload individual JSON files and individual CSV files per device
    for device_name, payload in payloads.items():
        device_safe_name = device_name.replace(" ", "_")
        
        # Upload JSON
        json_filename = f"{device_safe_name}_telemetry_{start_str}_to_{end_str}.json"
        json_data = json.dumps(payload, indent=2).encode('utf-8')
        link = upload_to_teams(token, json_folder, json_filename, json_data, 'application/json')
        uploaded_files.append({"name": json_filename, "link": link})
        
        # Upload individual CSV per device
        csv_filename = f"{device_safe_name}_telemetry_{start_str}_to_{end_str}.csv"
        csv_data = payload_to_csv_bytes(payload)
        link = upload_to_teams(token, csv_folder, csv_filename, csv_data, 'text/csv')
        uploaded_files.append({"name": csv_filename, "link": link})
    
    return uploaded_files


# =============================================================================
# MAIN EXPORT FUNCTION
# =============================================================================

def run_export():
    """Main export function."""
    print("Starting Omly telemetry export...")
    print(f"  Teams Folder: {MS_FOLDER_PATH}")
    
    start_ts, end_ts = calculate_time_range("1")  # Last 24 hours
    
    def progress(msg):
        print(f"  {msg}")
    
    payloads = download_all_devices(start_ts, end_ts, progress_callback=progress)
    
    progress("Uploading to Microsoft Teams...")
    start_str = epoch_ms_to_ddmmyy_hhmmss(start_ts)
    end_str = epoch_ms_to_ddmmyy_hhmmss(end_ts)
    
    uploaded_files = save_to_teams(payloads, start_str, end_str)
    
    print("\n✓ Success!")
    print(f"  Uploaded {len(uploaded_files)} files to Teams")
    
    return uploaded_files


# =============================================================================
# FLASK APP FOR CLOUD RUN
# =============================================================================

try:
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route("/", methods=["GET", "POST"])
    def handle_request():
        """HTTP endpoint for Cloud Scheduler."""
        try:
            files = run_export()
            return jsonify({"status": "success", "files": files}), 200
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "healthy"}), 200

except ImportError:
    app = None


def main():
    """Run locally or start Flask server."""
    if os.environ.get("PORT"):
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    else:
        try:
            run_export()
            return 0
        except Exception as e:
            print(f"\n✗ Error: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
