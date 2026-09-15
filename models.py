from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role          = db.Column(db.String(20),  nullable=False)
    state         = db.Column(db.String(60))
    lga           = db.Column(db.String(100))   # Extension Agents / Climate Champions
    cluster       = db.Column(db.String(100))   # FO cluster / community assignment
    supplier      = db.Column(db.String(120))   # AWS Supplier company name (role='aws_supplier')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Participant(db.Model):
    __tablename__ = "participants"
    id              = db.Column(db.Integer, primary_key=True)
    beneficiary_id  = db.Column(db.String(30), unique=True, index=True)
    full_name       = db.Column(db.String(120), nullable=False)
    gender          = db.Column(db.String(10))
    age_group       = db.Column(db.String(15))
    phone           = db.Column(db.String(15), unique=True, nullable=False, index=True)
    phone_alt       = db.Column(db.String(15))
    whatsapp_contact = db.Column(db.String(15))   # WhatsApp number (may differ from primary)
    extension_agent  = db.Column(db.String(120))  # assigned Extension Agent
    climate_champion = db.Column(db.String(120))  # assigned Climate Champion
    email           = db.Column(db.String(120))
    pwd_status      = db.Column(db.Boolean, default=False)
    role            = db.Column(db.String(20), nullable=False, index=True)
    business_name   = db.Column(db.String(120))
    state           = db.Column(db.String(60), nullable=False, index=True)
    lga             = db.Column(db.String(100), nullable=False, index=True)
    cluster         = db.Column(db.String(100))
    ward            = db.Column(db.String(100))
    village         = db.Column(db.String(100))
    address         = db.Column(db.Text)
    georef          = db.Column(db.String(60))
    primary_crop    = db.Column(db.String(50), index=True)
    secondary_crop  = db.Column(db.String(50))
    value_chain     = db.Column(db.String(50))
    farm_size_ha    = db.Column(db.Float)
    fo_group        = db.Column(db.String(120))
    aws_cluster     = db.Column(db.Boolean, default=True)
    language_pref   = db.Column(db.String(10), default="en")
    opted_in        = db.Column(db.Boolean, default=False)
    consent_date    = db.Column(db.Date)
    phone_verified  = db.Column(db.Boolean, default=False)
    verification_method = db.Column(db.String(30))
    verification_date   = db.Column(db.DateTime)
    cis_onboarded   = db.Column(db.Boolean, default=False)
    onboarding_date = db.Column(db.DateTime)
    registration_source = db.Column(db.String(50))
    data_protection_consent = db.Column(db.Boolean, default=False)
    status          = db.Column(db.String(20), default="Active")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by      = db.Column(db.String(80))
    logs = db.relationship("SMSLog", backref="participant", lazy=True)

class SMSLog(db.Model):
    __tablename__ = "sms_logs"
    id             = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participants.id"), nullable=False)
    message        = db.Column(db.Text, nullable=False)
    status         = db.Column(db.String(20), nullable=False)
    gateway_id     = db.Column(db.String(50))
    cost_kobo      = db.Column(db.Integer, default=0)
    sent_at        = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at   = db.Column(db.DateTime)

class WeatherCache(db.Model):
    __tablename__ = "weather_cache"
    id            = db.Column(db.Integer, primary_key=True)
    lga           = db.Column(db.String(100), nullable=False, index=True)
    forecast_date = db.Column(db.Date, nullable=False)
    rainfall_mm   = db.Column(db.Float)
    max_temp_c    = db.Column(db.Float)
    min_temp_c    = db.Column(db.Float)
    alert         = db.Column(db.String(200))
    source        = db.Column(db.String(20), default="forecast")
    humidity_pct  = db.Column(db.Float)
    wind_speed    = db.Column(db.Float)
    pressure_hpa  = db.Column(db.Float)
    fetched_at    = db.Column(db.DateTime, default=datetime.utcnow)

class WeatherStation(db.Model):
    __tablename__ = "weather_stations"
    id            = db.Column(db.Integer, primary_key=True)
    state         = db.Column(db.String(60), nullable=False, index=True)
    lga           = db.Column(db.String(100), nullable=False, index=True)
    device_id     = db.Column(db.String(60), unique=True, nullable=False)
    device_name   = db.Column(db.String(120))
    supplier      = db.Column(db.String(120), default="Green Allied Nigeria Limited")
    status        = db.Column(db.String(20), default="active")   # active / pending / offline / retired
    is_online     = db.Column(db.Boolean, default=None)           # last-known reachability
    last_seen     = db.Column(db.DateTime)                        # last time we got ANY reading
    battery_level = db.Column(db.Integer)                         # % (if device reports it)
    signal_strength = db.Column(db.Integer)                       # % or dBm-derived, best-effort
    sensor_status = db.Column(db.String(20))                      # ok / fault / unknown
    last_error    = db.Column(db.String(200))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProgrammeLGA(db.Model):
    __tablename__ = "programme_lgas"
    id            = db.Column(db.Integer, primary_key=True)
    state         = db.Column(db.String(60), nullable=False, index=True)
    lga           = db.Column(db.String(100), nullable=False)
    added_by      = db.Column(db.String(80))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('state', 'lga', name='uq_state_lga'),)

class Template(db.Model):
    __tablename__ = "templates"
    id                       = db.Column(db.Integer, primary_key=True)
    language                 = db.Column(db.String(10), nullable=False)
    crop                     = db.Column(db.String(50), nullable=False)
    content                  = db.Column(db.Text, nullable=False)
    english_content          = db.Column(db.Text)
    hausa_content            = db.Column(db.Text)
    igbo_content             = db.Column(db.Text)
    yoruba_content           = db.Column(db.Text)
    pidgin_content           = db.Column(db.Text)
    nupe_content             = db.Column(db.Text)
    
    # Extended template fields (up to 306 chars / 2 SMS pages)
    message_type             = db.Column(db.String(50))  # alert, advisory, general, training
    action_oriented_text     = db.Column(db.Text)  # "What to do" component
    severity_level           = db.Column(db.String(20))  # critical, high, medium, low
    character_count_english  = db.Column(db.Integer)
    character_count_hausa    = db.Column(db.Integer)
    character_count_igbo     = db.Column(db.Integer)
    character_count_yoruba   = db.Column(db.Integer)
    character_count_pidgin   = db.Column(db.Integer)
    character_count_nupe     = db.Column(db.Integer)
    
    created_at               = db.Column(db.DateTime, default=datetime.utcnow)

class DashboardMetric(db.Model):
    __tablename__ = "dashboard_metrics"
    id           = db.Column(db.Integer, primary_key=True)
    metric_name  = db.Column(db.String(50), nullable=False, index=True)
    metric_value = db.Column(db.Integer, default=0)
    state        = db.Column(db.String(60))
    lga          = db.Column(db.String(100))
    recorded_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# ═════════════════════════════════════════════════════════════════════════
# CLIMATE INFORMATION SERVICE - ENHANCED FEATURES
# Including: Climate Champions, Adoption Tracking, NiMet Integration
# ═════════════════════════════════════════════════════════════════════════

# CLIMATE CHAMPIONS - Community-level multipliers (trained by SPMU)
class ClimateChampion(db.Model):
    """
    Climate Champion: Extension Agent, Lead Farmer, or trained community member
    Managed by SPMU within their prospecting state
    Serves as community-level multiplier for climate information dissemination
    """
    __tablename__ = 'climate_champion'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), unique=True, nullable=False)
    
    # ═══ State Assignment ═══
    state = db.Column(db.String(50), nullable=False, index=True)  # SPMU manages champions within their state
    lga = db.Column(db.String(50), nullable=False)
    
    # ═══ Champion Type ═══
    champion_type = db.Column(db.String(30))  # 'extension_agent', 'lead_farmer', 'community_member'
    
    # ═══ Enrollment (by SPMU) ═══
    enrollment_date = db.Column(db.DateTime, default=datetime.utcnow)
    enrollment_status = db.Column(db.String(20), default='active')  # active, inactive, suspended
    enrolled_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # SPMU user
    
    # ═══ Training & Capacity Strengthening ═══
    training_date = db.Column(db.DateTime)
    training_status = db.Column(db.String(20))  # not_started, in_progress, completed
    training_topics_completed = db.Column(db.String(200))  # CSV: climate_basics, forecasting, sms_messaging, etc
    certification_date = db.Column(db.DateTime)
    certification_number = db.Column(db.String(50))  # e.g., "CIDU-CC-2026-001"
    
    # ═══ Multiplier Effect ═══
    farmers_reached = db.Column(db.Integer, default=0)  # Direct reach as community multiplier
    sms_forwarded = db.Column(db.Integer, default=0)  # Climate info forwarded to WhatsApp/local groups
    training_sessions_conducted = db.Column(db.Integer, default=0)
    
    # ═══ Community Engagement ═══
    last_activity_date = db.Column(db.DateTime)
    engagement_notes = db.Column(db.Text)  # SPMU notes on champion performance
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    participant = db.relationship('Participant', backref='champion_profile')
    enrolled_by = db.relationship('User', backref='champions_managed')
    
    def __repr__(self):
        return f'<ClimateChampion {self.id} - {self.state} {self.champion_type}>'


# ADOPTION & RETENTION TRACKING
class FarmerAdoption(db.Model):
    """
    Tracks farmer adoption of climate information (via SMS and Champions)
    Measures: Enrollment → First SMS → Engagement → Retention → Behavior Change
    """
    __tablename__ = 'farmer_adoption'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), unique=True, nullable=False)
    
    # ═══ Enrollment ═══
    enrollment_date = db.Column(db.DateTime)
    enrollment_source = db.Column(db.String(50))  # 'sms_response', 'champion_referral', 'agent', 'office'
    referred_by_champion_id = db.Column(db.Integer, db.ForeignKey('climate_champion.id'))
    
    # ═══ SMS Engagement ═══
    first_sms_received = db.Column(db.DateTime)
    days_to_first_sms = db.Column(db.Integer)
    sms_received_count = db.Column(db.Integer, default=0)
    last_sms_date = db.Column(db.DateTime)
    
    # ═══ Information Dissemination Success ═══
    messages_opened = db.Column(db.Integer, default=0)  # Estimated based on delivery confirmation
    whatsapp_group_joined = db.Column(db.Boolean, default=False)  # Multi-channel approach
    
    # ═══ Behavioral Adoption ═══
    behavior_changes_logged = db.Column(db.Integer, default=0)
    last_behavior_change_date = db.Column(db.DateTime)
    
    # ═══ Retention Status ═══
    days_since_last_sms = db.Column(db.Integer)
    retention_status = db.Column(db.String(20), default='pending')  # pending, active, at_risk, inactive, churned
    
    # ═══ Engagement Scoring ═══
    engagement_score = db.Column(db.Integer, default=0)  # 0-100
    
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    participant = db.relationship('Participant', backref='adoption_profile')
    
    def __repr__(self):
        return f'<FarmerAdoption {self.participant_id} - {self.retention_status}>'


class BehaviorChangeLog(db.Model):
    """
    Logs documented behavior changes from climate information adoption
    Champions/Agents report when farmers change farming practices based on CIDU alerts
    """
    __tablename__ = 'behavior_change_log'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False, index=True)
    
    # ═══ SMS Context ═══
    alert_type = db.Column(db.String(50))  # 'heavy_rain', 'drought', 'heat_wave', 'cold_snap', 'pest_alert'
    alert_date = db.Column(db.DateTime)
    
    # ═══ Behavior Change ═══
    behavior_description = db.Column(db.Text)  # "Delayed fertilizer by 3 days after rain alert"
    practice_changed = db.Column(db.String(100))  # 'planting_date', 'fertilizer_timing', 'irrigation', 'pest_mgmt'
    estimated_benefit = db.Column(db.String(200))  # "Saved 15% crop yield", "Reduced pest damage"
    
    # ═══ Verification ═══
    reported_date = db.Column(db.DateTime, default=datetime.utcnow)
    reported_by = db.Column(db.String(100))  # Champion/Agent name
    reported_by_champion_id = db.Column(db.Integer, db.ForeignKey('climate_champion.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    participant = db.relationship('Participant', backref='behavior_changes')
    
    def __repr__(self):
        return f'<BehaviorChange {self.participant_id} - {self.alert_type}>'


# NiMET PARTNERSHIP - Nigerian Meteorological Agency forecasts
class NiMetForecast(db.Model):
    """
    NiMet data integration: credible, localized seasonal and short-term forecasts
    Scientific backbone for all climate information service messaging
    Fetched twice daily (6 AM & 6 PM WAT)
    """
    __tablename__ = 'nimet_forecast'
    
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(50), nullable=False, index=True)
    lga = db.Column(db.String(50), index=True)
    forecast_date = db.Column(db.Date, nullable=False)
    
    # ═══ NiMet Source Data ═══
    nimet_forecast_json = db.Column(db.Text)
    nimet_confidence_level = db.Column(db.String(20))  # high, medium, low
    nimet_issued_date = db.Column(db.DateTime)
    nimet_source_status = db.Column(db.String(20))  # success, failed, timeout
    
    # ═══ Parsed Forecast Data ═══
    temperature_min = db.Column(db.Float)
    temperature_max = db.Column(db.Float)
    rainfall_expected = db.Column(db.Float)
    rainfall_probability = db.Column(db.Float)  # NiMet confidence %
    wind_speed = db.Column(db.Float)
    humidity = db.Column(db.Float)
    
    # ═══ Local Station Cross-validation ═══
    station_temperature = db.Column(db.Float)
    station_rainfall = db.Column(db.Float)
    variance_detected = db.Column(db.Boolean)
    variance_notes = db.Column(db.String(200))
    
    # ═══ Action-oriented Advisory ═══
    advisory_text = db.Column(db.Text)  # What to do? (farmer-actionable)
    advisory_languages = db.Column(db.String(100))  # CSV: English, Hausa, Nupe, Pidgin
    advisory_status = db.Column(db.String(20))  # pending, sent, failed
    
    # ═══ Message Dissemination ═══
    sms_sent_date = db.Column(db.DateTime)
    sms_delivery_count = db.Column(db.Integer, default=0)
    sms_failed_count = db.Column(db.Integer, default=0)
    whatsapp_sent = db.Column(db.Boolean, default=False)  # Multi-channel: SMS + WhatsApp
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_state_date', 'state', 'forecast_date'),
        db.Index('idx_advisory_status', 'advisory_status'),
    )
    
    def __repr__(self):
        return f'<NiMetForecast {self.state} {self.forecast_date}>'


# ═════════════════════════════════════════════════════════════════════════
# IFAD RECOMMENDATIONS — Feedback, Field Reports & Adoption Tracking
# ═════════════════════════════════════════════════════════════════════════

class FieldReport(db.Model):
    """
    Extension Agent / Climate Champion field report.
    Captures reach, advisory delivery, and — per IFAD adoption-tracking
    recommendation — how many farmers actually followed the advice given.
    """
    __tablename__ = "field_reports"
    id                  = db.Column(db.Integer, primary_key=True)
    submitted_by_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role_at_submission  = db.Column(db.String(20))     # extension_agent / climate_champion / spmu
    state               = db.Column(db.String(60), nullable=False, index=True)
    lga                 = db.Column(db.String(100), nullable=False, index=True)
    cluster             = db.Column(db.String(100))
    report_date         = db.Column(db.Date, nullable=False, default=date.today)
    farmers_reached     = db.Column(db.Integer, default=0)
    advisory_delivered  = db.Column(db.Boolean, default=True)
    farmers_adopted     = db.Column(db.Integer, default=0)
    farmers_partial     = db.Column(db.Integer, default=0)
    farmers_not_adopted = db.Column(db.Integer, default=0)
    activities_notes    = db.Column(db.Text)
    challenges_notes    = db.Column(db.Text)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_by = db.relationship("User", backref="field_reports")

    @property
    def adoption_rate_pct(self):
        total = (self.farmers_adopted or 0) + (self.farmers_partial or 0) + (self.farmers_not_adopted or 0)
        if not total: return None
        return round(((self.farmers_adopted or 0) + 0.5*(self.farmers_partial or 0)) / total * 100, 1)


class AdvisoryFeedback(db.Model):
    """
    Farmer feedback: "Was this advisory useful?" — IFAD recommendation.
    Captured either directly (public weather portal / SMS keyword reply)
    or logged by an Extension Agent / Climate Champion during a field visit.
    """
    __tablename__ = "advisory_feedback"
    id            = db.Column(db.Integer, primary_key=True)
    state         = db.Column(db.String(60), nullable=False, index=True)
    lga           = db.Column(db.String(100), index=True)
    channel       = db.Column(db.String(20))
    farmer_name   = db.Column(db.String(120))
    farmer_phone  = db.Column(db.String(20))
    useful        = db.Column(db.Boolean, nullable=False)
    comment       = db.Column(db.Text)
    logged_by_id  = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    logged_by = db.relationship("User", backref="feedback_logged")
