"""Support for non-delivered packages recorded in tracktry."""
from datetime import timedelta, datetime
import logging

from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, HTTP_OK
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Information provided by Tracktry"
ATTR_TRACKINGS = "trackings"
ATTR_COURIERS = "couriers"

BASE = "https://www.tracktry.com/track/"

UPDATE_TOPIC = f"{DOMAIN}_update"

ICON = "mdi:package-variant-closed"

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)

class TracktrySensor(Entity):
    """Representation of a Tracktry sensor."""

    def __init__(self, tracktry, name):
        """Initialize the sensor."""
        self._attributes = {}
        self._name = name
        self._state = None
        self.tracktry = tracktry
        self._couriers_update = datetime.fromisoformat("1970/01/01 00:00:00")

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
            await self._update_carriers()
        couriers = self.tracktry.couriers

        if not self.tracktry.meta:
            _LOGGER.error("Unknown errors when querying")
            return
        if self.tracktry.meta["code"] != HTTP_OK:
            _LOGGER.error(
                "Errors when querying tracktry. %s", str(self.tracktry.meta)
            )
            return

        status_to_ignore = {"delivered"}
        status_counts = {}
        trackings = []
        not_delivered_count = 0

        for track in self.tracktry.trackings["trackings"]:
            status = track["tag"].lower()
            name = (
                track["tracking_number"] if track["title"] is None else track["title"]
            )
            last_checkpoint = (
                "Shipment pending"
                if track["tag"] == "Pending"
                else track["checkpoints"][-1]
            )
            status_counts[status] = status_counts.get(status, 0) + 1
            trackings.append(
                {
                    "name": name,
                    "tracking_number": track["tracking_number"],
                    "slug": track["slug"],
                    "link": f"{BASE}{track['tracking_number']}/{track['slug']}",
                    "last_update": track["updated_at"],
                    "expected_delivery": track["expected_delivery"],
                    "status": track["tag"],
                    "last_checkpoint": last_checkpoint,
                }
            )

            if status not in status_to_ignore:
                not_delivered_count += 1
            else:
                _LOGGER.debug("Ignoring %s as it has status: %s", name, status)

        self._attributes = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            **status_counts,
            ATTR_TRACKINGS: trackings,
            ATTR_COURIERS: couriers
        }

        self._state = not_delivered_count
