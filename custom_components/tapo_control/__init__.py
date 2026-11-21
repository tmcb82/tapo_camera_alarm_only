import datetime
import hashlib

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_USERNAME,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    ConfigEntryAuthFailed,
    DependencyError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_TRANSPORT_METHOD,
    CONTROL_PORT,
    DOMAIN_CONFIG,
    IS_KLAP_DEVICE,
    LOGGER,
    DOMAIN,
    CLOUD_PASSWORD,
    PYTAPO_REQUIRED_VERSION,
    REPORTED_IP_ADDRESS,
    UPDATE_INTERVAL_BATTERY,
    UPDATE_INTERVAL_BATTERY_DEFAULT,
    UPDATE_INTERVAL_MAIN,
    UPDATE_INTERVAL_MAIN_DEFAULT,
)
from .utils import (
    _is_used_by_tplink,
    getDataForController,
    getIP,
    isBatteryPowered,
    registerController,
    getCamData,
    update_listener,
)
from pytapo.version import PYTAPO_VERSION

PLATFORMS = ["button", "siren"]

# Oldest config entry version which can still be migrated.
OLDEST_MIGRATABLE_VERSION = 15
CURRENT_VERSION = 25


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Tapo: Cameras Control component from YAML."""
    transport_method = None
    if DOMAIN in config and isinstance(config[DOMAIN], dict):
        transport_method = config[DOMAIN].get(CONF_TRANSPORT_METHOD)
    hass.data.setdefault(DOMAIN_CONFIG, {})
    hass.data[DOMAIN_CONFIG][CONF_TRANSPORT_METHOD] = transport_method
    if transport_method:
        LOGGER.warning(
            "Using transport method override from configuration.yaml: %s",
            transport_method,
        )
    return True


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version < OLDEST_MIGRATABLE_VERSION:
        LOGGER.error(
            "Config entry version %s is too old to be migrated. Please remove "
            "the integration entry and add it again.",
            config_entry.version,
        )
        return False

    while config_entry.version < CURRENT_VERSION:
        version = config_entry.version
        new = {**config_entry.data}

        if version == 15:
            new[UPDATE_INTERVAL_MAIN] = UPDATE_INTERVAL_MAIN_DEFAULT
            new[UPDATE_INTERVAL_BATTERY] = UPDATE_INTERVAL_BATTERY_DEFAULT
            hass.config_entries.async_update_entry(config_entry, data=new, version=16)

        elif version == 17:
            new[CONTROL_PORT] = 443
            hass.config_entries.async_update_entry(config_entry, data=new, version=18)

        elif version == 18:
            new[CONTROL_PORT] = int(new[CONTROL_PORT])
            hass.config_entries.async_update_entry(config_entry, data=new, version=19)

        elif version == 19:
            new[IS_KLAP_DEVICE] = False
            hass.config_entries.async_update_entry(config_entry, data=new, version=20)

        elif version == 20:
            try:
                host = config_entry.data.get(CONF_IP_ADDRESS)
                controlPort = config_entry.data.get(CONTROL_PORT)
                isKlapDevice = config_entry.data.get(IS_KLAP_DEVICE)
                cloud_password = config_entry.data.get(CLOUD_PASSWORD)
                username = config_entry.data.get(CONF_USERNAME)
                password = config_entry.data.get(CONF_PASSWORD)
                if cloud_password != "":
                    LOGGER.debug("Setting up controller using cloud password.")
                    tapoController = await hass.async_add_executor_job(
                        registerController,
                        host,
                        controlPort,
                        "admin",
                        cloud_password,
                        cloud_password,
                        "",
                        None,
                        isKlapDevice,
                        hass,
                    )
                else:
                    LOGGER.debug("Setting up controller using username and password.")
                    tapoController = await hass.async_add_executor_job(
                        registerController,
                        host,
                        controlPort,
                        username,
                        password,
                        "",
                        "",
                        None,
                        isKlapDevice,
                        hass,
                    )
                camData = await getCamData(hass, tapoController)
                reported_ip_address = getIP(camData)
                LOGGER.debug(f"Detected IP: {reported_ip_address}")
                new[REPORTED_IP_ADDRESS] = reported_ip_address

                hass.config_entries.async_update_entry(
                    config_entry,
                    data=new,
                    version=21,
                    unique_id=DOMAIN
                    + (reported_ip_address if reported_ip_address else host),
                )

            except Exception as e:
                LOGGER.error(
                    "Unable to connect to Tapo: Cameras Control controller: %s", str(e)
                )
                if "Invalid authentication data" in str(e):
                    raise ConfigEntryAuthFailed(e)
                # keep retrying to authenticate eventually (also covers
                # "Temporary Suspension:"), or retry for anything else
                raise ConfigEntryNotReady

        elif version == 24:
            host = new.get(CONF_IP_ADDRESS)
            reported_ip_address = new.get(REPORTED_IP_ADDRESS)
            control_port = new.get(CONTROL_PORT)
            if control_port is not None and (reported_ip_address or host):
                desired_unique_id = (
                    DOMAIN
                    + (reported_ip_address if reported_ip_address else host)
                    + str(control_port)
                )
            else:
                desired_unique_id = config_entry.unique_id

            if desired_unique_id != config_entry.unique_id:
                LOGGER.debug(
                    f"Updating {config_entry.unique_id} to {desired_unique_id} as part of migration."
                )
                hass.config_entries.async_update_entry(
                    config_entry,
                    data=new,
                    unique_id=desired_unique_id,
                    version=25,
                )
            else:
                LOGGER.debug(
                    f"Skipping {config_entry.unique_id} for unique_id update as part of migration."
                )
                hass.config_entries.async_update_entry(
                    config_entry,
                    data=new,
                    version=25,
                )

        else:
            # Versions 16, 21, 22 and 23 only added settings of features which
            # do not exist in this version of the integration.
            hass.config_entries.async_update_entry(
                config_entry, data=new, version=version + 1
            )

    LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.debug("Unloading tapo_control...")
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    # Close controllers to avoid unclosed aiohttp sessions
    await _close_controllers(hass, entry.entry_id)

    return True


async def _close_controllers(hass: HomeAssistant, entry_id: str):
    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if not data:
        return

    controllers = []
    if data.get("controller"):
        controllers.append(data["controller"])
    for child in data.get("childDevices", []):
        ctrl = child.get("controller")
        if ctrl:
            controllers.append(ctrl)

    for ctrl in controllers:
        try:
            await hass.async_add_executor_job(ctrl.close)
        except Exception as err:
            LOGGER.debug("Error closing controller during shutdown: %s", err)

    # Remove the entry data
    hass.data[DOMAIN].pop(entry_id, None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    if PYTAPO_REQUIRED_VERSION != PYTAPO_VERSION:
        raise DependencyError(
            [
                f"Incorrect pytapo version installed: {PYTAPO_VERSION}. Required: {PYTAPO_REQUIRED_VERSION}."
            ]
        )

    LOGGER.debug("Starting setup of Tapo: Cameras Control")

    """Set up the Tapo: Cameras Control component from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data.get(CONF_IP_ADDRESS)
    controlPort = entry.data.get(CONTROL_PORT)

    if _is_used_by_tplink(hass, host):
        LOGGER.warning(
            "TP-Link core integration is also configured for device IP %s. "
            "Using multiple integrations for the same device causes instability.",
            host,
        )

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    isKlapDevice = entry.data.get(IS_KLAP_DEVICE)
    cloud_password = entry.data.get(CLOUD_PASSWORD)
    updateIntervalMain = entry.data.get(UPDATE_INTERVAL_MAIN)
    updateIntervalBattery = entry.data.get(UPDATE_INTERVAL_BATTERY)

    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {}
        if "setup_retries" not in hass.data[DOMAIN][entry.entry_id]:
            hass.data[DOMAIN][entry.entry_id]["setup_retries"] = 0

    try:
        LOGGER.debug(isKlapDevice)
        if cloud_password != "":
            LOGGER.debug("Setting up controller using cloud password.")
            tapoController = await hass.async_add_executor_job(
                registerController,
                host,
                controlPort,
                "admin",
                cloud_password,
                cloud_password,
                "",
                None,
                isKlapDevice,
                hass,
            )
        else:
            LOGGER.debug("Setting up controller using username and password.")
            tapoController = await hass.async_add_executor_job(
                registerController,
                host,
                controlPort,
                username,
                password,
                "",
                "",
                None,
                isKlapDevice,
                hass,
            )
        LOGGER.debug("Controller has been set up.")

        def getAllEntities(entry):
            # Gather all entities, including of children devices
            allEntities = entry["entities"].copy()
            for childDevice in entry["childDevices"]:
                allEntities.extend(childDevice["entities"])
            return allEntities

        async def async_update_data():
            LOGGER.debug("async_update_data - entry")
            tapoController = hass.data[DOMAIN][entry.entry_id]["controller"]
            ts = datetime.datetime.utcnow().timestamp()

            # cameras state
            LOGGER.debug("async_update_data - before someEntityEnabled check")
            someEntityEnabled = False
            allEntities = getAllEntities(hass.data[DOMAIN][entry.entry_id])
            for entity in allEntities:
                LOGGER.debug(entity["entity"])
                if entity["entity"]._enabled:
                    LOGGER.debug("async_update_data - enabling someEntityEnabled check")
                    someEntityEnabled = True
                    break

            if (
                someEntityEnabled
                and hass.data[DOMAIN][entry.entry_id]["refreshEnabled"]
            ):
                # Update data for all controllers
                updateDataForAllControllers = {}
                for controller in hass.data[DOMAIN][entry.entry_id]["allControllers"]:
                    controllerData = getDataForController(hass, entry, controller)
                    LOGGER.debug(
                        f"{controllerData['name']} running on battery: {controllerData['isRunningOnBattery']}"
                    )
                    if (
                        controllerData["isRunningOnBattery"] is False
                        and ts - controllerData["lastUpdate"] > updateIntervalMain
                    ) or (
                        controllerData["isRunningOnBattery"] is True
                        and ts - controllerData["lastUpdate"] > updateIntervalBattery
                    ):
                        timeForAnUpdate = True
                        LOGGER.debug(f"Updating {controllerData['name']}...")
                    else:
                        timeForAnUpdate = False
                        LOGGER.debug(f"Skipping update for {controllerData['name']}...")
                    if timeForAnUpdate:
                        try:
                            updateDataForAllControllers[controller] = await getCamData(
                                hass, controller
                            )
                            controllerData["isRunningOnBattery"] = isBatteryPowered(
                                updateDataForAllControllers[controller]
                            )
                            controllerData["lastUpdate"] = (
                                datetime.datetime.utcnow().timestamp()
                            )
                            controllerData["reauth_retries"] = 0
                        except Exception as e:
                            updateDataForAllControllers[controller] = False
                            if str(e) == "Invalid authentication data":
                                if controllerData["reauth_retries"] < 3:
                                    controllerData["reauth_retries"] += 1
                                    raise e
                                else:
                                    controllerData["refreshEnabled"] = False
                                    raise ConfigEntryAuthFailed(e)
                            LOGGER.error(e)

                if tapoController in updateDataForAllControllers:
                    hass.data[DOMAIN][entry.entry_id]["camData"] = (
                        updateDataForAllControllers[tapoController]
                    )

                    LOGGER.debug("Updating entities...")

                    # Gather all entities, including of children devices
                    allEntities = getAllEntities(hass.data[DOMAIN][entry.entry_id])

                    for entity in allEntities:
                        if (
                            entity["entity"]._enabled
                            and entity["entry"]["controller"]
                            in updateDataForAllControllers
                        ):
                            LOGGER.debug("Updating entity...")
                            LOGGER.debug(entity["entity"])
                            entity["camData"] = updateDataForAllControllers[
                                entity["entry"]["controller"]
                            ]
                            entity["entity"].updateTapo(
                                updateDataForAllControllers[
                                    entity["entry"]["controller"]
                                ]
                            )
                            entity["entity"].async_schedule_update_ha_state(True)

        LOGGER.debug("Setting up data update coordinator.")

        tapoCoordinator = DataUpdateCoordinator(
            hass,
            LOGGER,
            name="Tapo resource status",
            update_method=async_update_data,
        )

        LOGGER.debug("Retrieving initial device data.")

        camData = await getCamData(hass, tapoController)
        LOGGER.debug("Retrieved initial device data.")
        LOGGER.debug("Setting up entry data.")
        hass.data[DOMAIN][entry.entry_id] = {
            "setup_retries": 0,
            "reauth_retries": 0,
            "controller": tapoController,
            "entry": entry,
            "usingCloudPassword": cloud_password != "",
            "allControllers": [tapoController],
            "update_listener": entry.add_update_listener(update_listener),
            "coordinator": tapoCoordinator,
            "camData": camData,
            "lastUpdate": 0,
            "entities": [],
            "name": camData["basic_info"]["device_alias"],
            "childDevices": [],
            "isRunningOnBattery": isBatteryPowered(camData),
            "isChild": False,
            "uuid": hashlib.md5(
                (
                    str(host) + str(username) + str(password) + str(cloud_password)
                ).encode()
            ).hexdigest(),
            "isParent": False,
            "refreshEnabled": True,
        }
        LOGGER.debug("Entry data has been set up.")

        if tapoController.isKLAP is False:
            LOGGER.debug("Controller is not KLAP device.")
            if not (
                camData["childDevices"] is False or camData["childDevices"] is None
            ):
                LOGGER.debug("Device is a parent.")
                hass.data[DOMAIN][entry.entry_id]["isParent"] = True
                if (
                    camData["childDevices"]
                    and "child_device_list" in camData["childDevices"]
                ):
                    for childDevice in camData["childDevices"]["child_device_list"]:
                        LOGGER.debug("Setting up child controller.")
                        tapoChildController = await hass.async_add_executor_job(
                            registerController,
                            host,
                            controlPort,
                            "admin",
                            cloud_password,
                            cloud_password,
                            "",
                            childDevice["device_id"],
                            None,
                            hass,
                        )
                        LOGGER.debug("Child controller set up.")
                        hass.data[DOMAIN][entry.entry_id]["allControllers"].append(
                            tapoChildController
                        )
                        LOGGER.debug("Getting initial child device data.")

                        childCamData = await getCamData(hass, tapoChildController)
                        LOGGER.debug("Retrieved initial child device data.")
                        hass.data[DOMAIN][entry.entry_id]["childDevices"].append(
                            {
                                "controller": tapoChildController,
                                "reauth_retries": 0,
                                "coordinator": tapoCoordinator,
                                "entry": entry,
                                "usingCloudPassword": cloud_password != "",
                                "camData": childCamData,
                                "lastUpdate": 0,
                                "entities": [],
                                "name": childCamData["basic_info"]["device_alias"],
                                "childDevices": [],
                                "isChild": True,
                                "isRunningOnBattery": isBatteryPowered(childCamData),
                                "isParent": False,
                            }
                        )
                else:
                    LOGGER.debug("No child devices found.")

        LOGGER.debug("Setting up entities.")
        await hass.async_create_task(
            hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        )
        LOGGER.debug("Entities set up.")

        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            lambda event: hass.add_job(_close_controllers, hass, entry.entry_id),
        )

        entry.async_on_unload(hass.data[DOMAIN][entry.entry_id]["update_listener"])

    except Exception as e:
        LOGGER.debug(
            "Tapo integration setup failed for %s (%s): %r",
            host,
            type(e).__name__,
            e,
            exc_info=True,
        )
        if "Invalid authentication data" in str(e):
            if hass.data[DOMAIN][entry.entry_id]["setup_retries"] < 3:
                hass.data[DOMAIN][entry.entry_id]["setup_retries"] += 1
                raise ConfigEntryNotReady(e)
            raise ConfigEntryAuthFailed(e)
        else:
            if "Temporary Suspension:" in str(
                e
            ):  # keep retrying to authenticate eventually, or throw
                # ConfigEntryAuthFailed on invalid auth eventually
                raise ConfigEntryNotReady(e)
            # Retry for anything else
            LOGGER.error(
                "Unable to connect to Tapo: Cameras Control controller: %s", str(e)
            )
            raise ConfigEntryNotReady(e)

    LOGGER.debug("Tapo integration setup completed for %s.", host)
    return True
