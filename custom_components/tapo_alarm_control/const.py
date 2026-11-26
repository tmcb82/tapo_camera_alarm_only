import logging

# Used for conflict detection
TPLINK_DOMAIN = "tplink"

DOMAIN = "tapo_alarm_control"
DOMAIN_CONFIG = DOMAIN + "_config"
BRAND = "TP-Link"

# Sign-in / connection related config entry keys
CONTROL_PORT = "control_port"
CLOUD_USERNAME = "cloud_username"
CLOUD_PASSWORD = "cloud_password"
CONF_TRANSPORT_METHOD = "transport_method"
IS_KLAP_DEVICE = "is_klap_device"
REPORTED_IP_ADDRESS = "reported_ip_address"

# Polling related config entry keys
UPDATE_INTERVAL_MAIN = "update_interval_main"
UPDATE_INTERVAL_BATTERY = "update_interval_battery"
UPDATE_INTERVAL_MAIN_DEFAULT = 30
UPDATE_INTERVAL_BATTERY_DEFAULT = 60 * 10

PYTAPO_REQUIRED_VERSION = "3.4.34"

LOGGER = logging.getLogger("custom_components." + DOMAIN)

# Requests of pytapo's getMost() which are not needed for the siren and manual
# alarm entities. They are omitted from every poll to keep requests small.
# "getAudioConfig" must stay in this list: pytapo retries getMost() without it
# when a hub answers with a malformed response, and a non-empty omit list
# disables that retry.
OMITTED_POLL_METHODS = [
    "getLinecrossingDetectionConfig",
    "getDualCamLinkage",
    "readLinkageTargetSetting",
    "getLinkageTargetCapability",
    "getDualCamCapability",
    "getAllChnInfo",
    "getDiagnoseMode",
    "getCoverConfig",
    "getSmartTrackConfig",
    "getFloodlightStatus",
    "getFloodlightConfig",
    "getFloodlightCapability",
    "getPirDetCapability",
    "getPirDetConfig",
    "getAlertEventType",
    "getDstRule",
    "getClockStatus",
    "getTimezone",
    "getNightVisionCapability",
    "getDetectionConfig",
    "getPersonDetectionConfig",
    "getVehicleDetectionConfig",
    "getBCDConfig",
    "getPetDetectionConfig",
    "getPackageDetectionConfig",
    "getBarkDetectionConfig",
    "getMeowDetectionConfig",
    "getGlassDetectionConfig",
    "getTamperDetectionConfig",
    "getLdc",
    "getLedStatus",
    "getTargetTrackConfig",
    "getPatrolSchedule",
    "getPatrolAction",
    "getPresetConfig",
    "getFirmwareUpdateStatus",
    "getMediaEncrypt",
    "getConnectionType",
    "getAlarmPlan",
    "getAlertTypeList",
    "getLightTypeList",
    "getLightFrequencyInfo",
    "getLightFrequencyCapability",
    "getRotationStatus",
    "getNightVisionModeConfig",
    "getWhitelampStatus",
    "getWhitelampConfig",
    "getWhitelampCapability",
    "getNightlightStatus",
    "getMusicConfig",
    "getMusicList",
    "getMusicCapability",
    "getMsgPushConfig",
    "getSdCardStatus",
    "getCircularRecordingConfig",
    "getRecordPlan",
    "getAudioConfig",
    "getFirmwareAutoUpgradeConfig",
    "getVideoQualities",
    "getVideoCapability",
    "getQuickRespList",
    "getChimeRingPlan",
    "getRingStatus",
    "getChimeCtrlList",
    "getBatteryPowerSave",
    "getBatteryOperatingMode",
    "getBatteryOperatingModeParam",
    "getPowerMode",
    "getChargingMode",
    "getBatteryStatistic",
    "getBatteryConfig",
    "getWakeUpConfig",
    "getReboot",
    "getBatteryCapability",
    "getHubStorage",
    "getPirSensitivity",
    "getClipsConfig",
]

TAPO_PREFIXES = (
    r"^c[0-9]{3}[a-zA-Z]*_.*",  # Security Cameras (C100, C200, C310, C325WB, etc.)
    r"^d[0-9]{3}[a-zA-Z]*_.*",  # Doorbells (D230, D235, D350V, etc.)
    r"^tc[0-9]{2,3}[a-zA-Z]*_.*",  # Pan/Tilt Cameras (TC60, TC70, TC85, etc.)
    r"^d[0-9]{3}[a-zA-Z]*c_.*",  # Doorbell Chimes (D100C, D230C, D325C, etc.)
    r"^h[0-9]{3}[a-zA-Z]*_.*",  # Smart Hubs (H100, H200, H300, etc.)
)
