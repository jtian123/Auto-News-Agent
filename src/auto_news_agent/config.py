from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class CampusProfile:
    campus_id: str
    school_name: str
    school_aliases: List[str]
    city: str
    region_aliases: List[str]
    content_categories: List[str]
    weekly_constraints: Dict[str, int]
    # Deprecated fields - kept for backwards compatibility but not used
    trusted_domains: List[str] = field(default_factory=list)
    transit_keywords: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "CampusProfile":
        raw = json.loads(Path(path).read_text())
        return cls(
            campus_id=raw["campus_id"],
            school_name=raw["school_name"],
            school_aliases=raw["school_aliases"],
            city=raw["city"],
            region_aliases=raw.get("region_aliases", []),
            content_categories=raw.get("content_categories", []),
            weekly_constraints=raw.get("weekly_constraints", {"final_picks": 8}),
            trusted_domains=raw.get("trusted_domains", []),
            transit_keywords=raw.get("transit_keywords", []),
        )


def profile_path(campus_id: str, base_dir: str | Path = "campus_profiles") -> Path:
    return Path(base_dir) / f"{campus_id}.json"
