"""
Tkinter GUI for Omly Telemetry Export
Simple single-button interface to download and save telemetry data.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading
import sys
import logging
import traceback
from datetime import datetime

# Setup logging to both file and console
log_file = Path(__file__).parent / "omly_gui.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Add parent directory to path to import from instructions folder
sys.path.insert(0, str(Path(__file__).parent.parent / "instructions"))

from config.secrets import BASE_URL, USERNAME, PASSWORD, DEVICES
from omly_api import epoch_ms_to_ddmmyy_hhmmss
from omly_download_json import calculate_time_range, download_all_devices
from omly_convert_to_excel import save_all_files


class OmlyGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Omly Telemetry Exporter")
        self.root.geometry("700x600")
        self.root.minsize(600, 500)
        self.root.resizable(True, True)
        
        # Configuration (imported from config/secrets.py)
        self.BASE_URL = BASE_URL
        self.USERNAME = USERNAME
        self.PASSWORD = PASSWORD
        self.DEVICES = DEVICES
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="30")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="IoT Omly Telemetry Export", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 30))
        
        row = 1
        
        # Info label
        ttk.Label(main_frame, text="Will download data from both sensors:", 
                 font=('Arial', 10)).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        row += 1
        
        for device_name in self.DEVICES.keys():
            ttk.Label(main_frame, text=f"  • {device_name}", 
                     font=('Arial', 9)).grid(
                row=row, column=0, columnspan=2, sticky=tk.W, padx=20, pady=2)
            row += 1
        
        row += 1
        
        # Time Range Selection
        ttk.Label(main_frame, text="Time Range:", font=('Arial', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))
        row += 1
        
        self.time_range_var = tk.StringVar(value="7")
        time_options = [
            ("Last 24 hours", "1"),
            ("Last 7 days", "7"),
            ("Last 30 days", "30"),
            ("All Time (from first data)", "all")
        ]
        
        for label, days in time_options:
            rb = ttk.Radiobutton(main_frame, text=label, 
                               variable=self.time_range_var, value=days)
            rb.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=20, pady=2)
            row += 1
        
        row += 1
        
        # Progress label
        self.progress_label = ttk.Label(main_frame, text="", foreground="blue")
        self.progress_label.grid(row=row, column=0, columnspan=2, pady=10)
        row += 1
        
        # Download button (THE SINGLE MAIN BUTTON)
        self.download_btn = ttk.Button(main_frame, text="Download Both Sensors & Save to Excel", 
                                      command=self.download_and_save, 
                                      style='Big.TButton')
        self.download_btn.grid(row=row, column=0, columnspan=2, pady=20, ipadx=30, ipady=15)
        
        # Style for bigger button
        style = ttk.Style()
        style.configure('Big.TButton', font=('Arial', 12, 'bold'))
        
    def download_and_save(self):
        """Main function: Download telemetry and save to file"""
        # Disable button during download
        self.download_btn.config(state='disabled')
        self.progress_label.config(text="Starting download...", foreground="blue")
        
        # Run download in separate thread to prevent GUI freezing
        thread = threading.Thread(target=self._download_worker, daemon=True)
        thread.start()
    
    def _download_worker(self):
        """Worker thread for downloading data from both devices"""
        try:
            # Calculate timestamps
            time_range = self.time_range_var.get()
            start_ts, end_ts = calculate_time_range(time_range)
            
            logger.info(f"Starting download: time_range={time_range}, start_ts={start_ts}, end_ts={end_ts}")
            
            # Use daily chunks for "all time" to preserve full resolution
            use_daily_chunks = (time_range == "all")
            
            # Progress callback for download updates
            def update_progress(message):
                logger.info(message)
                self.root.after(0, lambda: self.progress_label.config(text=message))
            
            # Download data from all devices
            payloads = download_all_devices(
                base_url=self.BASE_URL,
                username=self.USERNAME,
                password=self.PASSWORD,
                devices=self.DEVICES,
                start_ts=start_ts,
                end_ts=end_ts,
                progress_callback=update_progress,
                use_daily_chunks=use_daily_chunks
            )
            
            # Update progress
            self.root.after(0, lambda: self.progress_label.config(text="Saving files..."))
            
            # Generate timestamp strings for filenames
            start_str = epoch_ms_to_ddmmyy_hhmmss(start_ts)
            end_str = epoch_ms_to_ddmmyy_hhmmss(end_ts)
            
            logger.info(f"Download complete. Saving files: {start_str} to {end_str}")
            
            # Save all data from main thread
            self.root.after(0, lambda: self._save_files(payloads, start_str, end_str))
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            logger.error(traceback.format_exc())
            self.root.after(0, lambda: self._show_error(str(e)))
            self.root.after(0, lambda: self.download_btn.config(state='normal'))
            self.root.after(0, lambda: self.progress_label.config(text=""))
    
    def _save_files(self, payloads, start_str, end_str):
        """Save Excel workbook with multiple sheets and individual JSON files"""
        try:
            csv_files, json_files = save_all_files(payloads, start_str, end_str)
            
            logger.info(f"Files saved successfully!")
            for f in csv_files:
                logger.info(f"  CSV: {f}")
            for f in json_files:
                logger.info(f"  JSON: {f}")
            
            self.progress_label.config(text=f"✓ Saved successfully!", foreground="green")
            csv_list = "\n  ".join([str(f) for f in csv_files])
            json_list = "\n  ".join([str(f) for f in json_files])
            messagebox.showinfo("Success", 
                f"Telemetry data saved:\n\nCSV files:\n  {csv_list}\n\nJSON files:\n  {json_list}")
        except ImportError as e:
            logger.error(f"Import error: {e}")
            logger.error(traceback.format_exc())
            self._show_error("openpyxl not installed. Install with: pip install openpyxl")
        except Exception as e:
            logger.error(f"Save error: {e}")
            logger.error(traceback.format_exc())
            self._show_error(f"Failed to save files: {str(e)}")
        finally:
            self.download_btn.config(state='normal')
    
    def _show_error(self, message):
        """Show error message in UI and log"""
        logger.error(f"Error displayed to user: {message}")
        self.progress_label.config(text=f"✗ {message}", foreground="red")


def main():
    logger.info("=" * 50)
    logger.info("OMLY Telemetry Exporter started")
    logger.info("=" * 50)
    root = tk.Tk()
    app = OmlyGUI(root)
    root.mainloop()
    logger.info("Application closed")


if __name__ == "__main__":
    main()
