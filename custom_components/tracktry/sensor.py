"""Support for non-delivered packages recorded in tracktry."""
from datetime import timedelta, datetime
import logging

from tracktry.tracker import Tracking
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_API_KEY, CONF_NAME, HTTP_OK
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import Throttle


from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Information provided by Tracktry"
ATTR_TRACKINGS = "trackings"
ATTR_COURIERS = "couriers"

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

        if not tracktry.couriers or slug in [c["code"] for c in tracktry.couriers]:

            await tracktry.add_package_tracking(tracking_number, title, slug)
            async_dispatcher_send(hass, UPDATE_TOPIC)
        else:
            _LOGGER.error(f"slug '{slug}' not in allowed list of couriers")

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


class TracktrySensor(Entity):
    """Representation of a Tracktry sensor."""

    def __init__(self, tracktry, name):
        """Initialize the sensor."""
        self._attributes = {}
        self._name = name
        self._state = None
        self.tracktry = tracktry
        self._couriers_update = datetime.fromisoformat("2000-12-04")

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "packages"

    @property
    def device_state_attributes(self):
        """Return attributes for the sensor."""
        return self._attributes

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return ICON

    async def async_update_carriers(self):
        await self.tracktry.get_couriers()
        self._couriers_update = datetime.now()

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                UPDATE_TOPIC, self._force_update
            )
        )

    async def _force_update(self):
        """Force update of data."""
        await self.async_update(no_throttle=True)
        self.async_write_ha_state()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self, **kwargs):
        """Get the latest data from the tracktry API."""
        await self.tracktry.get_trackings()

        if self._couriers_update < datetime.now() - timedelta(days=7):
            await self.async_update_carriers()
        couriers = [c["code"] for c in self.tracktry.couriers]

        if not self.tracktry.meta:
            _LOGGER.error("Unknown errors when querying")
            return
        if self.tracktry.meta["code"] != HTTP_OK:
            _LOGGER.error("Errors when querying tracktry. %s", str(self.tracktry.meta))
            return

        status_to_ignore = {"delivered"}
        status_counts = {}
        trackings = []
        not_delivered_count = 0
        for track in self.tracktry.trackings["items"]:
            status = track["status"].lower()
            name = track["tracking_number"] if not track["title"] else track["title"]

            status_counts[status] = status_counts.get(status, 0) + 1
            current_tracking = {
                "name": name,
                "tracking_number": track["tracking_number"],
                "slug": track["carrier_code"],
                "link": f'{BASE}{track["tracking_number"]}/{track["carrier_code"]}',
                "last_update": track["updated_at"],
                "status": status,
                "status_description": None,
                "location": None,
            }

            try:
                current_tracking["location"] = track["origin_info"]["trackinfo"][0][
                    "Details"
                ]
                current_tracking["status_description"] = track["origin_info"][
                    "trackinfo"
                ][0]["StatusDescription"]
                current_tracking["location"] = track["origin_info"]["trackinfo"][0][
                    "Details"
                ]
            except KeyError:
                pass

            trackings.append(current_tracking)

            if status not in status_to_ignore:
                not_delivered_count += 1
            else:
                _LOGGER.debug("Ignoring %s as it has status: %s", name, status)

        self._attributes = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            **status_counts,
            ATTR_TRACKINGS: trackings,
            ATTR_COURIERS: couriers,
        }

        self._state = not_delivered_count

