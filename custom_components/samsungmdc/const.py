"""Constants for the Samsung MDC integration."""

from homeassistant.const import (
    Platform,
)
import homeassistant.const as homeassistant_consts

DOMAIN = "samsungmdc"
PLATFORMS = [
    Platform.MEDIA_PLAYER,
    # Platform.SENSOR,
    # Platform.BINARY_SENSOR,
    # Platform.SWITCH,
    # Platform.SELECT,
    # Platform.NUMBER,
    # Platform.TEXT,
]

DEFAULT_NAME = "Samsung MDC Display"

RESULT_INV_DSPID = "invalid_displayid"
RESULT_INV_IP = "invalid_ip"
RESULT_CANNOT_CONNECT = "cannot_connect"
RESULT_DISPLAY_OFF = "display_off"
RESULT_UNKNOWN = "unknown"

CONF_IP_ADDRESS = homeassistant_consts.CONF_IP_ADDRESS
CONF_NAME = homeassistant_consts.CONF_NAME
CONF_PORT = homeassistant_consts.CONF_PORT
CONF_TIMEOUT = homeassistant_consts.CONF_TIMEOUT
CONF_DISPLAY_ID = "display_id"
DEFAULT_DISPLAY_ID = 1
DEFAULT_POLL_INTERVAL = 10

# Connection retry settings (per Samsung MDC documentation)
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 2  # Samsung spec: retry every 2 seconds
POWER_ON_SOCKET_RECONNECT_TIME = (
    10  # Samsung spec: must re-connect socket after 10 sec for power on
)
POWER_ON_CHECK_INTERVAL = 3  # Check every 3 seconds after socket reconnect
POWER_ON_EXTERNAL_GRACE = 30  # seconds to ignore connection errors after power on
MAX_POWER_ON_CHECKS = 10  # Try for up to 30 more seconds (10 * 3)
MAX_CMD_CONCURRENCY = 1  # only one command at a time
BASE_BACKOFF = 0.5
BACKOFF_FACTOR = 1.8

SOURCE_NONE = "None"
SOURCE_S_VIDEO = "S-Video"
SOURCE_COMPONENT = "Component"
SOURCE_AV = "AV"
SOURCE_AV2 = "AV 2"
SOURCE_SCART1 = "SCART 1"
SOURCE_DVI = "DVI"
SOURCE_PC = "PC"
SOURCE_BNC = "BNC"
SOURCE_DVI_VIDEO = "DVI Video"
SOURCE_MAGIC_INFO = "MagicInfo"
SOURCE_HDMI1 = "HDMI 1"
SOURCE_HDMI1_PC = "HDMI 1 (PC)"
SOURCE_HDMI2 = "HDMI 2"
SOURCE_HDMI2_PC = "HDMI 2 (PC)"
SOURCE_DISPLAY_PORT_1 = "DisplayPort 1"
SOURCE_DISPLAY_PORT_2 = "DisplayPort 2"
SOURCE_DISPLAY_PORT_3 = "DisplayPort 3"
SOURCE_RF_TV = "TV"
SOURCE_HDMI3 = "HDMI 3"
SOURCE_HDMI3_PC = "HDMI 3 (PC)"
SOURCE_HDMI4 = "HDMI 4"
SOURCE_HDMI4_PC = "HDMI 4 (PC)"
SOURCE_TV_DTV = "DTV"
SOURCE_PLUG_IN_MODE = "Plug in mode"
SOURCE_HD_BASE_T = "HDBaseT"
SOURCE_MEDIA_MAGIC_INFO_S = "MagicInfo S"
SOURCE_WIDI_SCREEN_MIRRORING = "Screen Mirroring"
SOURCE_INTERNAL_USB = "USB"
SOURCE_URL_LAUNCHER = "URL Launcher"
SOURCE_IWB = "IWB"
