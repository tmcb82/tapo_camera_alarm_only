import asyncio
import base64
import hashlib
import socket
import time
import urllib.parse

import requests
from haffmpeg.tools import IMAGE_JPEG, ImageFrame
from pytapo import Tapo

from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.const import CONF_HOST, CONF_IP_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .const import (
    BRAND,
    CLOUD_PASSWORD,
    CONF_TRANSPORT_METHOD,
    CONTROL_PORT,
    DOMAIN,
    DOMAIN_CONFIG,
    LOGGER,
    OMITTED_POLL_METHODS,
    TPLINK_DOMAIN,
)

ALARM_CONFIG_TYPES = ("getAlarm", "getAlarmConfig", "getAlertConfig")


def isBatteryPowered(camData):
    basicInfo = camData.get("basic_info", {})
    return any(
        basicInfo.get(field) in ("BATTERY", "SOLAR")
        for field in ("power", "power_mode")
    )


def _is_used_by_tplink(hass: HomeAssistant, host: str) -> bool:
    for entry in hass.config_entries.async_entries(
        TPLINK_DOMAIN, include_ignore=False, include_disabled=False
    ):
        if entry.data.get(CONF_HOST) != host:
            continue
        return True
    return False


def pytapoLog(msg):
    LOGGER.debug(f"[pytapo] {msg}")


def pytapoWarnLog(msg):
    LOGGER.warning(f"[pytapo] {msg}")


def isKLAP(host, port, timeout=2):
    try:
        url = f"http://{host}:{port}"
        response = requests.get(url, timeout=timeout)
        return "200 OK" in response.text
    except requests.RequestException:
        return False


def registerController(
    host,
    control_port,
    username,
    password,
    password_cloud="",
    super_secret_key="",
    device_id=None,
    is_klap=None,
    hass=None,
):
    selected_transport_method = (
        hass.data.get(DOMAIN_CONFIG, {}).get(CONF_TRANSPORT_METHOD)
        if hass is not None
        else None
    )
    LOGGER.debug(
        f"Creating Tapo controller with transport method {selected_transport_method}."
    )

    return Tapo(
        host,
        username,
        password,
        password_cloud,
        super_secret_key,
        device_id,
        reuseSession=False,
        printDebugInformation=pytapoLog,
        printWarnInformation=pytapoWarnLog,
        retryStok=False,
        controlPort=control_port,
        isKLAP=is_klap,
        hass=hass,
        transportMethod=selected_transport_method,
    )


def isOpen(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect((ip, int(port)))
        s.shutdown(2)
        return True
    except Exception:
        return False
    finally:
        s.close()


def areCameraPortsOpened(host, controlPort=443):
    return isOpen(host, int(controlPort)) and isOpen(host, 554) and isOpen(host, 2020)


async def isRtspStreamWorking(
    hass, host, username, password, stream: str | None = None
):
    LOGGER.debug("[isRtspStreamWorking][%s] Testing RTSP stream.", host)
    _ffmpeg = hass.data[DATA_FFMPEG]
    LOGGER.debug("[isRtspStreamWorking][%s] Creating image frame.", host)
    ffmpeg = ImageFrame(_ffmpeg.binary)
    LOGGER.debug("[isRtspStreamWorking][%s] Encoding username and password.", host)
    username = urllib.parse.quote_plus(username)
    password = urllib.parse.quote_plus(password)

    stream_path = stream or "stream1"
    auth = f"{username}:{password}@" if username or password else ""
    streaming_url = f"rtsp://{auth}{host}:554/{stream_path}"

    safe_auth = "HIDDEN_USERNAME:HIDDEN_PASSWORD@" if auth else ""
    safe_streaming_url = f"rtsp://{safe_auth}{host}:554/{stream_path}"

    LOGGER.debug(
        "[isRtspStreamWorking][%s] Getting image from %s.",
        host,
        safe_streaming_url,
    )
    image = await asyncio.shield(
        ffmpeg.get_image(
            streaming_url,
            output_format=IMAGE_JPEG,
        )
    )
    LOGGER.debug(
        "[isRtspStreamWorking][%s] Image data received.",
        host,
    )
    return not image == b""


def result_has_error(result):
    if (
        result is not False
        and "result" in result
        and "responses" in result["result"]
        and any(
            map(
                lambda x: "error_code" not in x or x["error_code"] == 0,
                result["result"]["responses"],
            )
        )
    ):
        return False
    if result is not False and (
        "error_code" not in result or result["error_code"] == 0
    ):
        return False
    else:
        return True


def getDataForController(hass, entry, controller):
    entryData = hass.data[DOMAIN][entry.entry_id]
    if controller == entryData["controller"]:
        return entryData
    for childDevice in entryData.get("childDevices") or []:
        if controller == childDevice["controller"]:
            return childDevice
    return None


CONNECTION_PROBLEM_MARKERS = (
    "Invalid authentication data",
    "Temporary Suspension",
    "Failed to establish a new connection",
)


def connectionProblem(*errors):
    """Message of the first error which says the camera could not be reached or rejected the login."""
    for error in errors:
        message = str(error)
        if any(marker in message for marker in CONNECTION_PROBLEM_MARKERS):
            return message
        if isinstance(error, (requests.exceptions.RequestException, OSError)):
            # connection refused, timeouts, unreachable network, unreadable answer
            return f"could not communicate with the camera ({type(error).__name__})"
    return None


def recordPollResult(controllerData, error=None):
    """Remember whether the last poll of a controller worked, and why not."""
    if error is None:
        controllerData["pollOk"] = True
        controllerData["lastPollSuccess"] = time.time()
        controllerData["pollFailures"] = 0
        controllerData["pollFailureReason"] = None
        return
    message = str(error)
    if message == "Invalid authentication data":
        reason = "invalid_authentication"
    elif "Temporary Suspension" in message:
        reason = "temporary_suspension"
    else:
        reason = "error"
    controllerData["pollOk"] = False
    controllerData["pollFailures"] = controllerData.get("pollFailures", 0) + 1
    controllerData["pollFailureReason"] = reason


def notifyPollResult(controllerData):
    """Write the state of the entities which report the result of a poll."""
    for item in controllerData.get("entities", []):
        entity = item["entity"]
        if getattr(entity, "_tracks_poll_result", False) and entity._enabled:
            entity.async_schedule_update_ha_state()


def convertBasicInfo(basicInfo):
    convertedBasicInfo = basicInfo
    convertedBasicInfo["device_alias"] = base64.b64decode(basicInfo["nickname"]).decode(
        "utf-8"
    )
    convertedBasicInfo["device_model"] = basicInfo["model"]
    convertedBasicInfo["sw_version"] = basicInfo["fw_ver"]
    convertedBasicInfo["hw_version"] = basicInfo["hw_ver"]
    return convertedBasicInfo


def getIP(data):
    # KLAP report IP in this function
    if (
        "basic_info" in data
        and data["basic_info"] is not None
        and "ip" in data["basic_info"]
    ):
        return data["basic_info"]["ip"]
    # cameras report IP in this function
    elif (
        "network_ip_info" in data
        and data["network_ip_info"] is not None
        and "network" in data["network_ip_info"]
        and "wan" in data["network_ip_info"]["network"]
        and "ipaddr" in data["network_ip_info"]["network"]["wan"]
    ):
        return data["network_ip_info"]["network"]["wan"]["ipaddr"]
    return False


def build_device_info(attributes: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, slugify(f"{attributes['mac']}_tapo_alarm_control"))},
        connections={("mac", attributes["mac"])},
        name=attributes["device_alias"],
        manufacturer=BRAND,
        model=attributes["device_model"],
        sw_version=attributes["sw_version"],
        hw_version=attributes["hw_version"],
    )


async def getCamData(hass, controller):
    LOGGER.debug("getCamData")

    data = await hass.async_add_executor_job(controller.getMost, OMITTED_POLL_METHODS)
    LOGGER.debug("Raw update data:")
    LOGGER.debug(data)

    camData = {}

    camData["raw"] = data

    camData["user"] = controller.user
    if controller.isKLAP:
        camData["basic_info"] = convertBasicInfo(data["get_device_info"][0])
    else:
        camData["basic_info"] = data["getDeviceInfo"][0]["device_info"]["basic_info"]

    try:
        privacy_mode = data["getLensMaskConfig"][0]["lens_mask"]["lens_mask_info"][
            "enabled"
        ]
    except Exception:
        privacy_mode = None
    camData["privacy_mode"] = privacy_mode

    try:
        network_ip_info = data["getDeviceIpAddress"][0]
    except Exception:
        network_ip_info = None
    camData["network_ip_info"] = network_ip_info

    hubSiren = False
    alarmConfig = None
    alarmStatus = False
    if controller.isKLAP is False:
        try:
            if data["getSirenConfig"][0] != False:
                hubSiren = True
                sirenData = data["getSirenConfig"][0]
                alarmConfig = {
                    "typeOfAlarm": "getSirenConfig",
                    "siren_type": sirenData["siren_type"],
                    "siren_volume": sirenData["volume"],
                    "siren_duration": sirenData["duration"],
                }
        except Exception as err:
            LOGGER.error(f"getSirenConfig unexpected error {err=}, {type(err)=}")

    if controller.isKLAP is False:
        try:
            if not hubSiren and data["getAlarmConfig"][0] != False:
                alarmData = data["getAlarmConfig"][0]
                alarmConfig = {
                    "typeOfAlarm": "getAlarmConfig",
                    "mode": alarmData["alarm_mode"],
                    "automatic": alarmData["enabled"],
                }
                if "light_type" in alarmData:
                    alarmConfig["light_type"] = alarmData["light_type"]
                if "siren_type" in alarmData:
                    alarmConfig["siren_type"] = alarmData["siren_type"]
                if "siren_duration" in alarmData:
                    alarmConfig["siren_duration"] = alarmData["siren_duration"]
                if "alarm_duration" in alarmData:
                    alarmConfig["alarm_duration"] = alarmData["alarm_duration"]
                if "siren_volume" in alarmData:
                    alarmConfig["siren_volume"] = alarmData["siren_volume"]
                if "alarm_volume" in alarmData:
                    alarmConfig["alarm_volume"] = alarmData["alarm_volume"]

        except Exception as err:
            LOGGER.error(f"getAlarmConfig unexpected error {err=}, {type(err)=}")

    if controller.isKLAP is False:
        try:
            for alertConfig in data["getAlertConfig"]:
                alertConfigMsgAlarm = (
                    alertConfig.get("msg_alarm")
                    if isinstance(alertConfig, dict)
                    else None
                )
                alarmData = (
                    alertConfigMsgAlarm.get("chn1_msg_alarm_info")
                    if isinstance(alertConfigMsgAlarm, dict)
                    else None
                )
                if alarmConfig is None and isinstance(alarmData, dict):
                    alarmConfig = {
                        "typeOfAlarm": "getAlertConfig",
                        "mode": alarmData["alarm_mode"],
                        "automatic": alarmData["enabled"],
                        "alert_config": alarmData,
                    }
                    if "light_type" in alarmData:
                        alarmConfig["light_type"] = alarmData["light_type"]
                    if "siren_type" in alarmData:
                        alarmConfig["siren_type"] = alarmData["siren_type"]
                    if "alarm_type" in alarmData:
                        alarmConfig["siren_type"] = alarmData["alarm_type"]
                    if "siren_duration" in alarmData:
                        alarmConfig["siren_duration"] = alarmData["siren_duration"]
                    if "alarm_duration" in alarmData:
                        alarmConfig["alarm_duration"] = alarmData["alarm_duration"]
                    if "siren_volume" in alarmData:
                        alarmConfig["siren_volume"] = alarmData["siren_volume"]
                    if "alarm_volume" in alarmData:
                        alarmConfig["alarm_volume"] = alarmData["alarm_volume"]
                    break
        except Exception as err:
            LOGGER.error(f"getAlertConfig unexpected error {err=}, {type(err)=}")

    if controller.isKLAP is False:
        try:
            lastAlarmInfo = data["getLastAlarmInfo"][0]
            lastAlarmInfoMsgAlarm = (
                lastAlarmInfo.get("msg_alarm")
                if isinstance(lastAlarmInfo, dict)
                else None
            )
            alarmData = (
                lastAlarmInfoMsgAlarm.get("chn1_msg_alarm_info")
                if isinstance(lastAlarmInfoMsgAlarm, dict)
                else None
            )
            if alarmConfig is None and isinstance(alarmData, dict):
                alarmConfig = {
                    "typeOfAlarm": "getAlarm",
                    "mode": alarmData["alarm_mode"],
                    "automatic": alarmData["enabled"],
                }
                if "light_type" in alarmData:
                    alarmConfig["light_type"] = alarmData["light_type"]
                if "siren_type" in alarmData:
                    alarmConfig["siren_type"] = alarmData["siren_type"]
                if "alarm_type" in alarmData:
                    alarmConfig["siren_type"] = alarmData["alarm_type"]
                if "siren_duration" in alarmData:
                    alarmConfig["siren_duration"] = alarmData["siren_duration"]
                if "alarm_duration" in alarmData:
                    alarmConfig["alarm_duration"] = alarmData["alarm_duration"]
                if "siren_volume" in alarmData:
                    alarmConfig["siren_volume"] = alarmData["siren_volume"]
                if "alarm_volume" in alarmData:
                    alarmConfig["alarm_volume"] = alarmData["alarm_volume"]
        except Exception as err:
            LOGGER.error(f"getLastAlarmInfo unexpected error {err=}, {type(err)=}")

    if controller.isKLAP is False:
        try:
            if (
                data["getSirenStatus"][0] is not False
                and "status" in data["getSirenStatus"][0]
            ):
                alarmStatus = data["getSirenStatus"][0]["status"]
        except Exception as err:
            LOGGER.error(f"getSirenStatus unexpected error {err=}, {type(err)=}")

    camData["alarm_config"] = alarmConfig
    camData["alarm_status"] = alarmStatus
    camData["alarm_is_hubSiren"] = hubSiren

    try:
        childDevices = data["getChildDeviceList"][0]
    except Exception:
        childDevices = None
    camData["childDevices"] = childDevices

    camData["updated"] = time.time()

    LOGGER.debug("getCamData - done")
    LOGGER.debug("Processed update data:")
    LOGGER.debug(camData)
    return camData


async def update_listener(hass, entry):
    """Handle options update."""
    entryData = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entryData is None:
        return
    host = entry.data.get(CONF_IP_ADDRESS)
    controlPort = entry.data.get(CONTROL_PORT)
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    cloud_password = entry.data.get(CLOUD_PASSWORD)
    try:
        newUUID = hashlib.sha256(
            (str(host) + str(username) + str(password) + str(cloud_password)).encode()
        ).hexdigest()
        # only update controller if auth data changed
        if newUUID != hass.data[DOMAIN][entry.entry_id]["uuid"]:
            hass.data[DOMAIN][entry.entry_id]["uuid"] = newUUID
            if (
                hass.data[DOMAIN][entry.entry_id]["controller"]
                in hass.data[DOMAIN][entry.entry_id]["allControllers"]
            ):
                hass.data[DOMAIN][entry.entry_id]["allControllers"].remove(
                    hass.data[DOMAIN][entry.entry_id]["controller"]
                )
            if cloud_password != "":
                tapoController = await hass.async_add_executor_job(
                    registerController,
                    host,
                    controlPort,
                    "admin",
                    cloud_password,
                    "",
                    "",
                    None,
                    None,
                    hass,
                )
            else:
                tapoController = await hass.async_add_executor_job(
                    registerController,
                    host,
                    controlPort,
                    username,
                    password,
                    "",
                    "",
                    None,
                    None,
                    hass,
                )
            hass.data[DOMAIN][entry.entry_id]["usingCloudPassword"] = (
                cloud_password != ""
            )
            hass.data[DOMAIN][entry.entry_id]["controller"] = tapoController
            hass.data[DOMAIN][entry.entry_id]["allControllers"].append(tapoController)
    except Exception:
        LOGGER.error(
            "Authentication to Tapo camera failed."
            + " Please restart the camera and try again."
        )

    await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()


async def check_functionality(entry, hass, cls, check_function):
    try:
        if check_function == "getAlarm":
            alarm_config = entry.get("camData", {}).get("alarm_config")
            if (
                isinstance(alarm_config, dict)
                and alarm_config.get("typeOfAlarm") in ALARM_CONFIG_TYPES
            ):
                LOGGER.debug(
                    f"Found parsed alarm config, creating {cls.__name__}"
                )
                return True

        if isCacheSupported(check_function, entry["camData"]["raw"]):
            LOGGER.debug(
                f"Found cached capability {check_function}, creating {cls.__name__}"
            )
            return True
        else:
            if (
                entry["controller"].isKLAP is False
            ):  # no uncached entries for klap devices, so no need to check them
                LOGGER.debug(
                    f"Capability {check_function} not found, querying again..."
                )
                result = await hass.async_add_executor_job(
                    getattr(entry["controller"], check_function)
                )
                LOGGER.debug(result)
                LOGGER.debug(f"Creating {cls.__name__}")
                return True
    except Exception as err:
        LOGGER.info(f"Camera does not support {cls.__name__}: {err}")
        return False
    return False


async def check_and_create(entry, hass, cls, check_function, config_entry):
    if await check_functionality(entry, hass, cls, check_function):
        try:
            return cls(entry, hass, config_entry)
        except Exception as err:
            LOGGER.info(f"Camera does not support {cls.__name__}: {err}")
            return None
    return None


def pytapoFunctionMap(pytapoFunctionName):
    if pytapoFunctionName == "getAlarm":
        return ["getLastAlarmInfo", "getAlarmConfig"]
    return [pytapoFunctionName]


def isCacheSupported(check_function, rawData):
    rawFunctions = pytapoFunctionMap(check_function)
    for function in rawFunctions:
        if function in rawData:
            if rawData[function][0]:
                return True
            else:
                raise Exception(
                    f"Capability {check_function} (mapped to:{function}) cached but not supported."
                )
    return False
