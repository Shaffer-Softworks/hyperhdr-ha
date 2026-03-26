"""Constants for HyperHDR integration."""

from __future__ import annotations

# HyperHDR API: "origin" maxLength in JSON schema (e.g. set-color / set-effect).
HYPERHDR_ORIGIN_MAX_LENGTH = 20


def sanitize_hyperhdr_origin(origin: str) -> str:
    """Clamp origin to HyperHDR JSON schema maxLength (validation rejects longer strings)."""
    trimmed = origin.strip()
    if len(trimmed) <= HYPERHDR_ORIGIN_MAX_LENGTH:
        return trimmed
    return trimmed[:HYPERHDR_ORIGIN_MAX_LENGTH]


CONF_ADMIN_PASSWORD = "admin_password"
CONF_AUTH_ID = "auth_id"
CONF_CREATE_TOKEN = "create_token"
CONF_INSTANCE = "instance"
CONF_INSTANCE_CLIENTS = "INSTANCE_CLIENTS"
CONF_ON_UNLOAD = "ON_UNLOAD"
CONF_PORT_WS = "port_ws"
CONF_PRIORITY = "priority"
CONF_ROOT_CLIENT = "ROOT_CLIENT"
CONF_EFFECT_HIDE_LIST = "effect_hide_list"
CONF_EFFECT_SHOW_LIST = "effect_show_list"
CONF_SYSINFO = "SYSINFO"

DEFAULT_NAME = "HyperHDR"
DEFAULT_ORIGIN = sanitize_hyperhdr_origin("Home Assistant")
DEFAULT_PORT_JSON = 19444
DEFAULT_PORT_UI = 8090
DEFAULT_PORT_WS = 8090
DEFAULT_PRIORITY = 128

DOMAIN = "hyperhdr"

HYPERHDR_MANUFACTURER_NAME = "HyperHDR"
HYPERHDR_MODEL_NAME = f"{HYPERHDR_MANUFACTURER_NAME}"
HYPERHDR_RELEASES_URL = "https://github.com/Shaffer-Softworks/hyperhdr-ha/releases"
HYPERHDR_VERSION_WARN_CUTOFF = "21.0.0.0"

NAME_SUFFIX_HYPERHDR_LIGHT = ""
NAME_SUFFIX_HYPERHDR_PRIORITY_LIGHT = "Priority"

SIGNAL_INSTANCE_ADD = f"{DOMAIN}_instance_add_signal.{{}}"
SIGNAL_INSTANCE_REMOVE = f"{DOMAIN}_instance_remove_signal.{{}}"
SIGNAL_ENTITY_REMOVE = f"{DOMAIN}_entity_remove_signal.{{}}"
SIGNAL_AVERAGE_COLOR = f"{DOMAIN}_average_color_signal.{{}}"

TYPE_HYPERHDR_LED_CAMERA = "hyperhdr_led_camera"
TYPE_HYPERHDR_LED_GRADIENT_CAMERA = "hyperhdr_led_gradient_camera"
TYPE_HYPERHDR_LIGHT = "hyperhdr_light"
TYPE_HYPERHDR_PRIORITY_LIGHT = "hyperhdr_priority_light"
TYPE_HYPERHDR_COMPONENT_SWITCH_BASE = "hyperhdr_component_switch"

TYPE_HYPERHDR_SENSOR_BASE = "hyperhdr_sensor"
TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY = "visible_priority"
TYPE_HYPERHDR_SENSOR_AVERAGE_COLOR = "average_color"
TYPE_HYPERHDR_NUMBER_BASE = "hyperhdr_number"
TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME = "smoothing_time"
TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY = "smoothing_decay"
TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ = "smoothing_update_freq"
TYPE_HYPERHDR_NUMBER_HDR_TONE_MAPPING = "hdr_tone_mapping"

TYPE_HYPERHDR_SELECT_BASE = "hyperhdr_select"
TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE = "smoothing_type"
