-- ═══════════════════════════════════════════════════════════════════════
-- VCDP CLIMATE INFORMATION SERVICE - Database Migrations
-- Powered by NiMet Partnership & Community Climate Champions
-- ═══════════════════════════════════════════════════════════════════════

-- ═══ ENHANCED SMS TEMPLATES (Multi-language, Action-oriented, up to 306 chars) ═══
ALTER TABLE templates ADD COLUMN IF NOT EXISTS english_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS hausa_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS igbo_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS yoruba_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS pidgin_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS nupe_content TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS message_type VARCHAR(50);
ALTER TABLE templates ADD COLUMN IF NOT EXISTS action_oriented_text TEXT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS severity_level VARCHAR(20);
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_english INT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_hausa INT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_igbo INT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_yoruba INT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_pidgin INT;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS character_count_nupe INT;

-- ═══ CLIMATE CHAMPIONS - Community-level multipliers (managed by SPMU) ═══
CREATE TABLE IF NOT EXISTS climate_champion (
    id INT PRIMARY KEY AUTO_INCREMENT,
    participant_id INT NOT NULL UNIQUE,
    
    state VARCHAR(50) NOT NULL,
    lga VARCHAR(50) NOT NULL,
    champion_type VARCHAR(30),
    
    enrollment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    enrollment_status VARCHAR(20) DEFAULT 'active',
    enrolled_by_user_id INT,
    
    training_date DATETIME,
    training_status VARCHAR(20),
    training_topics_completed VARCHAR(200),
    certification_date DATETIME,
    certification_number VARCHAR(50),
    
    farmers_reached INT DEFAULT 0,
    sms_forwarded INT DEFAULT 0,
    training_sessions_conducted INT DEFAULT 0,
    
    last_activity_date DATETIME,
    engagement_notes TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (enrolled_by_user_id) REFERENCES users(id),
    INDEX idx_state_type (state, champion_type),
    INDEX idx_enrollment_status (enrollment_status)
);

-- ═══ FARMER ADOPTION TRACKING ═══
CREATE TABLE IF NOT EXISTS farmer_adoption (
    id INT PRIMARY KEY AUTO_INCREMENT,
    participant_id INT NOT NULL UNIQUE,
    
    enrollment_date DATETIME,
    enrollment_source VARCHAR(50),
    referred_by_champion_id INT,
    
    first_sms_received DATETIME,
    days_to_first_sms INT,
    sms_received_count INT DEFAULT 0,
    last_sms_date DATETIME,
    
    messages_opened INT DEFAULT 0,
    whatsapp_group_joined BOOLEAN DEFAULT FALSE,
    
    behavior_changes_logged INT DEFAULT 0,
    last_behavior_change_date DATETIME,
    
    days_since_last_sms INT,
    retention_status VARCHAR(20) DEFAULT 'pending',
    engagement_score INT DEFAULT 0,
    
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (referred_by_champion_id) REFERENCES climate_champion(id),
    INDEX idx_retention_status (retention_status),
    INDEX idx_engagement_score (engagement_score)
);

-- ═══ BEHAVIOR CHANGE LOGGING ═══
CREATE TABLE IF NOT EXISTS behavior_change_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    participant_id INT NOT NULL,
    
    alert_type VARCHAR(50),
    alert_date DATETIME,
    
    behavior_description TEXT,
    practice_changed VARCHAR(100),
    estimated_benefit VARCHAR(200),
    
    reported_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    reported_by VARCHAR(100),
    reported_by_champion_id INT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (participant_id) REFERENCES participants(id),
    FOREIGN KEY (reported_by_champion_id) REFERENCES climate_champion(id),
    INDEX idx_alert_type (alert_type),
    INDEX idx_reported_date (reported_date)
);

-- ═══ NiMET PARTNERSHIP - Localized forecasts as scientific backbone ═══
CREATE TABLE IF NOT EXISTS nimet_forecast (
    id INT PRIMARY KEY AUTO_INCREMENT,
    state VARCHAR(50) NOT NULL,
    lga VARCHAR(50),
    forecast_date DATE NOT NULL,
    
    nimet_forecast_json LONGTEXT,
    nimet_confidence_level VARCHAR(20),
    nimet_issued_date DATETIME,
    nimet_source_status VARCHAR(20),
    
    temperature_min FLOAT,
    temperature_max FLOAT,
    rainfall_expected FLOAT,
    rainfall_probability FLOAT,
    wind_speed FLOAT,
    humidity FLOAT,
    
    station_temperature FLOAT,
    station_rainfall FLOAT,
    variance_detected BOOLEAN,
    variance_notes VARCHAR(200),
    
    advisory_text LONGTEXT,
    advisory_languages VARCHAR(100),
    advisory_status VARCHAR(20),
    
    sms_sent_date DATETIME,
    sms_delivery_count INT DEFAULT 0,
    sms_failed_count INT DEFAULT 0,
    whatsapp_sent BOOLEAN DEFAULT FALSE,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_state_date (state, forecast_date),
    INDEX idx_advisory_status (advisory_status),
    INDEX idx_nimet_status (nimet_source_status)
);

-- ═══════════════════════════════════════════════════════════════════════
-- Verification Queries
-- ═══════════════════════════════════════════════════════════════════════

-- SHOW TABLES LIKE 'climate_champion';
-- SHOW TABLES LIKE 'farmer_adoption';
-- SHOW TABLES LIKE 'behavior_change_log';
-- SHOW TABLES LIKE 'nimet_forecast';
-- DESCRIBE climate_champion;
-- DESCRIBE nimet_forecast;

-- ═══════════════════════════════════════════════════════════════════════
-- END OF MIGRATIONS
-- ═══════════════════════════════════════════════════════════════════════
