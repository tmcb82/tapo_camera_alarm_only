from homeassistant.core import HomeAssistant

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo, Entity

from ..const import BRAND, LOGGER
from ..utils import build_device_info


class TapoEntity(Entity):
    def __init__(self, entry: dict, name_suffix: str):
        self._entry = entry
        self._enabled = False
        if self._entry["isChild"]:
            self._name = entry["camData"]["basic_info"]["device_alias"]
        else:
            self._name = entry["name"]
        self._name_suffix = name_suffix
        self._controller = entry["controller"]
        self._coordinator = entry["coordinator"]
        self._attributes = entry["camData"]["basic_info"]

    @property
    def name(self) -> str:
        return "{} {}".format(self._name, self._name_suffix)

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._attributes)

    @property
    def unique_id(self) -> str:
        id_suffix = "".join(self._name_suffix.split())
        return "{}-{}-{}".format(self._attributes["mac"], self._name, id_suffix).lower()

    @property
    def model(self):
        return self._attributes["device_model"]

    @property
    def brand(self):
        return BRAND

    async def async_added_to_hass(self) -> None:
        self._enabled = True

    async def async_will_remove_from_hass(self) -> None:
        self._enabled = False

    def updateTapo(self, camData):
        pass


class TapoButtonEntity(ButtonEntity, TapoEntity):
    def __init__(
        self,
        name_suffix,
        entry: dict,
        hass: HomeAssistant,
        icon=None,
        device_class=None,
    ):
        LOGGER.debug(f"Tapo {name_suffix} - init - start")
        self._hass = hass
        self._attr_icon = icon
        self._attr_device_class = device_class
        entry["entities"].append({"entity": self, "entry": entry})
        self.updateTapo(entry["camData"])

        TapoEntity.__init__(self, entry, name_suffix)
        ButtonEntity.__init__(self)
        LOGGER.debug(f"Tapo {name_suffix} - init - end")

    @property
    def state(self):
        return self._attr_state


class TapoBinarySensorEntity(BinarySensorEntity, TapoEntity):
    def __init__(
        self,
        name_suffix,
        entry: dict,
        hass: HomeAssistant,
        config_entry,
        icon=None,
        device_class=None,
    ):
        LOGGER.debug(f"Tapo {name_suffix} - init - start")
        self._hass = hass
        self._attr_icon = icon
        self._attr_device_class = device_class
        entry["entities"].append({"entity": self, "entry": entry})
        self.updateTapo(entry["camData"])

        TapoEntity.__init__(self, entry, name_suffix)
        BinarySensorEntity.__init__(self)
        LOGGER.debug(f"Tapo {name_suffix} - init - end")
