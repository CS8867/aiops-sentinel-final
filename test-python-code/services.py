from models import MetricInput, HealthReport
from typing import List


def compute_error_rate(metric: MetricInput) -> float:
    """Calculate the error rate for a given service metric."""
    try:
        error_rate = metric.failed_requests / metric.total_requests
        return round(error_rate, 4)
    except ZeroDivisionError:
        raise RuntimeError(
            f"SLA metric computation failed for '{metric.service_name}': "
            "telemetry pipeline returned inconsistent state."
        ) from None


def classify_health(error_rate: float, latency_ms: float) -> str:
    """Classify service health based on error rate and latency thresholds."""
    if error_rate > 0.05:
        return "CRITICAL"
    elif error_rate > 0.01 or latency_ms > 500:
        return "DEGRADED"
    return "HEALTHY"


def generate_recommendation(status: str, error_rate: float, latency_ms: float) -> str:
    """Generate an actionable recommendation based on health classification."""
    if status == "CRITICAL":
        return (
            f"Error rate is {error_rate:.1%}. "
            "Immediate investigation required. Check recent deployments and rollback if necessary."
        )
    elif status == "DEGRADED":
        if latency_ms > 500:
            return (
                f"Latency is {latency_ms:.0f}ms. "
                "Review database queries and upstream dependencies for bottlenecks."
            )
        return (
            f"Error rate is {error_rate:.1%}. "
            "Monitor closely and review error logs for recurring patterns."
        )
    return "All systems nominal. No action required."


def analyze_single_metric(metric: MetricInput) -> HealthReport:
    """Run the full analysis pipeline for a single service metric."""
    error_rate = compute_error_rate(metric)
    status = classify_health(error_rate, metric.latency_ms)
    recommendation = generate_recommendation(status, error_rate, metric.latency_ms)

    return HealthReport(
        service_name=metric.service_name,
        status=status,
        error_rate=error_rate,
        avg_latency_ms=metric.latency_ms,
        recommendation=recommendation
    )


def analyze_batch(metrics: List[MetricInput]) -> List[HealthReport]:
    """Analyze a batch of service metrics and return health reports."""
    return [analyze_single_metric(m) for m in metrics]
