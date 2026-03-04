"""Constants for the Tandoor Recipes integration."""

DOMAIN = "tandoor"
PLATFORMS = ["sensor"]

# Config keys
CONF_TANDOOR_URL = "tandoor_url"
CONF_API_TOKEN = "api_token"
CONF_SPACE_ID = "space_id"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ENABLE_BRING = "enable_bring"
CONF_BRING_ENTITY = "bring_entity"
CONF_AUTO_SYNC = "auto_sync"
CONF_ENABLE_BACKUP = "enable_backup"
CONF_PROXMOX_HOST = "proxmox_host"
CONF_CONTAINER_ID = "container_id"
CONF_SSH_USER = "ssh_user"
CONF_SSH_PASSWORD = "ssh_password"
CONF_SSH_KEY = "ssh_key"
CONF_ENABLE_VERSION_CHECK = "enable_version_check"
CONF_ENABLE_DOCKER_VERSION = "enable_docker_version"

# Defaults
DEFAULT_UPDATE_INTERVAL = 300
DEFAULT_SPACE_ID = 1
DEFAULT_PROXMOX_HOST = "192.168.178.88"
DEFAULT_CONTAINER_ID = 202
DEFAULT_SSH_USER = "root"

# API endpoints
API_MEAL_PLAN = "/api/meal-plan/"
API_SHOPPING = "/api/shopping-list-entry/"
GITHUB_RELEASES_URL = "https://api.github.com/repos/vabene1111/recipes/releases/latest"

# Sensor unique IDs
SENSOR_HEUTE = "tandoor_int_heute"
SENSOR_MORGEN = "tandoor_int_morgen"
SENSOR_UEBERMORGEN = "tandoor_int_uebermorgen"
SENSOR_NAECHSTE = "tandoor_int_naechste_gerichte"
SENSOR_ZUTATEN = "tandoor_int_zutaten"
SENSOR_INSTALLED_VERSION = "tandoor_int_installed_version"
SENSOR_LATEST_VERSION = "tandoor_int_latest_version"
SENSOR_UPDATE_STATUS = "tandoor_int_update_status"
SENSOR_BACKUP_STATUS = "tandoor_int_backup_status"

# Service names
SERVICE_LOAD = "load_from_tandoor"
SERVICE_SYNC = "sync_to_bring"
SERVICE_RESET = "reset_status"

# Internal state keys
DATA_COORDINATOR = "coordinator"
DATA_CONFIG = "config"
DATA_READY_TO_SYNC = "ready_to_sync"
DATA_BRING_ENTITY = "bring_entity"
