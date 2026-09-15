import requests, csv, os, logging
from datetime import date, datetime
from models import db, WeatherCache, WeatherStation
from config import Config
from services import tuya_client

logger = logging.getLogger(__name__)
LGA_COORDS = {}


def load_lga_coordinates():
    global LGA_COORDS
    csv_path = os.path.join(os.path.dirname(__file__), "..", "seeds", "lga_coordinates.csv")
    if not os.path.exists(csv_path):
        logger.warning("lga_coordinates.csv not found")
        return
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = f"{row['state'].strip().lower()},{row['lga'].strip().lower()}"
            LGA_COORDS[key] = (float(row["lat"]), float(row["lon"]))
    logger.info(f"Loaded {len(LGA_COORDS)} LGA coordinates")


def _station_key(state, lga):
    return f"{state.strip().lower()},{lga.strip().lower()}"


def get_station_for_lga(state, lga):
    """Return the active WeatherStation for this state/LGA, or None."""
    return WeatherStation.query.filter_by(
        state=state, lga=lga, status="active"
    ).first()


def _alert_from_readings(rainfall_mm, max_temp_c):
    if rainfall_mm is not None and rainfall_mm > 20:
        return "Heavy rain expected. Secure crops and clear field drains."
    if rainfall_mm is not None and rainfall_mm > 10:
        return "Moderate rain expected. Plan field activities carefully."
    if max_temp_c is not None and max_temp_c > 35:
        return "High temperature alert. Ensure adequate irrigation."
    return "Favorable weather conditions."


def _fetch_from_station(station):
    """Pull live readings from a Tuya FJ3395 weather station device."""
    raw, err = tuya_client.get_device_status(station.device_id)
    if err:
        logger.warning(f"Tuya station {station.device_id} ({station.lga}) error: {err}")
        station.status = "offline"
        db.session.commit()
        return None

    reading = tuya_client.parse_station_reading(raw)
    if reading is None:
        return None

    station.status = "active"
    station.last_seen = datetime.utcnow()
    db.session.commit()
    return reading


def get_weather_for_lga(state, lga):
    """
    Returns a WeatherCache-like object with current conditions for the LGA.
    Priority: live Tuya station reading (if configured & online) -> Open-Meteo forecast.
    Cached for Config.TUYA_CACHE_SECONDS (stations) / 3600s (forecast) to limit API calls.
    """
    if not LGA_COORDS:
        load_lga_coordinates()

    today = date.today()
    lga_key = lga.strip().lower()
    cached = WeatherCache.query.filter_by(lga=lga_key, forecast_date=today).first()

    # ── 1. Try live station first ────────────────────────────────────────
    station = get_station_for_lga(state, lga)
    if station:
        cache_age = (datetime.utcnow() - cached.fetched_at).total_seconds() if cached else 999999
        if cached and cached.source == "station" and cache_age < Config.TUYA_CACHE_SECONDS:
            return cached  # fresh enough, reuse

        reading = _fetch_from_station(station)
        if reading is not None:
            rainfall = reading.get("rainfall_24h_mm", 0) or 0
            max_temp = reading.get("temperature_c")
            alert = _alert_from_readings(rainfall, max_temp)

            if cached:
                cached.rainfall_mm  = rainfall
                cached.max_temp_c   = max_temp
                cached.min_temp_c   = max_temp
                cached.humidity_pct = reading.get("humidity_pct")
                cached.wind_speed   = reading.get("wind_speed")
                cached.pressure_hpa = reading.get("pressure_hpa")
                cached.alert        = alert
                cached.source       = "station"
                cached.fetched_at   = datetime.utcnow()
                w = cached
            else:
                w = WeatherCache(
                    lga=lga_key, forecast_date=today,
                    rainfall_mm=rainfall, max_temp_c=max_temp, min_temp_c=max_temp,
                    humidity_pct=reading.get("humidity_pct"),
                    wind_speed=reading.get("wind_speed"),
                    pressure_hpa=reading.get("pressure_hpa"),
                    alert=alert, source="station",
                )
                db.session.add(w)
            db.session.commit()
            return w
        # station offline -> fall through to forecast below

    # ── 2. Cached forecast still fresh? ─────────────────────────────────
    if cached and cached.source == "forecast" and (datetime.utcnow() - cached.fetched_at).seconds < 3600:
        return cached

    # ── 3. Open-Meteo forecast fallback ─────────────────────────────────
    key = _station_key(state, lga)
    coords = LGA_COORDS.get(key)
    if not coords:
        key2 = f"{state.strip().lower().replace(' state','')},{lga.strip().lower()}"
        coords = LGA_COORDS.get(key2)
    if not coords:
        logger.warning(f"No coords for '{state}','{lga}' — using generic advisory")
        if cached:
            return cached
        return _generic_advisory(lga_key, today)

    lat, lon = coords
    url = (f"{Config.WEATHER_API_BASE}?latitude={lat}&longitude={lon}"
           f"&daily=precipitation_sum,temperature_2m_max,temperature_2m_min&timezone=Africa%2FLagos")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        daily = r.json().get("daily", {})
        rainfall = (daily.get("precipitation_sum") or [0])[0]
        max_temp = (daily.get("temperature_2m_max") or [0])[0]
        min_temp = (daily.get("temperature_2m_min") or [0])[0]
        alert = _alert_from_readings(rainfall, max_temp)

        if cached:
            cached.rainfall_mm = rainfall
            cached.max_temp_c  = max_temp
            cached.min_temp_c  = min_temp
            cached.alert       = alert
            cached.source      = "forecast"
            cached.fetched_at  = datetime.utcnow()
            w = cached
        else:
            w = WeatherCache(lga=lga_key, forecast_date=today,
                rainfall_mm=rainfall, max_temp_c=max_temp, min_temp_c=min_temp,
                alert=alert, source="forecast")
            db.session.add(w)
        db.session.commit()
        return w
    except Exception as e:
        logger.error(f"Weather API error {state}/{lga}: {e} — using generic advisory")
        if cached:
            return cached
        return _generic_advisory(lga_key, today)


def _generic_advisory(lga_key, today):
    """
    Transient (not persisted) fallback used when neither a live station nor
    Open-Meteo is reachable. Ensures SMS dispatch is never blocked by an
    external API or network outage — beneficiaries still get a useful,
    general-purpose advisory.
    """
    return WeatherCache(
        lga=lga_key, forecast_date=today,
        rainfall_mm=0, max_temp_c=None, min_temp_c=None,
        alert="Weather update unavailable today — please follow local conditions and plan farm activities carefully.",
        source="fallback",
    )
