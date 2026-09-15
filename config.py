import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    SECRET_KEY               = os.getenv("SECRET_KEY", "vcdp-dev-key-2026")
    SQLALCHEMY_DATABASE_URI  = os.getenv("DATABASE_URL", "sqlite:///vcdp_cis.db")
    MAX_CONTENT_LENGTH       = 25 * 1024 * 1024  # 25 MB upload limit (CSV imports)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SMS_API_KEY    = os.getenv("TERMII_API_KEY", "")
    SMS_SENDER_ID  = os.getenv("SENDER_ID", "VCDP")
    SMS_API_URL    = "https://api.ng.termii.com/api/sms/send"
    SMS_COST_KOBO  = int(os.getenv("SMS_COST_KOBO", 600))
    WEATHER_API_BASE = os.getenv("WEATHER_API_BASE", "https://api.open-meteo.com/v1/forecast")
    REFRESH_INTERVAL = int(os.getenv("DASHBOARD_REFRESH_INTERVAL", 30))

    # ── Tuya Cloud — FJ3395 / 7-in-1 WiFi weather stations ──────────────
    TUYA_CLIENT_ID     = os.getenv("TUYA_CLIENT_ID", "")
    TUYA_CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET", "")
    TUYA_DATA_CENTER   = os.getenv("TUYA_DATA_CENTER", "eu")  # eu / us / cn / in
    # Cache window before re-polling a station (seconds)
    TUYA_CACHE_SECONDS = int(os.getenv("TUYA_CACHE_SECONDS", 600))

    VALID_STATES = [
        "Anambra State","Benue State","Ebonyi State","Enugu State",
        "Kogi State","Nasarawa State","Niger State","Ogun State","Taraba State"
    ]
    # DEPRECATED — kept only as the one-time seed data for the database-backed
    # ProgrammeLGA table (see seeds/programme_lgas.py). LGAs are now managed
    # live by Owner/NPMU through the "Manage LGAs" screen in the dashboard —
    # editing this dict after first boot has NO EFFECT on the running system.
    STATE_LGAS = {
        "Anambra State":  sorted(["Aguata","Anaocha","Awka North","Awka South","Ayamelum",
                           "Dunukofia","Idemili North","Idemili South","Ihiala","Njikoka",
                           "Nnewi North","Nnewi South","Ogbaru","Onitsha North","Onitsha South",
                           "Orumba North","Orumba South","Oyi"]),
        "Benue State":    ["Gwer East","Logo","Vandeikya"],
        "Ebonyi State":   ["Abakaliki","Afikpo South","Ikwo"],
        "Enugu State":    ["Enugu","Udenu"],
        "Kogi State":     ["Ajaokuta","Kabba/Bunu","Olamaboro"],
        "Nasarawa State": ["Doma","Lafia"],
        "Niger State":    ["Bida","Edati","Kontagora","Mokwa"],
        "Ogun State":     sorted(["Abeokuta North","Abeokuta South","Ado-Odo/Ota","Egbado North",
                           "Egbado South","Ewekoro","Ifo","Ijebu East","Ijebu North","Ijebu Ode",
                           "Obafemi Owode","Odeda","Sagamu"]),
        "Taraba State":   ["Karim Lamido","Wukari"],
    }
    VALID_CATEGORIES = ["Producer","Processor","Marketer"]
    VALID_ROLES      = ["producer","processor","marketer"]
    # VCDP value chain crops only
    VALID_CROPS      = ["Rice","Cassava"]
    # Simplified two-band age grouping for analytics
    VALID_AGE_GROUPS = ["15-35","35-Above"]
    VALID_GENDERS    = ["Male","Female"]
    VALID_LANGUAGES  = ["en","ha","ig","yo","pcm","nup"]
    VALID_REG_SOURCES= ["Field Agent","Self-Registration","FO Group","SPMU Upload","Other"]
