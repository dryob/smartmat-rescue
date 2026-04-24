"""Constants for the SmartMat Dashboard integration."""
from __future__ import annotations

DOMAIN = "smartmat_dashboard"
VERSION = "0.2.3"

# Config entry keys
CONF_WEIGHT_ENTITY = "weight_entity"
CONF_LAST_SEEN_ENTITY = "last_seen_entity"
CONF_SHORT_ID = "short_id"
CONF_PRODUCT_NAME = "product_name"

# Default values
DEFAULT_TARE = 0.0
DEFAULT_FULL = 1000.0
DEFAULT_PRODUCT_NAME = "未設定"

# Threshold entity IDs (shared across all mats - reused if they exist)
THRESHOLD_CRITICAL = "input_number.smartmat_threshold_critical"
THRESHOLD_LOW = "input_number.smartmat_threshold_low"
THRESHOLD_MID = "input_number.smartmat_threshold_mid"

# Default thresholds when input_number helpers don't exist
FALLBACK_CRITICAL = 10
FALLBACK_LOW = 33
FALLBACK_MID = 66

# Entity unique_id suffixes
UID_PRODUCT = "product"
UID_TARE = "tare"
UID_FULL = "full"
UID_INVENTORY = "inventory"

# Platforms provided
PLATFORMS = ["text", "number", "sensor"]

# Static card URL
CARD_URL = "/smartmat_dashboard/smartmat-card.js"
