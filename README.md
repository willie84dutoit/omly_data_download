# OMLY Data Download

Python tools to download IoT telemetry data from the OMLY platform (iot.omly.co).

## Features

- **GUI Application** (`omly_gui.py`) - Tkinter interface for manual data export
- **Headless Script** (`omly_headless.py`) - Command-line tool for scheduled downloads
- **Cloud Deployment** (`omly_cloud.py`) - Flask app for Google Cloud Run with Teams upload
- **Data Conversion** - Export to CSV and JSON formats

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `config/secrets_example.py` to `config/secrets.py` and fill in your credentials:
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
