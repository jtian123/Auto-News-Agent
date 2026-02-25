from __future__ import annotations

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any

from . import aggregator
from .config import CampusProfile, profile_path
from .gemini_client import GeminiSearchClient
from .schemas import CandidateItem, FinalPick
from .subagents import build_subagents


def _select_better_item(existing: CandidateItem, candidate: CandidateItem) -> CandidateItem:
    """Keep the richer candidate when duplicate IDs appear."""
    existing_score = (
        existing.confidence
        + (0.1 if existing.source_url else 0.0)
        + (0.05 if existing.venue and existing.venue != "TBD" else 0.0)
        + (0.05 if existing.time and existing.time != "TBD" else 0.0)
    )
    candidate_score = (
        candidate.confidence
        + (0.1 if candidate.source_url else 0.0)
        + (0.05 if candidate.venue and candidate.venue != "TBD" else 0.0)
        + (0.05 if candidate.time and candidate.time != "TBD" else 0.0)
    )
    return candidate if candidate_score > existing_score else existing


def _dedupe_by_id(items: List[CandidateItem]) -> Tuple[List[CandidateItem], int]:
    """Ensure unique IDs before/after AI stages to prevent exact duplicates in final picks."""
    by_id: Dict[str, CandidateItem] = {}
    duplicate_rows = 0
    for item in items:
        if item.id in by_id:
            duplicate_rows += 1
            by_id[item.id] = _select_better_item(by_id[item.id], item)
        else:
            by_id[item.id] = item
    return list(by_id.values()), duplicate_rows


async def _run_subagents(profile: CampusProfile) -> Tuple[List[CandidateItem], List[dict]]:
    """Run all subagents in parallel and collect results."""
    subagents = build_subagents()
    tasks = [asyncio.to_thread(agent.run, profile) for agent in subagents]
    results = await asyncio.gather(*tasks)

    all_items: List[CandidateItem] = []
    stats: List[dict] = []

    for agent, (items, agent_stats) in zip(subagents, results):
        all_items.extend(items)
        stats.append({"agent": agent.name, "category": agent.category, **agent_stats})

    return all_items, stats


def run_pipeline(campus_id: str, base_dir: str | Path = ".") -> List[FinalPick]:
    """
    Execute the full pipeline:
    1. Load campus profile
    2. Run subagents in parallel
    3. Canonicalize events with AI (cross-category dedupe)
    4. Verify source URLs with AI
    5. Score events using AI
    6. Apply constraints and select final picks
    7. Write outputs
    """
    profile_file = profile_path(campus_id, Path(base_dir) / "campus_profiles")
    profile = CampusProfile.load(profile_file)

    # Run subagents
    all_items, run_stats = asyncio.run(_run_subagents(profile))
    print(f"[info] Collected {len(all_items)} candidate events from subagents")
    all_items, duplicate_id_rows = _dedupe_by_id(all_items)
    if duplicate_id_rows:
        print(f"[info] Collapsed {duplicate_id_rows} duplicate-ID rows before canonicalization")

    client = GeminiSearchClient()

    # Single strict AI canonicalization pass (cross-category dedupe).
    canonicalization_input = [item.to_dict() for item in all_items]
    keep_ids, canonicalization_stats = client.canonicalize_events(
        canonicalization_input,
        school_name=profile.school_name,
        strict_mode=True,
    )
    keep_set = set(keep_ids)
    canonical_items = [item for item in all_items if item.id in keep_set] if keep_set else list(all_items)
    print(
        f"[info] AI strict canonicalization reduced candidates to {len(canonical_items)} "
        f"(dropped {canonicalization_stats.get('events_dropped_as_duplicates', 0)})"
    )

    # AI source verification and canonical source URL replacement
    verification_input = [item.to_dict() for item in canonical_items]
    verification_map, verification_stats = client.verify_event_sources(
        verification_input,
        school_name=profile.school_name,
    )
    for item in canonical_items:
        decision = verification_map.get(item.id)
        if not decision:
            continue
        if decision.get("verified") and decision.get("canonical_source_url"):
            item.source_url = decision["canonical_source_url"]
            if decision.get("source_name"):
                item.source_name = decision["source_name"]
        else:
            item.source_url = None
            item.source_name = None
    print(
        f"[info] AI source verification: {verification_stats.get('events_verified', 0)} verified, "
        f"{verification_stats.get('events_unverified', 0)} unverified, "
        f"{verification_stats.get('events_without_decision', 0)} without decision"
    )

    # Score events using AI
    events_for_scoring = [item.to_dict() for item in canonical_items]
    ai_scores = client.score_events(events_for_scoring, school_name=profile.school_name)
    print(f"[info] AI scored {len(ai_scores)} events")

    # Aggregate with AI scores
    final_picks = aggregator.aggregate(
        canonical_items,
        ai_scores,
        profile.weekly_constraints,
    )

    pipeline_stats: Dict[str, Any] = {
        "canonicalization": canonicalization_stats,
        "source_verification": verification_stats,
        "duplicate_id_rows_collapsed_pre_ai": duplicate_id_rows,
    }

    # Write outputs
    write_outputs(final_picks, run_stats, ai_scores, campus_id, base_dir, pipeline_stats)

    return final_picks


def write_outputs(
    final_picks: List[FinalPick],
    run_stats: List[dict],
    ai_scores: dict,
    campus_id: str,
    base_dir: str | Path = ".",
    pipeline_stats: Dict[str, Any] | None = None,
) -> None:
    """Write weekly digest and run report to outputs directory."""
    base_dir = Path(base_dir)
    outputs_dir = base_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Generate dated filename with campus prefix
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Write weekly digest with campus and date in filename
    digest_path = outputs_dir / f"{campus_id}_weekly_digest_{today_str}.json"
    digest = [pick.to_dict() for pick in final_picks]
    digest_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False))

    # Write run report
    report_path = outputs_dir / f"{campus_id}_run_report_{today_str}.json"
    total_raw = sum(s.get("raw_events", 0) for s in run_stats)
    total_kept = sum(s.get("kept", 0) for s in run_stats)
    report = {
        "campus_id": campus_id,
        "run_date": today_str,
        "total_raw_events": total_raw,
        "total_after_filtering": total_kept,
        "total_after_canonicalization": (
            (pipeline_stats or {}).get("canonicalization", {}).get("events_kept", total_kept)
        ),
        "events_scored": len(ai_scores),
        "final_picks": len(final_picks),
        "pipeline_stats": pipeline_stats or {},
        "subagents": run_stats,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"[info] Wrote {len(final_picks)} events to {digest_path}")
    print(f"[info] Wrote run report to {report_path}")


__all__ = ["run_pipeline"]
