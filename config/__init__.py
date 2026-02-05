# Configuration package
from .secrets import (
    BASE_URL, USERNAME, PASSWORD, DEVICES,
    MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET
)

__all__ = [
    'BASE_URL', 'USERNAME', 'PASSWORD', 'DEVICES',
    'MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET'
]
