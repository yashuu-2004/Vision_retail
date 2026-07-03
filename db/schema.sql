-- Vision Retail AI - PostgreSQL Schema
-- Purplle Tech Challenge 2026

CREATE SCHEMA IF NOT EXISTS vision_retail;
SET search_path TO vision_retail, public;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Stores
CREATE TABLE stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_code VARCHAR(50) UNIQUE NOT NULL,
    store_name VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    country VARCHAR(100),
    layout_file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stores_code ON stores(store_code);

-- Cameras
CREATE TABLE cameras (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    camera_code VARCHAR(50) NOT NULL,
    camera_name VARCHAR(255),
    camera_type VARCHAR(50), -- entry, floor, billing, etc.
    location_x FLOAT,
    location_y FLOAT,
    fov_angle FLOAT,
    resolution_width INT,
    resolution_height INT,
    fps INT DEFAULT 30,
    status VARCHAR(20) DEFAULT 'active', -- active, inactive, error
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, camera_code)
);

CREATE INDEX idx_cameras_store ON cameras(store_id);
CREATE INDEX idx_cameras_status ON cameras(status);

-- Zones (store layout)
CREATE TABLE zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    zone_code VARCHAR(50) NOT NULL,
    zone_name VARCHAR(255),
    zone_type VARCHAR(50), -- entry, floor, billing, etc.
    polygon JSONB, -- GeoJSON polygon coordinates
    area_sqm FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, zone_code)
);

CREATE INDEX idx_zones_store ON zones(store_id);

-- ============================================================================
-- Visitor & Session Management
-- ============================================================================

-- Visitor Sessions (customer visit tracking)
CREATE TABLE visitor_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    visitor_id VARCHAR(255) NOT NULL,
    session_start TIMESTAMP NOT NULL,
    session_end TIMESTAMP,
    entry_camera_id UUID REFERENCES cameras(id),
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    total_dwell_ms INT,
    is_staff BOOLEAN DEFAULT false,
    group_entry_id VARCHAR(255), -- groups visitors entering together
    has_purchase BOOLEAN DEFAULT false,
    purchase_amount DECIMAL(10,2),
    purchase_time TIMESTAMP,
    confidence FLOAT DEFAULT 0.95,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_store ON visitor_sessions(store_id);
CREATE INDEX idx_sessions_visitor ON visitor_sessions(visitor_id, store_id);
CREATE INDEX idx_sessions_time ON visitor_sessions(store_id, session_start);
CREATE INDEX idx_sessions_staff ON visitor_sessions(is_staff);
CREATE INDEX idx_sessions_purchase ON visitor_sessions(has_purchase);

-- ============================================================================
-- Events (raw detection events)
-- ============================================================================

-- Detection Events
CREATE TABLE detection_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255) NOT NULL, -- event_id from detection
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    camera_id UUID REFERENCES cameras(id),
    visitor_id VARCHAR(255),
    event_type VARCHAR(50) NOT NULL, -- ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY
    event_timestamp TIMESTAMP NOT NULL,
    zone_id VARCHAR(255),
    dwell_ms INT,
    is_staff BOOLEAN DEFAULT false,
    confidence FLOAT DEFAULT 0.95,
    metadata JSONB,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, event_id)
);

CREATE INDEX idx_events_store ON detection_events(store_id);
CREATE INDEX idx_events_type ON detection_events(event_type);
CREATE INDEX idx_events_time ON detection_events(store_id, event_timestamp);
CREATE INDEX idx_events_visitor ON detection_events(visitor_id, store_id);
CREATE INDEX idx_events_camera ON detection_events(camera_id);

-- ============================================================================
-- Zone Occupancy & Analytics
-- ============================================================================

-- Zone Occupancy (real-time or near real-time)
CREATE TABLE zone_occupancy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    occupancy_count INT DEFAULT 0,
    staff_count INT DEFAULT 0,
    avg_dwell_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_occupancy_store_zone ON zone_occupancy(store_id, zone_id);
CREATE INDEX idx_occupancy_time ON zone_occupancy(store_id, timestamp);

-- Zone Metrics (aggregated)
CREATE TABLE zone_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    metric_hour INT, -- 0-23, NULL for daily
    visitor_count INT DEFAULT 0,
    unique_visitors INT DEFAULT 0,
    purchase_count INT DEFAULT 0,
    conversion_rate FLOAT,
    avg_dwell_ms INT,
    total_revenue DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, zone_id, metric_date, metric_hour)
);

CREATE INDEX idx_zone_metrics_store ON zone_metrics(store_id);
CREATE INDEX idx_zone_metrics_date ON zone_metrics(store_id, metric_date);

-- ============================================================================
-- Queue Analytics
-- ============================================================================

-- Queue Events
CREATE TABLE queue_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    event_timestamp TIMESTAMP NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- QUEUE_JOIN, QUEUE_ABANDON, QUEUE_CHECKOUT
    visitor_id VARCHAR(255),
    queue_depth INT,
    wait_time_ms INT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_queue_store_zone ON queue_events(store_id, zone_id);
CREATE INDEX idx_queue_time ON queue_events(store_id, event_timestamp);

-- ============================================================================
-- Store Metrics (aggregated KPIs)
-- ============================================================================

-- Daily Store Metrics
CREATE TABLE store_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    total_visitors INT DEFAULT 0,
    unique_visitors INT DEFAULT 0,
    repeat_visitors INT DEFAULT 0,
    group_entries INT DEFAULT 0,
    staff_visitors INT DEFAULT 0,
    purchase_count INT DEFAULT 0,
    conversion_rate FLOAT,
    total_revenue DECIMAL(12,2),
    avg_dwell_ms INT,
    avg_revenue_per_visitor DECIMAL(10,2),
    peak_hour INT, -- 0-23
    peak_occupancy INT,
    queue_abandonment_count INT,
    avg_queue_wait_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, metric_date)
);

CREATE INDEX idx_store_metrics_store ON store_metrics(store_id);
CREATE INDEX idx_store_metrics_date ON store_metrics(store_id, metric_date);

-- Hourly Store Metrics
CREATE TABLE store_metrics_hourly (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    metric_hour INT NOT NULL, -- 0-23
    visitors INT DEFAULT 0,
    purchases INT DEFAULT 0,
    conversion_rate FLOAT,
    revenue DECIMAL(12,2),
    avg_dwell_ms INT,
    queue_depth INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, metric_date, metric_hour)
);

CREATE INDEX idx_hourly_metrics_store ON store_metrics_hourly(store_id);
CREATE INDEX idx_hourly_metrics_time ON store_metrics_hourly(store_id, metric_date, metric_hour);

-- ============================================================================
-- Anomaly Detection
-- ============================================================================

-- Anomalies
CREATE TABLE anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    anomaly_type VARCHAR(50) NOT NULL, -- QUEUE_SPIKE, CONVERSION_DROP, DEAD_ZONE, LOST_SALE, STALE_FEED, etc.
    severity VARCHAR(20) NOT NULL, -- critical, high, medium, low
    confidence FLOAT DEFAULT 0.8,
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    reason TEXT,
    suggested_action TEXT,
    zone_id UUID REFERENCES zones(id),
    metric_value FLOAT,
    baseline_value FLOAT,
    deviation_percent FLOAT,
    acknowledged BOOLEAN DEFAULT false,
    acknowledged_at TIMESTAMP,
    resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_anomalies_store ON anomalies(store_id);
CREATE INDEX idx_anomalies_type ON anomalies(anomaly_type);
CREATE INDEX idx_anomalies_time ON anomalies(store_id, detected_at);
CREATE INDEX idx_anomalies_resolved ON anomalies(store_id, resolved);

-- ============================================================================
-- Customer Journeys
-- ============================================================================

-- Customer Journey Paths
CREATE TABLE customer_journeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES visitor_sessions(id) ON DELETE CASCADE,
    journey_path TEXT[], -- array of zone_codes in order
    journey_sequence JSONB, -- detailed sequence with timestamps
    total_duration_ms INT,
    zone_count INT,
    unique_zones INT,
    ended_with_purchase BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_journeys_store ON customer_journeys(store_id);
CREATE INDEX idx_journeys_session ON customer_journeys(session_id);
CREATE INDEX idx_journeys_purchase ON customer_journeys(ended_with_purchase);

-- Top Journey Paths (cached)
CREATE TABLE top_journey_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    path_hash VARCHAR(255),
    journey_path TEXT[],
    occurrence_count INT DEFAULT 1,
    purchase_count INT DEFAULT 0,
    conversion_rate FLOAT,
    avg_duration_ms INT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, path_hash)
);

CREATE INDEX idx_top_paths_store ON top_journey_paths(store_id);

-- ============================================================================
-- Purchase Predictions
-- ============================================================================

-- Purchase Predictions
CREATE TABLE purchase_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES visitor_sessions(id) ON DELETE CASCADE,
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prediction_score FLOAT, -- 0-1 probability
    confidence FLOAT,
    features JSONB, -- features used for prediction
    actual_purchase BOOLEAN,
    prediction_correct BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_predictions_store ON purchase_predictions(store_id);
CREATE INDEX idx_predictions_session ON purchase_predictions(session_id);

-- ============================================================================
-- POS Transactions (linked to sessions)
-- ============================================================================

-- Transactions
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    session_id UUID REFERENCES visitor_sessions(id) ON DELETE SET NULL,
    transaction_id VARCHAR(255) NOT NULL,
    transaction_time TIMESTAMP NOT NULL,
    amount DECIMAL(10,2),
    items_count INT,
    payment_method VARCHAR(50),
    receipt_number VARCHAR(100),
    metadata JSONB,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, transaction_id)
);

CREATE INDEX idx_transactions_store ON transactions(store_id);
CREATE INDEX idx_transactions_time ON transactions(store_id, transaction_time);
CREATE INDEX idx_transactions_session ON transactions(session_id);

-- ============================================================================
-- System Monitoring
-- ============================================================================

-- Camera Health
CREATE TABLE camera_health (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20), -- online, offline, lag, error
    frames_per_sec FLOAT,
    frame_count INT,
    last_frame_timestamp TIMESTAMP,
    error_message TEXT,
    latency_ms INT
);

CREATE INDEX idx_camera_health_camera ON camera_health(camera_id);
CREATE INDEX idx_camera_health_time ON camera_health(check_time);

-- API Metrics (for monitoring)
CREATE TABLE api_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    status_code INT,
    latency_ms INT,
    trace_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_metrics_endpoint ON api_metrics(endpoint);
CREATE INDEX idx_api_metrics_time ON api_metrics(timestamp);

-- ============================================================================
-- Audit Log
-- ============================================================================

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_store ON audit_log(store_id);
CREATE INDEX idx_audit_time ON audit_log(created_at);

-- ============================================================================
-- Materialized Views (for performance)
-- ============================================================================

-- Daily conversion by zone (cached)
CREATE MATERIALIZED VIEW zone_conversion_daily AS
SELECT
    zm.store_id,
    zm.zone_id,
    z.zone_name,
    zm.metric_date,
    zm.visitor_count,
    zm.purchase_count,
    CASE WHEN zm.visitor_count > 0 THEN 
        ROUND(
            CAST((zm.purchase_count::FLOAT / zm.visitor_count) * 100 AS NUMERIC),
            2
        )
    ELSE 0 END as conversion_rate
FROM zone_metrics zm
JOIN zones z ON zm.zone_id = z.id
ORDER BY zm.metric_date DESC;

CREATE INDEX idx_zone_conv_store_date ON zone_conversion_daily(store_id, metric_date);

-- ============================================================================
-- Functions & Triggers
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_stores_timestamp
BEFORE UPDATE ON stores
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_update_sessions_timestamp
BEFORE UPDATE ON visitor_sessions
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- Permissions
-- ============================================================================

GRANT USAGE ON SCHEMA vision_retail TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA vision_retail TO postgres;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA vision_retail TO postgres;
