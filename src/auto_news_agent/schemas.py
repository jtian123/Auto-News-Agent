from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class CandidateItem:
    """Raw event extracted from Gemini search."""
    id: str
    title: str
    description: str
    date: str  # ISO format preferred: YYYY-MM-DD
    time: str  # e.g., "11:00 AM - 3:00 PM"
    venue: str
    address: Optional[str]
    category: str
    source_url: Optional[str]
    source_name: Optional[str]
    why_relevant: str  # Why students should care
    cost: Optional[str]  # e.g., "Free", "$20", "Under $30"
    freshness_days: int = 7
    confidence: float = 0.5
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinalPick(CandidateItem):
    """Scored and selected event for the weekly digest."""
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# JSON schema for Gemini structured output
EVENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title, clean without markdown"},
                    "description": {"type": "string", "description": "Brief description of what the event is"},
                    "date": {"type": "string", "description": "Event date in YYYY-MM-DD format"},
                    "time": {"type": "string", "description": "Event time, e.g., '11:00 AM - 3:00 PM'"},
                    "venue": {"type": "string", "description": "Venue or location name"},
                    "address": {"type": "string", "description": "Full address if available"},
                    "source_url": {"type": "string", "description": "URL to event page or source"},
                    "source_name": {"type": "string", "description": "Name of the source website"},
                    "why_relevant": {"type": "string", "description": "Why students should care about this event"},
                    "cost": {"type": "string", "description": "Cost info: 'Free', '$20', 'Under $30', etc."},
                },
                "required": ["title", "date", "venue"],
            },
        }
    },
    "required": ["events"],
}
