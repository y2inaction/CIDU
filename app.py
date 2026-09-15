from flask import Flask
from config import Config
from models import db
from flask_migrate import Migrate
from flask_login import LoginManager
from routes.api import api
from routes.auth import auth, register_cli
import logging, os

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    db.init_app(app)
    Migrate(app, db)
    lm = LoginManager()
    lm.init_app(app)
    lm.login_view = "auth.login"
    lm.login_message = "Please sign in to access the VCDP CIDU dashboard."
    @lm.user_loader
    def load_user(uid):
        from models import User
        return User.query.get(int(uid))
    app.register_blueprint(auth)
    app.register_blueprint(api)
    register_cli(app)
    with app.app_context():
        db.create_all()
        _ensure_columns()
        _seed_templates()
        _seed_admins()
        _seed_stations()
        _seed_lgas()
        from services.weather_api import load_lga_coordinates
        load_lga_coordinates()
    if os.getenv("FLASK_ENV") != "testing" and os.getenv("NO_SCHEDULER") != "1":
        try:
            from services.scheduler import init_scheduler
            init_scheduler(app)
        except Exception as e:
            logger.warning(f"Scheduler not started: {e}")
    return app

def _ensure_columns():
    """Lightweight auto-migration: add new columns to existing databases
    (SQLite & MySQL safe — ignores 'already exists')."""
    from sqlalchemy import text
    migrations = (
        ("users",            "lga",              "VARCHAR(100)"),
        ("users",            "cluster",          "VARCHAR(100)"),
        ("users",            "supplier",         "VARCHAR(120)"),
        ("participants",     "whatsapp_contact", "VARCHAR(15)"),
        ("participants",     "extension_agent",  "VARCHAR(120)"),
        ("participants",     "climate_champion", "VARCHAR(120)"),
        ("weather_stations", "supplier",         "VARCHAR(120)"),
        ("weather_stations", "is_online",        "BOOLEAN"),
        ("weather_stations", "battery_level",    "INTEGER"),
        ("weather_stations", "signal_strength",  "INTEGER"),
        ("weather_stations", "sensor_status",    "VARCHAR(20)"),
        ("weather_stations", "last_error",       "VARCHAR(200)"),
        ("weather_stations", "updated_at",       "DATETIME"),
    )
    for table, col, ddl in migrations:
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            db.session.commit()
            logger.info(f"{table} table: added column '{col}'")
        except Exception:
            db.session.rollback()  # column already exists

def _seed_templates():
    from models import Template
    from seeds.templates import seed_all_templates
    n = seed_all_templates(db, Template)
    if n: logger.info(f"Seeded {n} SMS templates")

def _seed_admins():
    from models import User
    from seeds.admin_accounts import seed_admins
    n = seed_admins(db, User)
    if n: logger.info(f"Seeded {n} admin accounts")

def _seed_stations():
    from models import WeatherStation
    from seeds.weather_stations import seed_weather_stations
    n = seed_weather_stations(db, WeatherStation)
    if n: logger.info(f"Seeded {n} weather stations")

def _seed_lgas():
    from models import ProgrammeLGA
    from seeds.programme_lgas import seed_programme_lgas
    n = seed_programme_lgas(db, ProgrammeLGA)
    if n: logger.info(f"Seeded {n} programme LGAs")

# cPanel / Passenger WSGI compatibility
application = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV","production") == "development"
    logger.info(f"VCDP CIDU starting on http://localhost:{port}")
    logger.info("Login: npmu_admin / VCDP@Npmu2026!")
    application.run(host="0.0.0.0", port=port, debug=debug)
