"""Constants for Tracktry."""
# Base component constants
NAME = "Tracktry"
DOMAIN = "tracktry"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.0"

ATTRIBUTION = "Data provided by Tracktry"
ISSUE_URL = (
    "https://github.com/slinkymanbyday/tracktry-homeassistant-custom-component/issues"
)

# Icons
ICON = "mdi:package"

# Platforms
SENSOR = "sensor"
PLATFORMS = [SENSOR]


# Configuration and options
# CONF_ENABLED = "enabled"
CONF_API_KEY = "key"

# Defaults
DEFAULT_NAME = DOMAIN


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
