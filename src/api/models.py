"""
Data models for VisionRetail AI API
Pydantic models for request/response validation
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
from decimal import Decimal


# ============================================================================
# Event Models
# ============================================================================

class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class DetectionEvent(BaseModel):
    event_id: str = Field(..., description="Unique event ID from detection")
    store_id: str = Field(..., description="Store identifier")
    camera_id: str = Field(..., description="Camera identifier")
    visitor_id: str = Field(..., description="Visitor/person stable ID")
    event_type: EventType = Field(..., description="Type of event")
    timestamp: datetime = Field(..., description="Event timestamp")
    zone_id: Optional[str] = Field(None, description="Zone identifier")
    dwell_ms: Optional[int] = Field(None, description="Dwell time in milliseconds")
    is_staff: bool = Field(False, description="Whether visitor is staff")
    confidence: float = Field(0.95, ge=0.0, le=1.0, description="Detection confidence")
    bbox: Optional[List[int]] = Field(None, description="Pixel-space bounding box [x1, y1, x2, y2]")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class EventRequest(BaseModel):
    events: List[DetectionEvent] = Field(
        ..., description="Batch of up to 500 events to ingest"
    )


# ============================================================================
# Metrics Models
# ============================================================================

class ZoneMetric(BaseModel):
    zone_id: str
    zone_name: str
    visitor_count: int
    unique_visitors: int
    purchase_count: int
    conversion_rate: float
    avg_dwell_ms: int
    total_revenue: Decimal
    evidence: Optional[Dict[str, Any]] = None


class MetricsResponse(BaseModel):
    timestamp: datetime
    store_id: str
    total_visitors: int
    unique_visitors: int
    repeat_visitors: int = 0
    group_entries: int = 0
    purchases: int = 0
    conversion_rate: float
    live_event_ratio: float = 0.0
    seeded_event_ratio: float = 0.0
    total_revenue: Decimal
    avg_dwell_ms: int
    avg_revenue_per_visitor: Decimal
    peak_hour: Optional[int] = None
    peak_occupancy: Optional[int] = None
    zones: List[ZoneMetric] = []
    evidence: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {Decimal: str}


# ============================================================================
# Funnel Models
# ============================================================================

class FunnelStage(BaseModel):
    stage: str  # entry, zone_visit, queue, billing, purchase
    count: int
    previous_count: int
    drop_off_percent: float


class FunnelResponse(BaseModel):
    timestamp: datetime
    store_id: str
    stages: List[FunnelStage]
    overall_conversion_rate: float
    evidence: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {Decimal: str}


# ============================================================================
# Heatmap Models
# ============================================================================

class ZoneHeat(BaseModel):
    zone_id: str
    zone_name: str
    value: float
    intensity: str  # "very_high", "high", "medium", "low", "very_low"
    color_hex: str  # for visualization


class HeatmapResponse(BaseModel):
    timestamp: datetime
    store_id: str
    metric: str  # visitor_count, dwell_time, conversion_rate
    zones: List[ZoneHeat]
    max_value: float
    min_value: float
    data_confidence: str = "low"
    evidence: Optional[Dict[str, Any]] = None


# ============================================================================
# Anomaly Models
# ============================================================================

class AnomalyType(str, Enum):
    QUEUE_SPIKE = "QUEUE_SPIKE"
    CONVERSION_DROP = "CONVERSION_DROP"
    DEAD_ZONE = "DEAD_ZONE"
    LOST_SALE = "LOST_SALE"
    STALE_FEED = "STALE_FEED"
    HIGH_DWELL_LOW_CONVERSION = "HIGH_DWELL_LOW_CONVERSION"
    ABNORMAL_TRAFFIC = "ABNORMAL_TRAFFIC"
    QUEUE_ABANDONMENT_SPIKE = "QUEUE_ABANDONMENT_SPIKE"
    STAFF_CONGESTION = "STAFF_CONGESTION"
    UNUSUAL_PATTERN = "UNUSUAL_PATTERN"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARN = "WARN"
    INFO = "INFO"
    # Legacy aliases for backward-compat
    HIGH = "WARN"
    MEDIUM = "WARN"
    LOW = "INFO"


class AnomalyResponse(BaseModel):
    anomaly_id: str
    store_id: str
    anomaly_type: AnomalyType
    severity: Severity
    confidence: float
    detected_at: datetime
    description: str
    reason: str
    suggested_action: str
    zone_id: Optional[str] = None
    metric_value: Optional[float] = None
    baseline_value: Optional[float] = None
    deviation_percent: Optional[float] = None


# ============================================================================
# Journey Models
# ============================================================================

class JourneySegment(BaseModel):
    zone_id: str
    zone_name: str
    entry_time: datetime
    exit_time: datetime
    dwell_ms: int


class JourneyResponse(BaseModel):
    journey_path: List[str]  # zone codes in order
    occurrence_count: int
    purchase_count: int
    conversion_rate: float
    avg_duration_ms: int
    avg_segments: int


# ============================================================================
# Prediction Models
# ============================================================================

class PredictionResponse(BaseModel):
    prediction_id: str
    store_id: str
    visitor_id: str
    prediction_score: float  # 0-1 probability
    abandonment_probability: Optional[float] = None
    basket_size_probability: Optional[float] = None
    confidence: float
    model_version: Optional[str] = None
    features_used: List[str]
    reasoning: str
    predicted_at: datetime
    evidence: Optional[Dict[str, Any]] = None


# ============================================================================
# Health Models
# ============================================================================

class ComponentStatus(BaseModel):
    name: str
    status: str  # healthy, degraded, unhealthy
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    components: List[ComponentStatus]
    uptime_seconds: int


# ============================================================================
# Queue Analytics Models
# ============================================================================

class QueueMetrics(BaseModel):
    current_depth: int
    max_depth: int
    avg_depth: float
    avg_wait_time_ms: int
    abandonment_rate: float
    abandonment_count: int
    checkout_count: int


# ============================================================================
# Opportunity Models
# ============================================================================

class Opportunity(BaseModel):
    opportunity_id: str
    zone_id: str
    zone_name: str
    opportunity_type: str  # high_dwell_low_conversion, queue_bottleneck, etc.
    severity: str
    metric: str
    current_value: float
    recommended_value: float
    estimated_revenue_impact: Decimal
    action: str
    
    class Config:
        json_encoders = {Decimal: str}
