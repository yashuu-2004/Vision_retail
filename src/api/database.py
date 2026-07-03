"""
Database setup and ORM models.

The challenge reviewer runs the service through Docker with PostgreSQL, while
unit tests and quick local checks should work without a database daemon.  The
default is therefore SQLite; Docker overrides DATABASE_URL to PostgreSQL.
"""

import os
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    DECIMAL,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vision_retail.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")
SCHEMA = None if IS_SQLITE else "vision_retail"

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def uuid_column():
    if IS_SQLITE:
        return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    return Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(table: str) -> str:
    return f"{SCHEMA}.{table}.id" if SCHEMA else f"{table}.id"


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = {"schema": SCHEMA} if SCHEMA else {}

    id = uuid_column()
    store_code = Column(String(50), unique=True, nullable=False)
    store_name = Column(String(255), nullable=False)
    city = Column(String(100))
    country = Column(String(100))
    layout_file_path = Column(String(500))
    aliases = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cameras = relationship("Camera", back_populates="store", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="store", cascade="all, delete-orphan")
    sessions = relationship("VisitorSession", back_populates="store", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        UniqueConstraint("store_id", "camera_code", name="uq_camera_store_code"),
        {"schema": SCHEMA},
    ) if SCHEMA else (UniqueConstraint("store_id", "camera_code", name="uq_camera_store_code"),)

    id = uuid_column()
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    camera_code = Column(String(50), nullable=False)
    camera_name = Column(String(255))
    camera_type = Column(String(50))
    source_file = Column(String(255))
    fps = Column(Float)
    status = Column(String(20), default="active")
    last_heartbeat = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="cameras")


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("store_id", "zone_code", name="uq_zone_store_code"),
        {"schema": SCHEMA},
    ) if SCHEMA else (UniqueConstraint("store_id", "zone_code", name="uq_zone_store_code"),)

    id = uuid_column()
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    zone_code = Column(String(50), nullable=False)
    zone_name = Column(String(255))
    zone_type = Column(String(50))
    polygon = Column(JSON)
    area_sqm = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="zones")


class DetectionEventRecord(Base):
    __tablename__ = "detection_events"
    __table_args__ = (
        UniqueConstraint("store_id", "event_id", name="uq_event_store_id"),
        {"schema": SCHEMA},
    ) if SCHEMA else (UniqueConstraint("store_id", "event_id", name="uq_event_store_id"),)

    id = uuid_column()
    event_id = Column(String(255), nullable=False)
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    camera_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("cameras")))
    camera_code = Column(String(50))
    visitor_id = Column(String(255), nullable=False)
    event_type = Column(String(50), nullable=False)
    event_timestamp = Column(DateTime, nullable=False)
    zone_id = Column(String(255))
    dwell_ms = Column(Integer, default=0)
    is_staff = Column(Boolean, default=False)
    confidence = Column(Float, default=0.95)
    event_metadata = Column("metadata", JSON, default=dict)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"
    __table_args__ = (
        UniqueConstraint("store_id", "visitor_id", name="uq_session_store_visitor"),
        {"schema": SCHEMA},
    ) if SCHEMA else (UniqueConstraint("store_id", "visitor_id", name="uq_session_store_visitor"),)

    id = uuid_column()
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    visitor_id = Column(String(255), nullable=False)
    session_start = Column(DateTime, nullable=False)
    session_end = Column(DateTime)
    total_dwell_ms = Column(Integer, default=0)
    is_staff = Column(Boolean, default=False)
    has_purchase = Column(Boolean, default=False)
    purchase_amount = Column(DECIMAL(10, 2), default=0)
    purchase_time = Column(DateTime)
    transaction_id = Column(String(255))
    confidence = Column(Float, default=0.95)
    journey_path = Column(JSON, default=list)
    session_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("Store", back_populates="sessions")


class TransactionRecord(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("store_id", "transaction_id", name="uq_transaction_store_id"),
        {"schema": SCHEMA},
    ) if SCHEMA else (UniqueConstraint("store_id", "transaction_id", name="uq_transaction_store_id"),)

    id = uuid_column()
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    transaction_id = Column(String(255), nullable=False)
    transaction_timestamp = Column(DateTime, nullable=False)
    basket_value_inr = Column(DECIMAL(10, 2), nullable=False)
    item_count = Column(Integer, default=0)
    line_count = Column(Integer, default=0)
    primary_department = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class AnomalyRecord(Base):
    __tablename__ = "anomalies"
    __table_args__ = {"schema": SCHEMA} if SCHEMA else {}

    id = uuid_column()
    store_id = Column(String(36) if IS_SQLITE else PG_UUID(as_uuid=True), ForeignKey(fk("stores")), nullable=False)
    anomaly_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    confidence = Column(Float, default=0.8)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    description = Column(Text)
    reason = Column(Text)
    suggested_action = Column(Text)
    zone_id = Column(String(255))
    metric_value = Column(Float)
    baseline_value = Column(Float)
    deviation_percent = Column(Float)
    acknowledged = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)
    anomaly_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db_sync():
    """Initialize database tables from synchronous contexts/tests."""
    if SCHEMA:
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    Base.metadata.create_all(bind=engine)


async def init_db():
    """Initialize database tables."""
    init_db_sync()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
