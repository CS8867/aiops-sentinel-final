from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MetricInput(BaseModel):
    service_name: str
    total_requests: int
    failed_requests: int
    latency_ms: float
    timestamp: Optional[datetime] = None


class HealthReport(BaseModel):
    service_name: str
    status: str
    error_rate: float
    avg_latency_ms: float
    recommendation: str


class BatchMetricInput(BaseModel):
    metrics: List[MetricInput]
