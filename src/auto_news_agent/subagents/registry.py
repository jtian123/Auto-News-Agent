from __future__ import annotations

from typing import List

from .base import Subagent


# Streamlined 4-subagent structure with 1 query each.
# Use {SCHOOL_ALIAS}, {SCHOOL_NAME}, {CITY}, {TODAY} placeholders - NO hardcoded school names!
# Note: {TODAY} is actually tomorrow's date (today's events expire by posting time at 6pm)
SUBAGENT_SPECS = [
    (
        "CAMPUS_EVENTS",
        "SCHOOL_EVENT",  # Will be replaced with actual school name at runtime
        [
            "{SCHOOL_ALIAS} official events, student club events, workshops, and networking starting {TODAY}; include date/time/venue/link",
        ],
    ),
    (
        "SPORTS",
        "SPORTS",
        [
            "{SCHOOL_ALIAS} home athletics games starting {TODAY} at campus venues; include opponent, date, time, venue, ticket link",
        ],
    ),
    (
        "CITY_LIFE",
        "{CITY}_EVENT",  # Will be replaced with actual city at runtime
        [
            "{CITY} pop-ups, markets, concerts, festivals, and food events near {SCHOOL_ALIAS} starting {TODAY}; under $30; include date/time/venue/link",
        ],
    ),
    (
        "CAREER",
        "CAREER",
        [
            "{SCHOOL_ALIAS} career fairs, recruiting events, and professional development workshops starting {TODAY}; include date/time/venue/link",
        ],
    ),
]


def build_subagents() -> List[Subagent]:
    return [Subagent(name, category, templates) for name, category, templates in SUBAGENT_SPECS]
