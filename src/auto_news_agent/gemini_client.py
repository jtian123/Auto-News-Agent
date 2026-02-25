from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional, Tuple


class GeminiSearchClient:
    """Wrapper around google-genai with Google Search grounding and structured JSON output."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model
        self.client = None
        self.genai_types = None

        if not self.api_key:
            print("[warn] GEMINI_API_KEY is missing; Gemini search is disabled.")
            return

        try:
            from google import genai
            from google.genai import types

            self.genai_types = types
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"[warn] Failed to initialize Gemini client: {e}")
            self.client = None

    @property
    def enabled(self) -> bool:
        return self.client is not None and self.genai_types is not None

    def search_events(
        self,
        query: str,
        today: str,
        category: str,
        school_name: str = "University",
        trusted_domains: List[str] | None = None,
        window_days: int = 14,
    ) -> List[Dict[str, Any]]:
        """
        Search for events using Google Search grounding and return structured JSON.

        Returns a list of event dictionaries with fields:
        - title, description, date, time, venue, address, source_url, source_name, why_relevant, cost
        """
        if not self.enabled:
            return []

        try:
            types = self.genai_types

            # Configure Google Search grounding tool
            tool = types.Tool(google_search=types.GoogleSearch())

            trusted_text = ""
            if trusted_domains:
                trusted_text = f"Prefer results from: {', '.join(trusted_domains)}."

            prompt = f"""You are a campus event research assistant. Search for real, verified events.

SEARCH QUERY: {query}

REQUIREMENTS:
- Only include events on or after {today} within the next {window_days} days
- Each event MUST have a verifiable source URL
- Exclude: listicles, rumors, past events, general articles without specific event dates
- IMPORTANT FOR SPORTS: Only include HOME games at campus venues or local area. NO away games at other cities.
- {trusted_text}

Return a JSON object with an "events" array. Each event object must have:
- title: Event name (plain text, no markdown or special formatting)
- description: Brief description of what the event is (appropriate length for context)
- date: Event date in YYYY-MM-DD format
- time: Event time (e.g., "11:00 AM - 3:00 PM") or "TBD" if unknown
- venue: Location/venue name
- address: Full address if available, otherwise null
- source_url: Direct URL to event page or announcement (NOT search pages, NOT redirect wrappers)
- source_name: Website/source name (e.g., "Eventbrite", official university site)
- why_relevant: Why {school_name} students would care about this
- cost: Price info ("Free", "$20", "Under $30") or null if unknown

Return up to 10 quality events. The scoring system will filter and rank them later.
Respond ONLY with valid JSON, no other text."""

            config = types.GenerateContentConfig(
                tools=[tool],
                temperature=0.1,  # Low temperature for factual accuracy
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config,
            )

            # Extract text from response
            text = self._extract_response_text(response)

            # Parse JSON response
            return self._parse_json_response(text, category)

        except Exception as e:
            print(f"[warn] Gemini search failed for query '{query[:50]}...': {e}")
            return []

    def canonicalize_events(
        self,
        events: List[Dict[str, Any]],
        school_name: str = "University",
        strict_mode: bool = False,
    ) -> Tuple[List[str], Dict[str, int]]:
        """
        Use AI to canonicalize duplicate/near-duplicate events across categories.

        Returns:
            (keep_ids, stats)
            - keep_ids: event IDs selected as canonical candidates
            - stats: summary counters
        """
        if not events:
            return [], {
                "events_input": 0,
                "events_kept": 0,
                "events_dropped_as_duplicates": 0,
                "clusters_found": 0,
            }

        if not self.enabled:
            all_ids = [e.get("id") for e in events if e.get("id")]
            return all_ids, {
                "events_input": len(events),
                "events_kept": len(all_ids),
                "events_dropped_as_duplicates": 0,
                "clusters_found": 0,
            }

        try:
            event_summaries = []
            for e in events:
                event_summaries.append(
                    {
                        "id": e.get("id"),
                        "title": e.get("title"),
                        "description": e.get("description"),
                        "date": e.get("date"),
                        "time": e.get("time"),
                        "venue": e.get("venue"),
                        "category": e.get("category"),
                        "source_url": e.get("source_url"),
                        "source_name": e.get("source_name"),
                    }
                )

            strict_rules = ""
            if strict_mode:
                strict_rules = """
STRICT UNIQUENESS RULES:
- If title and date are the same, treat as duplicates unless there is clear evidence they are different sessions.
- If title/date are same and one venue is "TBD" while the other has concrete venue, prefer the concrete venue record.
- Prefer records with clearer event details (venue/time/source_url) when selecting canonical_id.
"""

            prompt = f"""You are an event canonicalization agent for {school_name}.

Your goal is to AGGRESSIVELY identify and merge duplicate events across different categories.

CRITICAL - CROSS-CATEGORY DUPLICATES:
Events from DIFFERENT categories can be the SAME real-world event!
Example: "CUIMC Well-Being Fair!" might appear as:
  - COLUMBIA_EVENT (from school events subagent)
  - NEW_YORK_EVENT (from city events subagent)
  - CULTURE (from culture subagent)
  - FOOD_DRINK (from food subagent)
These are ALL THE SAME EVENT and should be merged into ONE!

DUPLICATE DETECTION RULES:
1. Same or very similar title (>80% word overlap) + same date = DUPLICATE regardless of category
2. Same venue + same date + similar time = likely DUPLICATE
3. Category field should be IGNORED when comparing - it just indicates which subagent found it
4. Minor title variations ("CUIMC Well-Being Fair!" vs "CUIMC Well-Being Fair") = SAME event

INPUT:
A JSON array of event objects. Event IDs are unique.

TASK:
1) Group events that refer to the same real-world event, IGNORING the category field.
2) For each duplicate group, choose ONE canonical event ID (prefer the one with most complete info: has source_url, specific venue, specific time).
3) Keep non-duplicates as-is.
4) Be AGGRESSIVE about merging - it's worse to show duplicates than to miss one event.
{strict_rules}

Output JSON ONLY in this exact shape:
{{
  "keep_ids": ["id1", "id2"],
  "clusters": [
    {{
      "canonical_id": "id1",
      "member_ids": ["id1", "id9"],
      "reason": "Same event title/date/venue with wording variation",
      "duplicate_confidence": 0.92
    }}
  ]
}}

Rules:
- "keep_ids" must contain ONLY the canonical IDs from each cluster + truly unique events.
- EXCLUDE duplicate member_ids from keep_ids (only the canonical_id should be in keep_ids).
- Every duplicate cluster must include canonical_id in member_ids.
- Confidence is 0 to 1.
- Return valid JSON only.

EVENTS:
{json.dumps(event_summaries, ensure_ascii=False)}
"""

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=self.genai_types.GenerateContentConfig(temperature=0.1),
            )
            text = self._extract_response_text(response)
            keep_ids, cluster_count = self._parse_canonicalization_response(text, events)
            return keep_ids, {
                "events_input": len(events),
                "events_kept": len(keep_ids),
                "events_dropped_as_duplicates": max(0, len(events) - len(keep_ids)),
                "clusters_found": cluster_count,
            }
        except Exception as e:
            print(f"[warn] AI canonicalization failed: {e}")
            all_ids = [e.get("id") for e in events if e.get("id")]
            return all_ids, {
                "events_input": len(events),
                "events_kept": len(all_ids),
                "events_dropped_as_duplicates": 0,
                "clusters_found": 0,
            }

    def verify_event_sources(
        self,
        events: List[Dict[str, Any]],
        school_name: str = "University",
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
        """
        Verify sources for each event using AI search and return per-event decisions.

        Returns:
            (verification_map, stats)
            - verification_map[event_id] = {
                verified, canonical_source_url, source_name,
                verification_confidence, reason, evidence_urls
              }
        """
        if not events:
            return {}, {
                "events_checked": 0,
                "events_verified": 0,
                "events_unverified": 0,
                "events_without_decision": 0,
            }

        if not self.enabled:
            return {}, {
                "events_checked": len(events),
                "events_verified": 0,
                "events_unverified": 0,
                "events_without_decision": len(events),
            }

        try:
            types = self.genai_types
            tool = types.Tool(google_search=types.GoogleSearch())

            all_verifications: Dict[str, Dict[str, Any]] = {}
            batch_size = 40  # Process 40 events per API call to reduce total calls
            for start in range(0, len(events), batch_size):
                batch_events = events[start:start + batch_size]
                compact_events = []
                for e in batch_events:
                    compact_events.append(
                        {
                            "id": e.get("id"),
                            "title": e.get("title"),
                            "description": e.get("description"),
                            "date": e.get("date"),
                            "time": e.get("time"),
                            "venue": e.get("venue"),
                            "address": e.get("address"),
                            "source_url": e.get("source_url"),
                            "source_name": e.get("source_name"),
                        }
                    )

                prompt = f"""You are a source verification agent for {school_name} weekly event digest.

For each event:
1) Verify it appears to be a real upcoming event.
2) Select ONE canonical direct source URL for that specific event.
3) Avoid search pages, redirect wrappers, and generic home pages.
4) If confidence is low, mark verified=false.

Output JSON ONLY in this exact shape:
{{
  "verifications": [
    {{
      "id": "event_id",
      "verified": true,
      "canonical_source_url": "https://...",
      "source_name": "Site Name",
      "verification_confidence": 0.88,
      "reason": "Date/title/venue match found on official listing",
      "evidence_urls": ["https://...", "https://..."]
    }}
  ]
}}

Rules:
- Include one verification object for every input event ID.
- "canonical_source_url" should be null when verified=false.
- Keep confidence between 0 and 1.
- Return valid JSON only.

EVENTS:
{json.dumps(compact_events, ensure_ascii=False)}
"""

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        tools=[tool],
                        temperature=0.1,
                    ),
                )
                text = self._extract_response_text(response)
                verification_map = self._parse_source_verification_response(text, batch_events)
                all_verifications.update(verification_map)

            checked = len(events)
            verified = 0
            unverified = 0
            without_decision = 0
            for event in events:
                event_id = event.get("id")
                decision = all_verifications.get(event_id)
                if not decision:
                    without_decision += 1
                    continue
                if decision.get("verified"):
                    verified += 1
                else:
                    unverified += 1

            return all_verifications, {
                "events_checked": checked,
                "events_verified": verified,
                "events_unverified": unverified,
                "events_without_decision": without_decision,
            }
        except Exception as e:
            print(f"[warn] AI source verification failed: {e}")
            return {}, {
                "events_checked": len(events),
                "events_verified": 0,
                "events_unverified": 0,
                "events_without_decision": len(events),
            }

    def _parse_json_response(self, text: str, category: str) -> List[Dict[str, Any]]:
        """Parse JSON from Gemini response, handling various formats."""
        if not text:
            return []

        # Clean up the response text
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)

            if isinstance(data, dict) and "events" in data:
                events = data["events"]
            elif isinstance(data, list):
                events = data
            else:
                return []

            # Validate and clean each event
            valid_events = []
            for event in events:
                if not isinstance(event, dict):
                    continue

                # Must have at least title, date, venue
                if not all(event.get(f) for f in ["title", "date", "venue"]):
                    continue

                # Clean the event data
                cleaned = self._clean_event(event, category)
                if cleaned:
                    valid_events.append(cleaned)

            return valid_events

        except json.JSONDecodeError:
            # Try to extract JSON from mixed content
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    if "events" in data:
                        return self._parse_json_response(json.dumps(data), category)
                except json.JSONDecodeError:
                    pass
            return []

    def _clean_event(self, event: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
        """Clean and validate a single event dictionary."""

        def clean_text(s: Any) -> str:
            """Remove markdown and clean text."""
            if not s:
                return ""
            s = str(s)
            # Remove markdown bold/italic
            s = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', s)
            # Remove markdown links, keep text
            s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
            # Clean up whitespace
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        title = clean_text(event.get("title"))
        if not title or len(title) < 5:
            return None

        # Filter out non-event responses (Gemini sometimes returns explanatory text)
        skip_phrases = [
            "here are", "i found", "based on", "according to",
            "unfortunately", "i couldn't", "no events"
        ]
        if any(phrase in title.lower() for phrase in skip_phrases):
            return None

        return {
            "title": title,
            "description": clean_text(event.get("description")) or title,
            "date": clean_text(event.get("date")) or "TBD",
            "time": clean_text(event.get("time")) or "TBD",
            "venue": clean_text(event.get("venue")) or "TBD",
            "address": clean_text(event.get("address")) or None,
            "source_url": self._clean_url_value(event.get("source_url")),
            "source_name": clean_text(event.get("source_name")) or None,
            "why_relevant": clean_text(event.get("why_relevant")) or f"Relevant {category} event for students.",
            "cost": clean_text(event.get("cost")) or None,
            "category": category,
        }

    def _extract_grounding_urls(self, response) -> List[str]:
        """Extract grounding attribution URLs from Gemini response."""
        urls = []
        try:
            if not response.candidates:
                return urls

            gm = response.candidates[0].grounding_metadata
            if gm and hasattr(gm, "grounding_chunks"):
                for chunk in gm.grounding_chunks:
                    if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                        urls.append(chunk.web.uri)

            # Also try grounding_supports
            if gm and hasattr(gm, "grounding_supports"):
                for support in gm.grounding_supports:
                    if hasattr(support, "grounding_chunk_indices"):
                        for idx in support.grounding_chunk_indices:
                            if idx < len(urls):
                                continue  # Already have this one

        except Exception:
            pass

        return list(dict.fromkeys(urls))  # Dedupe while preserving order

    def _extract_response_text(self, response) -> str:
        """Extract text content from a Gemini response object."""
        text = ""
        try:
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
        except Exception:
            pass

        if not text and hasattr(response, "text"):
            text = response.text or ""
        return text.strip()

    def _extract_json_payload(self, text: str) -> Any:
        """Extract a JSON object/array from possibly mixed model output."""
        if not text:
            return None

        text = text.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        obj_match = re.search(r"\{[\s\S]*\}", text)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                return None
        return None

    def _clean_url_value(self, url: Any) -> Optional[str]:
        """Normalize URL text and ensure valid http/https URL."""
        if not url:
            return None
        s = str(url).strip()
        s = re.sub(r'[\[\]]', '', s)
        s = re.sub(r'[)\]}>]+$', '', s)
        if s.startswith(("http://", "https://")):
            if self._is_noncanonical_source_url(s):
                return None
            return s
        return None

    def _is_noncanonical_source_url(self, url: str) -> bool:
        """Reject known wrapper/search URLs that are not canonical event pages."""
        try:
            parsed = urlparse(url)
        except Exception:
            return True
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        if "vertexaisearch.cloud.google.com" in host and "grounding-api-redirect" in path:
            return True
        if host.endswith("google.com") and path == "/search":
            return True
        return False

    def _parse_canonicalization_response(
        self,
        text: str,
        events: List[Dict[str, Any]],
    ) -> Tuple[List[str], int]:
        """Parse canonicalization output and return keep IDs + cluster count."""
        valid_ids = [e.get("id") for e in events if e.get("id")]
        valid_set = set(valid_ids)

        data = self._extract_json_payload(text)
        if not isinstance(data, dict):
            return valid_ids, 0

        keep_ids: List[str] = []
        seen: set[str] = set()
        raw_keep = data.get("keep_ids")
        if isinstance(raw_keep, list):
            for event_id in raw_keep:
                if isinstance(event_id, str) and event_id in valid_set and event_id not in seen:
                    keep_ids.append(event_id)
                    seen.add(event_id)

        clusters = data.get("clusters")
        cluster_count = 0
        if isinstance(clusters, list):
            for cluster in clusters:
                if not isinstance(cluster, dict):
                    continue
                canonical_id = cluster.get("canonical_id")
                member_ids = cluster.get("member_ids")
                if isinstance(canonical_id, str) and canonical_id in valid_set and isinstance(member_ids, list):
                    cluster_count += 1
                    if canonical_id not in seen:
                        keep_ids.append(canonical_id)
                        seen.add(canonical_id)

        if not keep_ids:
            return valid_ids, cluster_count
        return keep_ids, cluster_count

    def _parse_source_verification_response(
        self,
        text: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Parse source verification output and return per-event decisions."""
        data = self._extract_json_payload(text)
        valid_ids = {e.get("id") for e in events if e.get("id")}
        verifications: List[Any] = []
        if isinstance(data, dict):
            if isinstance(data.get("verifications"), list):
                verifications = data.get("verifications")
            elif isinstance(data.get("results"), list):
                verifications = data.get("results")
            elif isinstance(data.get("items"), list):
                verifications = data.get("items")
        elif isinstance(data, list):
            verifications = data
        if not verifications:
            return {}

        output: Dict[str, Dict[str, Any]] = {}
        for record in verifications:
            if not isinstance(record, dict):
                continue

            event_id = record.get("id")
            if not isinstance(event_id, str) or event_id not in valid_ids:
                continue

            verified_raw = record.get("verified")
            if isinstance(verified_raw, bool):
                verified = verified_raw
            elif isinstance(verified_raw, str):
                verified = verified_raw.strip().lower() in {"true", "yes", "1"}
            else:
                verified = False
            canonical_source_url = self._clean_url_value(record.get("canonical_source_url"))
            if not verified:
                canonical_source_url = None

            source_name = record.get("source_name")
            if source_name is not None:
                source_name = str(source_name).strip() or None

            confidence = record.get("verification_confidence")
            if isinstance(confidence, (int, float)):
                verification_confidence = max(0.0, min(1.0, float(confidence)))
            else:
                verification_confidence = 0.0

            reason = record.get("reason")
            if reason is not None:
                reason = str(reason).strip() or None

            evidence_urls: List[str] = []
            raw_evidence_urls = record.get("evidence_urls")
            if isinstance(raw_evidence_urls, list):
                seen_urls: set[str] = set()
                for raw_url in raw_evidence_urls:
                    cleaned = self._clean_url_value(raw_url)
                    if cleaned and cleaned not in seen_urls:
                        evidence_urls.append(cleaned)
                        seen_urls.add(cleaned)

            output[event_id] = {
                "verified": verified and canonical_source_url is not None,
                "canonical_source_url": canonical_source_url,
                "source_name": source_name,
                "verification_confidence": verification_confidence,
                "reason": reason,
                "evidence_urls": evidence_urls,
            }

        return output

    def score_events(
        self,
        events: List[Dict[str, Any]],
        school_name: str = "University",
    ) -> Dict[str, float]:
        """
        Use AI to score a batch of events for student appeal.

        Args:
            events: List of event dictionaries with 'id', 'title', 'description', etc.
            school_name: Name of the school for context

        Returns:
            Dict mapping event_id to score (0-100)
        """
        if not self.enabled or not events:
            return {}

        try:
            types = self.genai_types

            # Build event summaries for the prompt
            event_summaries = []
            for e in events:
                summary = (
                    f"ID: {e.get('id')}\n"
                    f"Title: {e.get('title')}\n"
                    f"Description: {e.get('description', 'N/A')}\n"
                    f"Date: {e.get('date', 'TBD')} at {e.get('time', 'TBD')}\n"
                    f"Venue: {e.get('venue', 'TBD')}\n"
                    f"Cost: {e.get('cost', 'Unknown')}\n"
                    f"Category: {e.get('category', 'Unknown')}"
                )
                event_summaries.append(summary)

            events_text = "\n\n---\n\n".join(event_summaries)

            prompt = f"""You are a {school_name} student evaluating upcoming events for a weekly digest.

STEP 1 - IDENTIFY DUPLICATE EVENTS (CRITICAL - DO THIS FIRST):
Scan ALL events and identify duplicates. Events are DUPLICATES if:
- Same or very similar title (even with minor wording differences)
- Same date and same/similar venue
- IGNORE the Category field - same event can appear in different categories!

Example duplicates:
- "CUIMC Well-Being Fair!" in COLUMBIA_EVENT and "CUIMC Well-Being Fair!" in CULTURE = DUPLICATE
- "Career Expo" and "Virtual Career Expo" on same date = likely DUPLICATE
- Events at "50 Haven Ave" and "Riverview Lounge" on same date/time = likely SAME VENUE

For ALL duplicates: Score the BEST one 70-85, score ALL OTHERS 5-15.

STEP 2 - IDENTIFY SIMILAR EVENT TYPES:
- Sports games: Pick the ONE best matchup, score it 70-85. Score ALL other games 15-25.
- Women's sports: Score 25-35 points LOWER than men's equivalent

STEP 3 - SCORE REMAINING UNIQUE EVENTS (0-100):
Consider these factors:
- Excitement & Fun Factor: Would students genuinely enjoy this?
- Relevance: How relevant to student life, career, social activities?
- Accessibility: Easy to attend? (location, cost, timing)
- Uniqueness: Special opportunity or just routine?
- Social Appeal: Would students go with friends?

VARIETY IS KEY:
- Final digest should have diverse event types
- Don't let sports dominate (max 1-2)
- Prefer variety: 1 sports, 2-3 career, 2-3 cultural/food, 1-2 other

EVENTS TO SCORE:

{events_text}

Return a JSON object with "scores" array. Each item must have:
- id: The event ID exactly as provided
- score: Integer 0-100
- reason: One sentence explaining the score (MUST say "DUPLICATE of [other event]" if it's a duplicate)

Example format:
{{"scores": [
  {{"id": "event_1234", "score": 85, "reason": "Free career fair with major employers on campus"}},
  {{"id": "event_5678", "score": 8, "reason": "DUPLICATE of CUIMC Well-Being Fair in event_1234"}}
]}}

Score ALL events. Respond with valid JSON only."""

            config = types.GenerateContentConfig(
                temperature=0.3,  # Slightly higher for nuanced judgment
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config,
            )

            # Extract text from response
            text = self._extract_response_text(response)

            # Parse scores from response
            return self._parse_scores_response(text, events)

        except Exception as e:
            print(f"[warn] AI scoring failed: {e}")
            # Return default scores as fallback
            return {e.get("id"): 50.0 for e in events}

    def _parse_scores_response(
        self, text: str, events: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Parse scoring response and return id -> score mapping."""
        scores = {}

        # Default score for any events not scored
        default_score = 50.0

        if not text:
            return {e.get("id"): default_score for e in events}

        text = text.strip()

        # Remove markdown code blocks
        if "```" in text:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1).strip()

        # Find JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()

        try:
            data = json.loads(text)

            if isinstance(data, dict) and "scores" in data:
                for item in data["scores"]:
                    if isinstance(item, dict) and "id" in item and "score" in item:
                        event_id = item["id"]
                        score = item["score"]
                        # Validate score is a number between 0-100
                        if isinstance(score, (int, float)) and 0 <= score <= 100:
                            scores[event_id] = float(score)

        except json.JSONDecodeError:
            pass

        # Fill in default scores for any missing events
        for e in events:
            event_id = e.get("id")
            if event_id and event_id not in scores:
                scores[event_id] = default_score

        return scores
