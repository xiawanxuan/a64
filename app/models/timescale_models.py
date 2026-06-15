import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, SmallInteger, Text, JSON, UUID, DOUBLE_PRECISION, ARRAY
from app.database.timescaledb import Base


class VibrationWaveform(Base):
    __tablename__ = "vibration_waveform"

    time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    turbine_id = Column(String(64), primary_key=True, nullable=False)
    sensor_id = Column(String(64), primary_key=True, nullable=False)
    sample_rate = Column(Integer, nullable=False)
    acceleration_x = Column(DOUBLE_PRECISION)
    acceleration_y = Column(DOUBLE_PRECISION)
    acceleration_z = Column(DOUBLE_PRECISION)
    velocity_x = Column(DOUBLE_PRECISION)
    velocity_y = Column(DOUBLE_PRECISION)
    velocity_z = Column(DOUBLE_PRECISION)
    temperature = Column(DOUBLE_PRECISION)
    upload_batch_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RotationSpeed(Base):
    __tablename__ = "rotation_speed"

    time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    turbine_id = Column(String(64), primary_key=True, nullable=False)
    shaft_id = Column(String(64), primary_key=True, nullable=False)
    speed_rpm = Column(DOUBLE_PRECISION, nullable=False)
    upload_batch_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class OrderSpectrum(Base):
    __tablename__ = "order_spectrum"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time = Column(DateTime(timezone=True), nullable=False)
    turbine_id = Column(String(64), nullable=False)
    gear_id = Column(String(64), nullable=False)
    analysis_start = Column(DateTime(timezone=True), nullable=False)
    analysis_end = Column(DateTime(timezone=True), nullable=False)
    order_values = Column(ARRAY(DOUBLE_PRECISION), nullable=False)
    amplitude_values = Column(ARRAY(DOUBLE_PRECISION), nullable=False)
    max_order = Column(DOUBLE_PRECISION, nullable=False)
    order_resolution = Column(DOUBLE_PRECISION, nullable=False)
    resampled_count = Column(Integer, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class GearFaultFeatures(Base):
    __tablename__ = "gear_fault_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time = Column(DateTime(timezone=True), nullable=False)
    turbine_id = Column(String(64), nullable=False)
    gear_id = Column(String(64), nullable=False)
    spectrum_id = Column(UUID(as_uuid=True))
    mesh_order = Column(DOUBLE_PRECISION, nullable=False)
    mesh_amplitude = Column(DOUBLE_PRECISION, nullable=False)
    sideband_orders = Column(ARRAY(DOUBLE_PRECISION), nullable=False)
    sideband_amplitudes = Column(ARRAY(DOUBLE_PRECISION), nullable=False)
    sideband_spacing = Column(DOUBLE_PRECISION, nullable=False)
    max_sideband_amp = Column(DOUBLE_PRECISION, nullable=False)
    sideband_energy = Column(DOUBLE_PRECISION, nullable=False)
    kurtosis = Column(DOUBLE_PRECISION)
    crest_factor = Column(DOUBLE_PRECISION)
    rms_value = Column(DOUBLE_PRECISION)
    peak_value = Column(DOUBLE_PRECISION)
    fault_severity = Column(SmallInteger, nullable=False, default=0)
    status = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turbine_id = Column(String(64), nullable=False)
    sensor_id = Column(String(64))
    shaft_id = Column(String(64))
    total_chunks = Column(Integer, nullable=False)
    uploaded_chunks = Column(Integer, nullable=False, default=0)
    total_samples = Column(BigInteger, nullable=False, default=0)
    sample_rate = Column(Integer, nullable=False)
    waveform_format = Column(String(32))
    has_speed_data = Column(Boolean, default=False)
    start_time = Column(DateTime(timezone=True))
    status = Column(SmallInteger, nullable=False, default=0)
    file_name = Column(String(256))
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)

    __table_args__ = (
        Index("ix_upload_batches_turbine_status", "turbine_id", "status"),
    )


class FailedAnalysisRecord(Base):
    __tablename__ = "failed_analysis_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turbine_id = Column(String(64), nullable=False)
    gear_id = Column(String(64))
    analysis_type = Column(String(64), nullable=False)
    batch_id = Column(UUID(as_uuid=True))
    waveform_file = Column(String(512), nullable=False)
    speed_file = Column(String(512))
    error_type = Column(String(128), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text)
    params = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
