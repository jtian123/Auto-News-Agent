from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List

from .schemas import CandidateItem, FinalPick


def normalize_title(title: str) -> str:
    """Normalize title for deduplication comparison."""
    # Lowercase
    s = title.lower()
    # Remove punctuation and extra whitespace
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove common prefixes/suffixes
    s = re.sub(r'^(the|a|an)\s+', '', s)
    return s


def title_similarity(t1: str, t2: str) -> float:
    """Calculate similarity between two normalized titles using word overlap."""
    words1 = set(normalize_title(t1).split())
    words2 = set(normalize_title(t2).split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0


def dedupe(items: List[CandidateItem], similarity_threshold: float = 0.7) -> List[CandidateItem]:
    """
    Remove duplicate events using fuzzy title matching and date comparison.

    Events are considered duplicates if:
    - Title similarity > threshold AND same date
    - OR exact normalized title match
    """
    if not items:
        return []

    unique: List[CandidateItem] = []
    seen_normalized: set[str] = set()

    # Sort by confidence descending so we keep the best version
    sorted_items = sorted(items, key=lambda x: x.confidence, reverse=True)

    for item in sorted_items:
        norm_title = normalize_title(item.title)

        # Check exact match first
        title_date_key = f"{norm_title}|{item.date}"
        if title_date_key in seen_normalized:
            continue

        # Check fuzzy similarity against existing items
        is_duplicate = False
        for existing in unique:
            # Same date and similar title = duplicate
            if item.date == existing.date:
                sim = title_similarity(item.title, existing.title)
                if sim >= similarity_threshold:
                    is_duplicate = True
                    break

            # Very high title similarity regardless of date (likely same event, different source)
            sim = title_similarity(item.title, existing.title)
            if sim >= 0.9:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(item)
            seen_normalized.add(title_date_key)

    return unique


def is_title_duplicate(title: str, existing_titles: List[str], threshold: float = 0.7) -> bool:
    """Check if a title is too similar to any existing selected title."""
    for existing in existing_titles:
        if title_similarity(title, existing) >= threshold:
            return True
    return False


def apply_constraints(
    scored: List[FinalPick], weekly_constraints: Dict[str, int]
) -> List[FinalPick]:
    """Apply category min/max constraints to select final picks."""

    final_picks = weekly_constraints.get("final_picks", len(scored))

    # Separate min and max constraints
    min_requirements = {
        key.replace("min_", ""): val
        for key, val in weekly_constraints.items()
        if key.startswith("min_")
    }
    max_limits = {
        key.replace("max_", ""): val
        for key, val in weekly_constraints.items()
        if key.startswith("max_")
    }

    selected: List[FinalPick] = []
    selected_ids: set[str] = set()
    selected_titles: List[str] = []  # Track titles for fuzzy dedup
    category_counts: Dict[str, int] = defaultdict(int)

    # Phase 1: Fulfill minimum requirements first (by score within each category)
    for category, needed in min_requirements.items():
        candidates = sorted(
            [c for c in scored if c.category == category and c not in selected],
            key=lambda x: x.score,
            reverse=True,
        )
        for pick in candidates[:needed]:
            if pick.id in selected_ids:
                continue
            # Safety net: reject if title is too similar to already selected
            if is_title_duplicate(pick.title, selected_titles):
                continue
            selected.append(pick)
            selected_ids.add(pick.id)
            selected_titles.append(pick.title)
            category_counts[category] += 1

    # Phase 2: Fill remaining slots by score, respecting max limits
    for pick in scored:
        if len(selected) >= final_picks:
            break

        cat = pick.category
        max_limit = max_limits.get(cat, float("inf"))

        if category_counts.get(cat, 0) >= max_limit:
            continue
        if pick.id in selected_ids:
            continue
        # Safety net: reject if title is too similar to already selected
        if is_title_duplicate(pick.title, selected_titles):
            continue

        selected.append(pick)
        selected_ids.add(pick.id)
        selected_titles.append(pick.title)
        category_counts[cat] += 1

    return selected


def aggregate(
    items: List[CandidateItem],
    ai_scores: Dict[str, float],
    weekly_constraints: Dict[str, int],
) -> List[FinalPick]:
    """
    Main aggregation pipeline: apply AI scores → apply constraints.

    NOTE: Deduplication is now handled by AI scoring agent, not hardcoded logic.

    Args:
        items: List of CandidateItems from subagents
        ai_scores: Dict mapping event_id to AI-generated score (0-100)
        weekly_constraints: Dict with final_picks, min_*, max_* constraints
    """
    # NO deduplication - AI scoring agent handles it by giving duplicates very low scores

    # Convert to FinalPick with AI scores
    scored: List[FinalPick] = []
    for item in items:
        score = ai_scores.get(item.id, 50.0)  # Default to 50 if not scored
        scored.append(FinalPick(**item.to_dict(), score=score))

    # Sort by score
    scored.sort(key=lambda x: x.score, reverse=True)

    # Apply constraints and return
    return apply_constraints(scored, weekly_constraints)
