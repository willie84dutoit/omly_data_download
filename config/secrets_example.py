# =============================================================================
# OMLY API CREDENTIALS - EXAMPLE TEMPLATE
# =============================================================================
# Copy this file to 'secrets.py' and fill in your actual credentials
# DO NOT commit secrets.py to version control

# API Configuration
BASE_URL = "https://iot.omly.co"
USERNAME = "your_email@example.com"
PASSWORD = "your_password_here"

# Device IDs - get these from the OMLY dashboard
DEVICES = {
    "Research Office": "device-uuid-here",
    "Operations Office": "device-uuid-here"
}

# Microsoft Azure AD / Teams Configuration (optional - for cloud deployment)
MS_TENANT_ID = "your-tenant-id-here"
MS_CLIENT_ID = "your-client-id-here"
MS_CLIENT_SECRET = "your-client-secret-here"
