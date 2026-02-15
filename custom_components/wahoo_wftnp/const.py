"""Constants for the Wahoo Kickr Core integration."""

DOMAIN = "wahoo_wftnp"
NAME = "Wahoo Fitness TNP"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_ADDRESS = "address"
CONF_SLEEP_TIMEOUT = "sleep_timeout"
CONF_LAST_SEEN_INTERVAL = "last_seen_interval"
CONF_UPDATE_THROTTLE = "update_throttle"

DEFAULT_PORT = 5555
DEFAULT_SLEEP_TIMEOUT = 10
DEFAULT_LAST_SEEN_INTERVAL = 60
DEFAULT_UPDATE_THROTTLE = 0

SERVICE_SET_ERG_WATTS = "set_erg_watts"
SERVICE_SET_GRADE = "set_grade"
SERVICE_REQUEST_CONTROL = "request_control"
SERVICE_RESET = "reset"
SERVICE_START_TRAINING = "start_training"
SERVICE_STOP_TRAINING = "stop_training"
