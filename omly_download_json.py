"""
Download telemetry data from Omly devices.
Handles authentication and data retrieval for multiple devices.
Supports crash recovery by saving daily chunks to disk.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
from pathlib import Path
import sys
import json
import shutil

# Add parent directory to path to import from instructions folder
sys.path.insert(0, str(Path(__file__).parent.parent / "instructions"))

from omly_api import omly_login, OMConfig, export_telemetry_json


def get_temp_dir() -> Path:
    """Get the temp directory for storing daily chunks."""
    temp_dir = Path(__file__).parent.parent / "chunks"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir


def get_chunk_path(device_name: str, date_label: str) -> Path:
    """Get the path for a daily chunk file."""
    # Convert date_label from "12/12" to "12-12" for valid filename
    safe_label = date_label.replace("/", "-")
    # Use lowercase device name without spaces
    safe_device = device_name.lower().replace(" ", "_")
    return get_temp_dir() / f"{safe_device}_{safe_label}.json"


def save_chunk(device_name: str, date_label: str, payload: Dict[str, Any]) -> None:
    """Save a daily chunk to disk."""
    chunk_path = get_chunk_path(device_name, date_label)
    with open(chunk_path, 'w') as f:
        json.dump(payload, f)


def load_chunk(device_name: str, date_label: str) -> Dict[str, Any] | None:
    """Load a daily chunk from disk if it exists."""
    chunk_path = get_chunk_path(device_name, date_label)
    if chunk_path.exists():
        with open(chunk_path, 'r') as f:
            return json.load(f)
    return None


def cleanup_temp_files() -> None:
    """Remove all temp chunk files after successful download."""
    temp_dir = get_temp_dir()
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def calculate_time_range(time_range: str) -> tuple[int, int]:
    """
    Calculate start and end timestamps based on time range selection.
    
    Args:
        time_range: Either "all" or number of days as string ("1", "7", "30")
    
    Returns:
        Tuple of (start_ts, end_ts) in milliseconds
    """
    end_ts = int(datetime.now().timestamp() * 1000)
    
    if time_range == "all":
        # For "All Time", start from sensor installation date: Dec 12, 2025
        install_date = datetime(2025, 12, 12, 0, 0, 0)
        start_ts = int(install_date.timestamp() * 1000)
    else:
        days = int(time_range)
        start_ts = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    
    return start_ts, end_ts


def generate_daily_ranges(start_ts: int, end_ts: int) -> list[tuple[int, int, str]]:
    """
    Generate daily timestamp ranges from start to end.
    
    Returns:
        List of (day_start_ts, day_end_ts, date_label) tuples
    """
    ranges = []
    start_dt = datetime.fromtimestamp(start_ts / 1000)
    end_dt = datetime.fromtimestamp(end_ts / 1000)
    
    # Start from midnight of start date
    current = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0)
    
    while current < end_dt:
        day_start = int(current.timestamp() * 1000)
        next_day = current + timedelta(days=1)
        day_end = int(next_day.timestamp() * 1000) - 1  # End of current day
        
        # Cap at actual end time
        if day_end > end_ts:
            day_end = end_ts
        
        date_label = current.strftime("%d/%m")
        ranges.append((day_start, day_end, date_label))
        current = next_day
    
    return ranges


def merge_payloads(existing: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge new telemetry data into existing payload.
    Payload structure: {'telemetry': {'sensor': [...]}, 'keys': [...]}
    """
    if not existing:
        return new_data
    
    # Merge telemetry data
    existing_telemetry = existing.get('telemetry', {})
    new_telemetry = new_data.get('telemetry', {})
    
    for sensor, values in new_telemetry.items():
        if sensor in existing_telemetry:
            existing_telemetry[sensor].extend(values)
        else:
            existing_telemetry[sensor] = values
    
    existing['telemetry'] = existing_telemetry
    
    # Merge keys (union)
    existing_keys = set(existing.get('keys', []))
    new_keys = set(new_data.get('keys', []))
    existing['keys'] = list(existing_keys | new_keys)
    
    return existing


def download_all_devices(
    base_url: str,
    username: str,
    password: str,
    devices: Dict[str, str],
    start_ts: int,
    end_ts: int,
    progress_callback=None,
    use_daily_chunks: bool = False
) -> Dict[str, Any]:
    """
    Download telemetry data from all specified devices.
    
    Args:
        base_url: Omly API base URL
        username: Omly username
        password: Omly password
        devices: Dict mapping device names to entity IDs
        start_ts: Start timestamp in milliseconds
        end_ts: End timestamp in milliseconds
        progress_callback: Optional callback function(message: str)
        use_daily_chunks: If True, download day by day to preserve resolution
    
    Returns:
        Dict mapping device names to their telemetry payloads
    """
    # Login once
    if progress_callback:
        progress_callback("Logging in...")
    
    token = omly_login(base_url, username, password)
    cfg = OMConfig(base_url=base_url, token=token)
    
    # Download data from all devices
    payloads = {}
    
    if use_daily_chunks:
        # Generate daily ranges for full resolution
        daily_ranges = generate_daily_ranges(start_ts, end_ts)
        total_days = len(daily_ranges)
        
        for device_name, entity_id in devices.items():
            device_payload = {}
            
            for day_num, (day_start, day_end, date_label) in enumerate(daily_ranges, 1):
                # Check if we have a cached chunk (crash recovery)
                cached = load_chunk(device_name, date_label)
                if cached:
                    if progress_callback:
                        progress_callback(f"{device_name}: {date_label} ({day_num}/{total_days}) [cached]")
                    device_payload = merge_payloads(device_payload, cached)
                    continue
                
                if progress_callback:
                    progress_callback(f"{device_name}: {date_label} ({day_num}/{total_days})")
                
                day_payload = export_telemetry_json(
                    cfg=cfg,
                    entity_type="DEVICE",
                    entity_id=entity_id,
                    start_ts=day_start,
                    end_ts=day_end,
                    keys=None,
                    aggregated=False,
                    limit=100000
                )
                
                # Save chunk to disk for crash recovery
                save_chunk(device_name, date_label, day_payload)
                device_payload = merge_payloads(device_payload, day_payload)
            
            payloads[device_name] = device_payload
        
        # Note: Chunks are kept in /chunks folder for reference
    else:
        # Single request for shorter time ranges
        for device_name, entity_id in devices.items():
            if progress_callback:
                progress_callback(f"Downloading {device_name}...")
            
            payload = export_telemetry_json(
                cfg=cfg,
                entity_type="DEVICE",
                entity_id=entity_id,
                start_ts=start_ts,
                end_ts=end_ts,
                keys=None,
                aggregated=False,
                limit=100000
            )
            payloads[device_name] = payload
    
    return payloads
