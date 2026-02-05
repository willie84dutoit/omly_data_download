"""Script to get SharePoint Site ID and Drive ID for Teams integration."""
import requests
from config.secrets import MS_TENANT_ID as TENANT_ID, MS_CLIENT_ID as CLIENT_ID, MS_CLIENT_SECRET as CLIENT_SECRET

def get_access_token():
    """Get Microsoft Graph API access token."""
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Error getting token: {response.status_code}")
        print(response.text)
        return None

def list_sites(token):
    """List available SharePoint sites."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Search for sites
    url = "https://graph.microsoft.com/v1.0/sites?search=*"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        sites = response.json().get("value", [])
        print("\n=== Available SharePoint Sites ===")
        for site in sites:
            print(f"\nName: {site.get('displayName', 'N/A')}")
            print(f"  Site ID: {site.get('id')}")
            print(f"  Web URL: {site.get('webUrl', 'N/A')}")
        return sites
    else:
        print(f"Error listing sites: {response.status_code}")
        print(response.text)
        return []

def list_drives(token, site_id):
    """List drives (document libraries) for a site."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Extract the actual site ID (last part after commas)
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        drives = response.json().get("value", [])
        print(f"\n=== Drives for site ===")
        for drive in drives:
            print(f"\nName: {drive.get('name', 'N/A')}")
            print(f"  Drive ID: {drive.get('id')}")
            print(f"  Web URL: {drive.get('webUrl', 'N/A')}")
        return drives
    else:
        print(f"Error listing drives: {response.status_code}")
        print(response.text)
        return []

def list_folders(token, drive_id, folder_path="root"):
    """List folders in a drive."""
    headers = {"Authorization": f"Bearer {token}"}
    
    if folder_path == "root":
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
    else:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/children"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        items = response.json().get("value", [])
        print(f"\n=== Contents of {folder_path} ===")
        for item in items:
            item_type = "📁" if item.get("folder") else "📄"
            print(f"{item_type} {item.get('name')}")
        return items
    else:
        print(f"Error listing folders: {response.status_code}")
        print(response.text)
        return []

if __name__ == "__main__":
    print("Getting access token...")
    token = get_access_token()
    
    if token:
        print("Token obtained successfully!")
        
        # Life AgriScience site
        drive_id = "b!Qg1vpj2pP0OU9Zk9kxM2LQ9uHEGJDyVOo_wdMRM0_rdPe67ljTPTTLjMlVk0-VZI"
        
        # Rename the folder
        rename_folder(token, drive_id, "Research Projects/Absolute systems - IAQ Pilot/2. Data/sensor data", "2.2 Sensor Data")
        
        # Verify
        list_folders(token, drive_id, "Research Projects/Absolute systems - IAQ Pilot/2. Data")
    else:
        print("Failed to get access token. Check your credentials and API permissions.")
