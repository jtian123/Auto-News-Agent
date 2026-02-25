from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

from dateutil import parser as dateparser

from ..config import CampusProfile
from ..gemini_client import GeminiSearchClient
from ..schemas import CandidateItem


class Subagent:
    """
    Subagent that searches for events using Gemini with structured JSON output.

    Each subagent has a name, category, and list of query templates.
    It runs all queries and returns validated CandidateItems.
    """

    def __init__(self, name: str, category: str, query_templates: List[str]):
        self.name = name
        self.category = category
        self.query_templates = query_templates

    def run(self, profile: CampusProfile) -> Tuple[List[CandidateItem], dict]:
        """
        Execute all query templates and return (items, stats).
        """
        client = GeminiSearchClient()
        items: List[CandidateItem] = []
        today = datetime.utcnow().date()

        # Start from tomorrow - today's events will be expired by posting time (6pm)
        tomorrow = today + timedelta(days=1)
        tomorrow_str = tomorrow.isoformat()

        # Get school alias for use in queries and categories
        school_alias = profile.school_aliases[0] if profile.school_aliases else profile.school_name
        city_upper = profile.city.upper().replace(" ", "_")

        # Resolve dynamic category names
        resolved_category = self.category
        if resolved_category == "SCHOOL_EVENT":
            resolved_category = f"{school_alias.upper()}_EVENT"
        elif "{CITY}" in resolved_category:
            resolved_category = resolved_category.replace("{CITY}", city_upper)

        stats = {
            "queries": 0,
            "raw_events": 0,
            "kept": 0,
            "dropped_past": 0,
            "dropped_far": 0,
            "dropped_invalid": 0,
        }

        for tmpl in self.query_templates:
            query = tmpl.format(
                SCHOOL_ALIAS=school_alias,
                SCHOOL_NAME=profile.school_name,
                CITY=profile.city,
                CAMPUS=profile.school_name,
                TODAY=tomorrow_str,
            )
            stats["queries"] += 1

            # Get structured events from Gemini
            raw_events = client.search_events(
                query=query,
                today=tomorrow_str,
                category=resolved_category,
                school_name=profile.school_name,
                trusted_domains=profile.trusted_domains,
                window_days=10,
            )
            stats["raw_events"] += len(raw_events)

            for event in raw_events:
                # Validate and convert to CandidateItem
                item = self._process_event(event, today, profile, resolved_category)
                if item is None:
                    stats["dropped_invalid"] += 1
                    continue

                # Filter by date range (note: freshness_days calculated from today, not tomorrow)
                # Events tomorrow have freshness_days = 1, so we want >= 1
                if item.freshness_days < 1:
                    stats["dropped_past"] += 1
                    continue
                if item.freshness_days > 10:
                    stats["dropped_far"] += 1
                    continue

                items.append(item)
                stats["kept"] += 1

        return items, stats

    def _process_event(
        self, event: Dict[str, Any], today: datetime.date, profile: CampusProfile, resolved_category: str
    ) -> CandidateItem | None:
        """Convert a raw event dict to a CandidateItem with validation."""

        title = event.get("title", "").strip()
        if not title:
            return None

        # Parse date and calculate freshness
        date_str = event.get("date", "TBD")
        freshness_days = 7  # default
        parsed_date = None

        if date_str and date_str != "TBD":
            try:
                parsed_date = dateparser.parse(date_str, fuzzy=True)
                if parsed_date:
                    delta = parsed_date.date() - today
                    freshness_days = delta.days
            except Exception:
                pass

        # Calculate confidence based on data completeness
        confidence = self._calculate_confidence(event)

        # Generate a stable deterministic ID to avoid Python hash randomization collisions.
        # NOTE: Category is NOT included in the hash - same event from different subagents
        # should get the same ID so they can be deduplicated.
        id_seed = "|".join(
            [
                title.strip().lower(),
                str(date_str).strip().lower(),
                str(event.get("venue", "")).strip().lower(),
                str(event.get("time", "")).strip().lower(),
            ]
        )
        item_id = f"evt_{hashlib.sha1(id_seed.encode('utf-8')).hexdigest()[:12]}"

        return CandidateItem(
            id=item_id,
            title=title,
            description=event.get("description", title),
            date=date_str,
            time=event.get("time", "TBD"),
            venue=event.get("venue", "TBD"),
            address=event.get("address"),
            category=resolved_category,
            source_url=event.get("source_url"),
            source_name=event.get("source_name"),
            why_relevant=event.get("why_relevant", f"Relevant {resolved_category} event for students."),
            cost=event.get("cost"),
            freshness_days=freshness_days,
            confidence=confidence,
            tags=[resolved_category.lower()],
        )

    def _calculate_confidence(self, event: Dict[str, Any]) -> float:
        """Calculate confidence score based on data completeness."""
        score = 0.3  # Base score

        # Has specific date (not TBD)
        if event.get("date") and event.get("date") != "TBD":
            score += 0.2

        # Has specific time
        if event.get("time") and event.get("time") != "TBD":
            score += 0.1

        # Has source URL
        if event.get("source_url"):
            score += 0.2

        # Has venue/address
        if event.get("venue") and event.get("venue") != "TBD":
            score += 0.1

        # Has description
        if event.get("description") and len(event.get("description", "")) > 20:
            score += 0.1

        return min(1.0, score)
