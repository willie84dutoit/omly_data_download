"""
Headless script for Omly Telemetry Export
Designed for Google Cloud Run with Cloud Scheduler.
Downloads last 24 hours of telemetry data.

Usage:
    python omly_headless.py
"""

from pathlib import Path
import sys

# Add parent directory to path to import from instructions folder
sys.path.insert(0, str(Path(__file__).parent.parent / "instructions"))

from config.secrets import BASE_URL, USERNAME, PASSWORD, DEVICES
from omly_api import epoch_ms_to_ddmmyy_hhmmss
from omly_download_json import calculate_time_range, download_all_devices
from omly_convert_to_excel import save_all_files


def main():
    print("Downloading last 24 hours of telemetry data...")
    
    # Calculate timestamps for last 24 hours
    start_ts, end_ts = calculate_time_range("1")
    
    # Progress callback
    def progress(msg):
        print(f"  {msg}")
    
    try:
        # Download data
        payloads = download_all_devices(
            base_url=BASE_URL,
            username=USERNAME,
            password=PASSWORD,
            devices=DEVICES,
            start_ts=start_ts,
            end_ts=end_ts,
            progress_callback=progress
        )
        
        # Save files
        progress("Saving files...")
        start_str = epoch_ms_to_ddmmyy_hhmmss(start_ts)
        end_str = epoch_ms_to_ddmmyy_hhmmss(end_ts)
        
        csv_files, json_files = save_all_files(payloads, start_str, end_str)
        
        print("\n✓ Success!")
        print("  CSV files:")
        for cf in csv_files:
            print(f"    - {cf}")
        print("  JSON files:")
        for jf in json_files:
            print(f"    - {jf.name}")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
