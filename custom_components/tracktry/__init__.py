"""Support for non-delivered packages recorded in tracktry."""
from datetime import timedelta
import logging

from tracktry.tracker import Tracking
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_API_KEY, CONF_NAME, HTTP_OK
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN
from .sensor import TracktrySensor

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Information provided by Tracktry"
ATTR_TRACKINGS = "trackings"

BASE = "https://www.tracktry.com/track/"

CONF_SLUG = "slug"
CONF_TITLE = "title"
CONF_TRACKING_NUMBER = "tracking_number"

DEFAULT_NAME = "tracktry"
UPDATE_TOPIC = f"{DOMAIN}_update"

ICON = "mdi:package-variant-closed"

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)

SERVICE_ADD_TRACKING = "add_tracking"
SERVICE_REMOVE_TRACKING = "remove_tracking"

ADD_TRACKING_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TRACKING_NUMBER): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional(CONF_SLUG): cv.string,
    }
)

REMOVE_TRACKING_SERVICE_SCHEMA = vol.Schema(
    {vol.Required(CONF_SLUG): cv.string, vol.Required(CONF_TRACKING_NUMBER): cv.string}
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Tracktry sensor platform."""
    apikey = config[CONF_API_KEY]
    name = config[CONF_NAME]

    session = async_get_clientsession(hass)
    tracktry = Tracking(hass.loop, session, apikey)

    await tracktry.get_trackings()

    if not tracktry.meta or tracktry.meta["code"] != HTTP_OK:
        _LOGGER.error(
            "No tracking data found. Check API key is correct: %s", tracktry.meta
        )
        return

    instance = TracktrySensor(tracktry, name)

    async_add_entities([instance], True)

    async def handle_add_tracking(call):
        """Call when a user adds a new Tracktry tracking from Home Assistant."""
        title = call.data.get(CONF_TITLE)
        slug = call.data.get(CONF_SLUG)
        tracking_number = call.data[CONF_TRACKING_NUMBER]

        await tracktry.add_package_tracking(tracking_number, title, slug)
        async_dispatcher_send(hass, UPDATE_TOPIC)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TRACKING,
        handle_add_tracking,
        schema=ADD_TRACKING_SERVICE_SCHEMA,
    )

    async def handle_remove_tracking(call):
        """Call when a user removes an Tracktry tracking from Home Assistant."""
        slug = call.data[CONF_SLUG]
        tracking_number = call.data[CONF_TRACKING_NUMBER]

        await tracktry.remove_package_tracking(slug, tracking_number)
        async_dispatcher_send(hass, UPDATE_TOPIC)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_TRACKING,
        handle_remove_tracking,
        schema=REMOVE_TRACKING_SERVICE_SCHEMA,
    )