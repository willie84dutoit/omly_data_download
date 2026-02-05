"""
Convert and save Omly telemetry data to Excel and JSON formats.
Handles file organization and data formatting.
"""

import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


def save_all_files(
    payloads: Dict[str, Any],
    start_str: str,
    end_str: str
) -> tuple[List[Path], List[Path]]:
    """
    Save telemetry data to individual CSV files and JSON files per device.
    
    Args:
        payloads: Dict mapping device names to their telemetry payloads
        start_str: Start timestamp in ddmmyy_hhmmss format
        end_str: End timestamp in ddmmyy_hhmmss format
    
    Returns:
        Tuple of (list_of_csv_paths, list_of_json_paths)
    """
    # Extract date parts from ddmmyy_hhmmss format (e.g., "150125_120000" -> "15-12-25")
    start_date = f"{start_str[0:2]}-{start_str[2:4]}-{start_str[4:6]}"
    end_date = f"{end_str[0:2]}-{end_str[2:4]}-{end_str[4:6]}"
    date_range_folder = f"{start_date}_{end_date}"
    
    # Create directory paths with date range
    csv_dir = Path("csv") / date_range_folder
    json_dir = Path("json") / date_range_folder
    
    csv_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = []
    csv_files = []
    
    # Process each device
    for device_name, payload in payloads.items():
        # Create short name for files (e.g., "Research Office" -> "research")
        short_name = device_name.split()[0].lower()
        
        # Save individual JSON file
        json_filename = f"{short_name}_{date_range_folder}.json"
        json_path = json_dir / json_filename
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        json_files.append(json_path)
        
        # Save individual CSV file
        csv_filename = f"{short_name}_{date_range_folder}.csv"
        csv_path = csv_dir / csv_filename
        write_csv(payload, str(csv_path))
        csv_files.append(csv_path)
    
    return csv_files, json_files


def write_excel_sheet(worksheet, payload: Dict[str, Any]) -> None:
    """
    Write telemetry data to an Excel worksheet.
    
    Args:
        worksheet: openpyxl worksheet object
        payload: Telemetry payload dict with 'telemetry' and 'keys'
    """
    telemetry = payload.get('telemetry', {})
    keys = payload.get('keys', [])
    
    if not telemetry or not keys:
        worksheet.append(['No telemetry data available'])
        return
    
    # Build a dictionary of timestamp -> {key: value}
    data_by_timestamp = {}
    
    for key in keys:
        if key in telemetry:
            for entry in telemetry[key]:
                ts = entry['ts']
                value = entry['value']
                if ts not in data_by_timestamp:
                    data_by_timestamp[ts] = {}
                data_by_timestamp[ts][key] = value
    
    # Sort by timestamp
    sorted_timestamps = sorted(data_by_timestamp.keys())
    
    # Write header row
    header = ['timestamp', 'datetime'] + keys
    worksheet.append(header)
    
    # Write data rows
    for ts in sorted_timestamps:
        # Convert timestamp to readable datetime
        dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
        row = [ts, dt]
        
        # Add values for each key
        for key in keys:
            row.append(data_by_timestamp[ts].get(key, ''))
        
        worksheet.append(row)


def write_csv(payload: Dict[str, Any], file_path: str) -> None:
    """
    Convert telemetry JSON to CSV format.
    
    Args:
        payload: Telemetry payload dict with 'telemetry' and 'keys'
        file_path: Output CSV file path
    
    Raises:
        ValueError: If no telemetry data to export
    """
    telemetry = payload.get('telemetry', {})
    keys = payload.get('keys', [])
    
    if not telemetry or not keys:
        raise ValueError("No telemetry data to export")
    
    # Build a dictionary of timestamp -> {key: value}
    data_by_timestamp = {}
    
    for key in keys:
        if key in telemetry:
            for entry in telemetry[key]:
                ts = entry['ts']
                value = entry['value']
                if ts not in data_by_timestamp:
                    data_by_timestamp[ts] = {}
                data_by_timestamp[ts][key] = value
    
    # Sort by timestamp
    sorted_timestamps = sorted(data_by_timestamp.keys())
    
    # Write CSV
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header row
        header = ['timestamp', 'datetime'] + keys
        writer.writerow(header)
        
        # Data rows
        for ts in sorted_timestamps:
            # Convert timestamp to readable datetime
            dt = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            row = [ts, dt]
            
            # Add values for each key
            for key in keys:
                row.append(data_by_timestamp[ts].get(key, ''))
            
            writer.writerow(row)
