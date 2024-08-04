"""Constants for HyperHDR integration."""

CONF_AUTH_ID = "auth_id"
CONF_CREATE_TOKEN = "create_token"
CONF_INSTANCE = "instance"
CONF_INSTANCE_CLIENTS = "INSTANCE_CLIENTS"
CONF_ON_UNLOAD = "ON_UNLOAD"
CONF_PRIORITY = "priority"
CONF_ROOT_CLIENT = "ROOT_CLIENT"
CONF_EFFECT_HIDE_LIST = "effect_hide_list"
CONF_EFFECT_SHOW_LIST = "effect_show_list"

DEFAULT_NAME = "HyperHDR"
DEFAULT_ORIGIN = "Home Assistant"
DEFAULT_PRIORITY = 128

DOMAIN = "hyperhdr"

HYPERHDR_MANUFACTURER_NAME = "HyperHDR"
HYPERHDR_MODEL_NAME = f"{HYPERHDR_MANUFACTURER_NAME}"
HYPERHDR_RELEASES_URL = "https://github.com/awawa-dev/HyperHDR/releases"
HYPERHDR_VERSION_WARN_CUTOFF = "20.0.0.0"

NAME_SUFFIX_HYPERHDR_LIGHT = ""
NAME_SUFFIX_HYPERHDR_PRIORITY_LIGHT = "Priority"

SIGNAL_INSTANCE_ADD = f"{DOMAIN}_instance_add_signal.{{}}"
SIGNAL_INSTANCE_REMOVE = f"{DOMAIN}_instance_remove_signal.{{}}"
SIGNAL_ENTITY_REMOVE = f"{DOMAIN}_entity_remove_signal.{{}}"

TYPE_HYPERHDR_CAMERA = "hyperhdr_camera"
TYPE_HYPERHDR_LIGHT = "hyperhdr_light"
TYPE_HYPERHDR_PRIORITY_LIGHT = "hyperhdr_priority_light"
TYPE_HYPERHDR_COMPONENT_SWITCH_BASE = "hyperhdr_component_switch"

TYPE_HYPERHDR_SENSOR_BASE = "hyperhdr_sensor"
TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY = "visible_priority"
