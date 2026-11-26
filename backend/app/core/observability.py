import re
from collections import defaultdict
from threading import Lock
from typing import Any

from opentelemetry import trace

_UUID_OR_ID_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|/\d+",
    re.IGNORECASE,
)


def normalize_path_group(path: str) -> str:
    """Collapse entity IDs in request paths to keep metric label cardinality bounded."""
    return _UUID_OR_ID_RE.sub("/{id}", path)


class MetricsRegistry:
    """In-memory HTTP telemetry collector exporting Prometheus text and JSON summaries."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_ms_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._route_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._total_requests = 0
        self._total_errors = 0

    def record(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        otel_enabled: bool = False,
    ) -> None:
        """Record an HTTP request metric and optionally emit an OpenTelemetry span."""
        path_group = normalize_path_group(path)
        with self._lock:
            self._total_requests += 1
            if status_code >= 500:
                self._total_errors += 1
            self._counts[(method, path_group, status_code)] += 1
            self._route_counts[(method, path_group)] += 1
            self._latency_ms_sum[(method, path_group)] += duration_ms

        if otel_enabled:
            tracer = trace.get_tracer("ai_procurement_manager")
            with tracer.start_as_current_span(f"{method} {path_group}") as span:
                span.set_attribute("http.method", method)
                span.set_attribute("http.route", path_group)
                span.set_attribute("http.status_code", status_code)
                span.set_attribute("http.duration_ms", round(duration_ms, 2))

    def render_prometheus(self) -> str:
        """Render collected HTTP metrics in Prometheus text exposition format."""
        lines = [
            "# HELP procurement_http_requests_total Total HTTP requests processed.",
            "# TYPE procurement_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), count in sorted(self._counts.items()):
                lines.append(
                    f'procurement_http_requests_total{{method="{method}",'
                    f'route="{route}",status="{status}"}} {count}'
                )
            lines.append(
                "# HELP procurement_http_request_duration_ms_sum Total request duration (ms)."
            )
            lines.append("# TYPE procurement_http_request_duration_ms_sum counter")
            for (method, route), total_ms in sorted(self._latency_ms_sum.items()):
                lines.append(
                    f'procurement_http_request_duration_ms_sum{{method="{method}",'
                    f'route="{route}"}} {total_ms:.2f}'
                )
            lines.append("# HELP procurement_http_server_errors_total Total 5xx HTTP responses.")
            lines.append("# TYPE procurement_http_server_errors_total counter")
            lines.append(f"procurement_http_server_errors_total {self._total_errors}")
        return "\n".join(lines) + "\n"

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serializable telemetry summary."""
        with self._lock:
            avg_latency_by_route = {
                f"{method} {route}": round(self._latency_ms_sum[(method, route)] / max(1, count), 2)
                for (method, route), count in sorted(self._route_counts.items())
            }
            return {
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "routes_tracked": len(self._route_counts),
                "avg_latency_ms_by_route": avg_latency_by_route,
            }
