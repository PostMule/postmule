from dataclasses import dataclass, field


@dataclass
class HealthResult:
    ok: bool
    status: str  # "ok" | "warn" | "error"
    message: str = ""
