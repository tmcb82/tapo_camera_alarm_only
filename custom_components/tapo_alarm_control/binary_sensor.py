from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER
from .tapo.entities import TapoBinarySensorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    LOGGER.debug("Setting up binary sensors")
    entry = hass.data[DOMAIN][config_entry.entry_id]

    binarySensors = []
    if not entry["isChild"]:
        LOGGER.debug("Adding tapoCloudBinarySensor...")
        binarySensors.append(TapoCloudBinarySensor(entry, hass, config_entry))

    async_add_entities(binarySensors)


class TapoCloudBinarySensor(TapoBinarySensorEntity):
    """Reports whether the last poll of the device succeeded.

    The state comes from the regular data update, so this entity does not send
    any additional requests and never logs in on its own. A successful poll
    means the camera accepted the stored login (the cloud password, when one is
    configured) and answered. A failed poll turns the sensor off and the reason
    is available in the attributes.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Makes the update loop write the state right after a failed poll
    _tracks_poll_result = True

    def __init__(
        self, entry: dict, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        TapoBinarySensorEntity.__init__(
            self,
            "TP-Link Cloud",
            entry,
            hass,
            config_entry,
            None,
            BinarySensorDeviceClass.CONNECTIVITY,
        )

    @property
    def is_on(self) -> bool:
        return bool(self._entry.get("pollOk", False))

    @property
    def extra_state_attributes(self) -> dict:
        lastSuccess = self._entry.get("lastPollSuccess")
        return {
            "last_successful_poll": (
                dt_util.as_local(dt_util.utc_from_timestamp(lastSuccess)).isoformat()
                if lastSuccess
                else None
            ),
            "consecutive_failures": self._entry.get("pollFailures", 0),
            "last_failure_reason": self._entry.get("pollFailureReason"),
            "using_cloud_password": self._entry.get("usingCloudPassword", False),
        }

    async def async_update(self) -> None:
        await self._coordinator.async_request_refresh()
