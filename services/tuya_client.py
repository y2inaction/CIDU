"""
Tuya Cloud API client — for FJ3395-TUYA (or similar) WiFi weather stations.

Handles:
  - Token acquisition (HMAC-SHA256 signed requests)
  - Token caching / auto-refresh
  - Fetching live device status (the 7-in-1 sensor array DPs)
  - Mapping raw Tuya "data points" (DPs) to readable weather values

Docs reference: https://developer.tuya.com/en/docs/cloud/
"""

import hashlib
import hmac
import time
import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

# ── Endpoint by data center ──────────────────────────────────────────────
# Pick the one matching where your Tuya Cloud Project was created.
ENDPOINTS = {
    "us":      "https://openapi.tuyaus.com",
    "eu":      "https://openapi.tuyaeu.com",
    "eu_west": "https://openapi-weaz.tuyaeu.com",
    "cn":      "https://openapi.tuyacn.com",
    "in":      "https://openapi.tuyain.com",
}

_token_cache = {"access_token": None, "expires_at": 0}


def _sign(client_id, secret, t, method="GET", path="", body="", token=""):
    """Tuya Cloud API signature (HMAC-SHA256)."""
    content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join([method, content_sha256, "", path])
    sign_str = client_id + token + t + string_to_sign
    sign = hmac.new(secret.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return sign


def _get_endpoint():
    return ENDPOINTS.get(Config.TUYA_DATA_CENTER, ENDPOINTS["eu"])


def _get_access_token():
    """Get a cached or fresh Tuya access token (valid ~2 hours)."""
    now = int(time.time() * 1000)
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60_000:
        return _token_cache["access_token"]

    if not Config.TUYA_CLIENT_ID or not Config.TUYA_CLIENT_SECRET:
        return None

    path = "/v1.0/token?grant_type=1"
    t = str(now)
    sign = _sign(Config.TUYA_CLIENT_ID, Config.TUYA_CLIENT_SECRET, t, "GET", path)

    headers = {
        "client_id": Config.TUYA_CLIENT_ID,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256",
    }
    try:
        r = requests.get(_get_endpoint() + path, headers=headers, timeout=10)
        d = r.json()
        if not d.get("success"):
            logger.error(f"Tuya token error: {d}")
            return None
        result = d["result"]
        _token_cache["access_token"] = result["access_token"]
        _token_cache["expires_at"] = now + result["expire_time"] * 1000
        return _token_cache["access_token"]
    except Exception as e:
        logger.error(f"Tuya token request failed: {e}")
        return None


def _signed_request(method, path, body=""):
    """Make an authenticated, signed request to Tuya Cloud."""
    token = _get_access_token()
    if not token:
        return None, "No Tuya access token (check TUYA_CLIENT_ID / TUYA_CLIENT_SECRET in .env)"

    now = int(time.time() * 1000)
    t = str(now)
    sign = _sign(Config.TUYA_CLIENT_ID, Config.TUYA_CLIENT_SECRET, t, method, path, body, token)

    headers = {
        "client_id": Config.TUYA_CLIENT_ID,
        "access_token": token,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256",
    }
    try:
        url = _get_endpoint() + path
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        else:
            headers["Content-Type"] = "application/json"
            r = requests.post(url, headers=headers, data=body, timeout=10)
        d = r.json()
        if not d.get("success"):
            return None, d.get("msg", str(d))
        return d.get("result"), None
    except Exception as e:
        return None, str(e)


def get_device_status(device_id):
    """
    Fetch live data-point (DP) status for a single device.
    Returns a dict like: {"temp_current": 285, "humidity_value": 62, ...}
    Tuya often reports temperature *10 and humidity as integer %.
    """
    result, err = _signed_request("GET", f"/v1.0/devices/{device_id}/status")
    if err:
        logger.warning(f"Tuya device {device_id} status error: {err}")
        return None, err
    # result is a list of {"code": "...", "value": ...}
    status = {item["code"]: item["value"] for item in result}
    return status, None


def get_device_info(device_id):
    """Fetch basic device info (name, online status, last active time)."""
    result, err = _signed_request("GET", f"/v1.0/devices/{device_id}")
    if err:
        return None, err
    return result, None


# ── DP code mapping for FJ3395 / generic 7-in-1 Tuya weather stations ─────
# NOTE: exact DP codes vary by firmware batch. Use the "Debug Device" tool
# in the Tuya IoT Platform (Cloud > Development > your project > Devices >
# select device > Device Debugging) to confirm YOUR station's exact codes,
# then adjust DP_MAP in config.py (TUYA_DP_MAP) if they differ.
DEFAULT_DP_MAP = {
    "temp_current":     "temp_current",      # outdoor temperature (x10, °C)
    "humidity_value":   "humidity_value",     # outdoor humidity (%)
    "rain_24h":         "rain_24h",           # 24h rainfall accumulation (x10, mm)
    "rain_rate":        "rain_rate",          # current rain rate (x10, mm/h)
    "windspeed_avg":    "windspeed_avg",      # wind speed (x10, m/s or km/h)
    "wind_direct":      "wind_direct",        # wind direction (degrees)
    "pressure":         "pressure",           # barometric pressure (hPa)
    "uv_index":         "uv_index",           # UV index
    "battery_state":    "battery_state",      # sensor battery status (enum, e.g. "low"/"high")
    "battery_percentage": "battery_percentage",  # some firmwares report a numeric % instead
    "signal_strength":  "signal_strength",    # WiFi/RF signal, if the firmware exposes it
}


def parse_station_reading(raw_status, dp_map=None):
    """
    Convert raw Tuya DP values into a normalized weather reading dict.
    Handles the common x10 scaling used by most Tuya weather DPs.
    """
    dp_map = dp_map or DEFAULT_DP_MAP
    if raw_status is None:
        return None

    def get(key, scale=1, default=None):
        code = dp_map.get(key)
        if code is None or code not in raw_status:
            return default
        val = raw_status[code]
        try:
            return round(val / scale, 2)
        except (TypeError, ValueError):
            return val

    battery_pct = get("battery_percentage", scale=1)
    if battery_pct is None:
        # Fall back to enum battery_state (e.g. "high"/"middle"/"low") → rough %
        state_map = {"high": 90, "middle": 55, "low": 15}
        raw_state = raw_status.get(dp_map.get("battery_state"))
        battery_pct = state_map.get(str(raw_state).lower()) if raw_state is not None else None

    reading = {
        "temperature_c":  get("temp_current", scale=10),
        "humidity_pct":   get("humidity_value", scale=1),
        "rainfall_24h_mm": get("rain_24h", scale=10, default=0),
        "rain_rate_mm_h": get("rain_rate", scale=10, default=0),
        "wind_speed":     get("windspeed_avg", scale=10),
        "wind_direction": get("wind_direct", scale=1),
        "pressure_hpa":   get("pressure", scale=1),
        "uv_index":       get("uv_index", scale=1),
        "battery_state":  raw_status.get(dp_map.get("battery_state"), None),
        "battery_level":  battery_pct,
        "signal_strength": get("signal_strength", scale=1),
    }
    # Sensor status: "ok" if the station returned at least temperature or rainfall,
    # since a live station with no core readings usually means a sensor fault.
    reading["sensor_status"] = "ok" if (reading["temperature_c"] is not None or
                                         reading["rainfall_24h_mm"] not in (None, 0)) else "fault"
    return reading


def get_device_health(device_id, dp_map=None):
    """
    Combined online/offline + last-active + live-reading health check for a
    single station. Used by the AWS Station Health tab and dashboard KPIs.
    Degrades gracefully (never raises) when Tuya isn't configured or the
    device is unreachable, so the dashboard always renders something useful.
    """
    if not Config.TUYA_CLIENT_ID or not Config.TUYA_CLIENT_SECRET:
        return {"online": None, "reading": None, "last_active": None,
                "error": "Tuya Cloud not configured (set TUYA_CLIENT_ID / TUYA_CLIENT_SECRET)"}

    info, info_err = get_device_info(device_id)
    online = None
    last_active = None
    if info and not info_err:
        online = info.get("online")
        ts = info.get("active_time") or info.get("update_time")
        if ts:
            try:
                last_active = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
            except (TypeError, ValueError):
                last_active = None

    raw, status_err = get_device_status(device_id)
    reading = parse_station_reading(raw, dp_map) if raw else None

    error = None
    if info_err and status_err:
        error = status_err or info_err
    elif online is False:
        error = "Device reports offline in Tuya Cloud"

    return {"online": online, "reading": reading, "last_active": last_active, "error": error}


def test_connection():
    """Quick connectivity / credentials test for the Reports tab."""
    if not Config.TUYA_CLIENT_ID or not Config.TUYA_CLIENT_SECRET:
        return {"ok": False, "message": "Tuya credentials not configured. Set TUYA_CLIENT_ID and TUYA_CLIENT_SECRET in .env"}
    token = _get_access_token()
    if not token:
        return {"ok": False, "message": "Could not obtain Tuya access token. Check credentials and data center region."}
    return {"ok": True, "message": f"Tuya Cloud connected successfully (data center: {Config.TUYA_DATA_CENTER})"}
