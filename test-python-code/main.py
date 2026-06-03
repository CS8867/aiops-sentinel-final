from fastapi import FastAPI, HTTPException
from models import MetricInput, BatchMetricInput, HealthReport
from services import analyze_single_metric, analyze_batch
from utils import log_analysis_event, get_timestamp
from typing import List

app = FastAPI(
    title="Sentinel Health Analyzer",
    description="Microservice for real-time service health analysis and incident classification.",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    """Liveness probe for the service."""
    return {"status": "ok", "timestamp": get_timestamp()}


@app.post("/analyze", response_model=HealthReport)
def analyze_metric(metric: MetricInput):
    """Analyze a single service metric and return a health report."""
    try:
        report = analyze_single_metric(metric)
        log_analysis_event(report.service_name, report.status)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/batch", response_model=List[HealthReport])
def analyze_metric_batch(payload: BatchMetricInput):
    """Analyze a batch of service metrics and return health reports."""
    if not payload.metrics:
        raise HTTPException(status_code=400, detail="Metrics list cannot be empty.")
    try:
        reports = analyze_batch(payload.metrics)
        for report in reports:
            log_analysis_event(report.service_name, report.status)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
