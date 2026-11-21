from homeassistant.core import HomeAssistant

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import STATE_UNAVAILABLE

from .const import DOMAIN, LOGGER
from .tapo.entities import TapoButtonEntity
from .utils import check_and_create, result_has_error


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    LOGGER.debug("Setting up buttons")
    entry = hass.data[DOMAIN][config_entry.entry_id]

    async def setupEntities(entry):
        buttons = []
        if not entry["isChild"]:
            tapoStartManualAlarmButton = await check_and_create(
                entry, hass, TapoStartManualAlarmButton, "getAlarm", config_entry
            )
            if tapoStartManualAlarmButton:
                LOGGER.debug("Adding tapoStartManualAlarmButton...")
                buttons.append(tapoStartManualAlarmButton)

            tapoStopManualAlarmButton = await check_and_create(
                entry, hass, TapoStopManualAlarmButton, "getAlarm", config_entry
            )
            if tapoStopManualAlarmButton:
                LOGGER.debug("Adding tapoStopManualAlarmButton...")
                buttons.append(tapoStopManualAlarmButton)

        return buttons

    buttons = await setupEntities(entry)

    for childDevice in entry["childDevices"]:
        buttons.extend(await setupEntities(childDevice))

    async_add_entities(buttons)


class TapoStartManualAlarmButton(TapoButtonEntity):
    def __init__(self, entry: dict, hass: HomeAssistant, config_entry):
        self.sirenType = None
        TapoButtonEntity.__init__(
            self, "Manual Alarm Start", entry, hass, "mdi:alarm-light-outline"
        )

    async def async_press(self) -> None:
        result = False
        result2 = False
        try:
            result = await self._hass.async_add_executor_job(
                self._controller.startManualAlarm,
            )
        except Exception as e:
            LOGGER.debug(e)

        try:
            result2 = await self._hass.async_add_executor_job(
                self._controller.setSirenStatus, True
            )
        except Exception as e:
            LOGGER.debug(e)

        if result_has_error(result) and result_has_error(result2):
            if self.sirenType is not None:
                try:
                    result3 = await self._hass.async_add_executor_job(
                        self._controller.testUsrDefAudio, self.sirenType, True
                    )
                    if result_has_error(result3):
                        raise Exception("Camera does not support triggering the siren.")
                except Exception:
                    raise Exception("Camera does not support triggering the siren.")
            else:
                raise Exception("Camera does not support triggering the siren.")

    def updateTapo(self, camData):
        if not camData or camData["privacy_mode"] == "on":
            self.camData = STATE_UNAVAILABLE
        else:
            if (
                "alarm_config" in camData
                and camData["alarm_config"]
                and "siren_type" in camData["alarm_config"]
                and camData["alarm_config"]["siren_type"]
            ):
                self.sirenType = camData["alarm_config"]["siren_type"]


class TapoStopManualAlarmButton(TapoButtonEntity):
    def __init__(self, entry: dict, hass: HomeAssistant, config_entry):
        self.sirenType = None
        TapoButtonEntity.__init__(
            self,
            "Manual Alarm Stop",
            entry,
            hass,
            "mdi:alarm-light-off-outline",
        )

    async def async_press(self) -> None:
        result = False
        result2 = False
        try:
            result = await self._hass.async_add_executor_job(
                self._controller.stopManualAlarm,
            )
        except Exception as e:
            LOGGER.debug(e)

        try:
            result2 = await self._hass.async_add_executor_job(
                self._controller.setSirenStatus, False
            )
        except Exception as e:
            LOGGER.debug(e)

        if result_has_error(result) and result_has_error(result2):
            if self.sirenType is not None:
                try:
                    result3 = await self._hass.async_add_executor_job(
                        self._controller.testUsrDefAudio, self.sirenType, False
                    )
                    if result_has_error(result3):
                        self._attr_available = False
                        raise Exception("Camera does not support triggering the siren.")
                except Exception:
                    raise Exception("Camera does not support triggering the siren.")
            else:
                raise Exception("Camera does not support triggering the siren.")

    def updateTapo(self, camData):
        if not camData or camData["privacy_mode"] == "on":
            self.camData = STATE_UNAVAILABLE
        else:
            if (
                "alarm_config" in camData
                and camData["alarm_config"]
                and "siren_type" in camData["alarm_config"]
                and camData["alarm_config"]["siren_type"]
            ):
                self.sirenType = camData["alarm_config"]["siren_type"]
