"""Data models for MCI."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SubIndexResult:
    """Result from a single sub-index collector."""
    name: str                    # e.g. "security"
    score: float                 # 0-100 normalized
    weight: float                # from config
    details: dict = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)  # human-readable signals
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class MCIResult:
    """Composite MCI result."""
    score: float
    label: str
    advice: str
    sub_indexes: list[SubIndexResult]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "label": self.label,
            "advice": self.advice,
            "timestamp": self.timestamp.isoformat(),
            "sub_indexes": [
                {
                    "name": si.name,
                    "score": round(si.score, 1),
                    "weight": si.weight,
                    "weighted": round(si.weighted_score, 1),
                    "signals": si.signals,
                    "details": si.details,
                }
                for si in self.sub_indexes
            ],
        }
