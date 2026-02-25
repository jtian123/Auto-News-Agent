# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto News Agent is a weekly campus culture intelligence system that aggregates student-relevant events using Google Gemini's search grounding capabilities. It runs 7 parallel subagents, deduplicates results, scores them using AI, then outputs a dated JSON digest and generates Instagram poster images.

## Development Commands

```bash
# Install in development mode
pip install -e .

# Run the pipeline (requires GEMINI_API_KEY in environment)
export GEMINI_API_KEY=your_key
PYTHONPATH=src .venv/bin/python -m auto_news_agent.cli --campus usc_la --print

# Run pipeline and generate poster images
PYTHONPATH=src .venv/bin/python -m auto_news_agent.cli --campus ucla --generate-posters

# Generate posters from existing digest (skip pipeline)
PYTHONPATH=src .venv/bin/python -m auto_news_agent.cli --posters-only outputs/ucla_weekly_digest_2026-01-23.json --campus ucla

# Available campus IDs: usc_la, ucla, ucb, uw, columbia, nyu, stanford
```

## Architecture

### Pipeline Flow

```
Campus Profile (JSON)
    ↓
7 Subagents (parallel via asyncio.gather)
    ↓
Gemini Search with grounding → JSON event extraction
    ↓
CandidateItems (structured event data)
    ↓
Deduplicate (fuzzy title matching)
    ↓
AI Scoring (single Gemini call for all events)
    ↓
Apply Constraints (min/max per category)
    ↓
FinalPicks (8 scored events)
    ↓
Weekly Digest JSON: {campus_id}_weekly_digest_{date}.json
    ↓ (optional: --generate-posters)
Image Generation Pipeline
    ↓
Pair events by category (4 pairs from 8 events)
    ↓
Generate dynamic prompts (LEGO voxel style)
    ↓
Gemini 3 Pro Image Preview → PNG posters
    ↓
Outputs: outputs/posters/{campus_id}_poster_{n}_{date}.png
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `cli.py` | Entry point, argument parsing, poster generation flags |
| `pipeline.py` | Orchestrates subagents, AI scoring, and output |
| `gemini_client.py` | Gemini API: search grounding + batch AI scoring |
| `aggregator.py` | Fuzzy deduplication, constraint enforcement |
| `subagents/base.py` | Subagent class with structured event extraction |
| `subagents/registry.py` | Factory for 7 predefined subagent specs |
| `config.py` | CampusProfile dataclass and loader |
| `schemas.py` | CandidateItem and FinalPick dataclasses |
| `image_generator.py` | Poster image generation using Gemini 3 Pro |

### Event Schema

Events have these fields:
- `title`, `description`: Event name and details
- `date` (YYYY-MM-DD), `time`: When it happens
- `venue`, `address`: Where it happens
- `source_url`, `source_name`: Verified source from Gemini grounding
- `why_relevant`: Why students should care
- `cost`: Price info (Free, $20, etc.)
- `category`: {SCHOOL}_EVENT, {CITY}_EVENT, FOOD_DRINK, SPORTS, CULTURE, HOUSING, CLUBS
- `score`: AI-generated score 0-100

### AI Scoring System

Events are scored by Gemini in a single batch call after deduplication. The AI evaluates:
- **Excitement & Fun Factor**: Would students enjoy this?
- **Relevance**: How relevant to student life/career/social?
- **Accessibility**: Easy to attend? (location, cost, timing)
- **Uniqueness**: Special opportunity or routine?
- **Social Appeal**: Would students go with friends?

### Deduplication

Uses fuzzy title matching (Jaccard similarity on word sets):
- Same date + similarity > 0.7 = duplicate
- Very high similarity (> 0.9) regardless of date = duplicate
- Keeps higher-confidence version

### Image Generation Pipeline

Generates Instagram-ready poster images (4:5 aspect ratio) using Gemini 3 Pro Image Preview.

**Process:**
1. Load events from weekly digest JSON
2. Pair events by similar category (e.g., two LA_EVENTs together)
3. Generate dynamic prompt for each pair with LEGO voxel style
4. Call `gemini-3-pro-image-preview` model for image generation
5. Save PNG images and text prompts

**Poster Design:**
- LEGO voxel / block-based 3D illustration style
- Two events per poster (top and bottom sections)
- Each section has distinct visual scene (different angles, colors, compositions)
- Text overlays: title, date/time, venue, cost badge
- Footer: "This week at {school} · {city}"
- Campus-specific aesthetic (school name, city style)

**CLI Flags:**
- `--generate-posters`: Generate posters after running pipeline
- `--posters-only PATH`: Generate posters from existing digest (skip pipeline)

**Output Files:**
- `outputs/posters/{campus_id}_poster_{n}_{date}.png` - Generated images
- `outputs/posters/prompts/{campus_id}_poster_{n}_{date}.txt` - Saved prompts

## Configuration

Campus profiles in `campus_profiles/` control:
- `campus_id`: Unique identifier (used in output filenames)
- `school_name`: Full school name
- `school_aliases`: Short names for search queries
- `city`: Primary city
- `region_aliases`: Nearby areas for local events
- `content_categories`: Event category types
- `weekly_constraints`: min/max per category, total final_picks

**Deprecated fields (not used):**
- `transit_keywords`: Was for transit-related searches
- `trusted_domains`: Was for source filtering

## Outputs

Generated in `outputs/`:
- `{campus_id}_weekly_digest_{YYYY-MM-DD}.json` - Final picks with full event details and AI scores
- `{campus_id}_run_report_{YYYY-MM-DD}.json` - Pipeline statistics per subagent

Generated in `outputs/posters/` (when using `--generate-posters` or `--posters-only`):
- `{campus_id}_poster_{n}_{YYYY-MM-DD}.png` - Instagram poster images (4:5 ratio)
- `prompts/{campus_id}_poster_{n}_{YYYY-MM-DD}.txt` - Text prompts used for generation

## Key Design Decisions

- **Profile-driven**: All campus-specific behavior from JSON config
- **Parallel execution**: Subagents run concurrently via `asyncio.gather`
- **Structured extraction**: Gemini returns JSON, parsed and validated
- **AI scoring**: Single Gemini call scores all deduplicated events semantically
- **Grounding metadata**: Source URLs from Gemini's `groundingChunks`
- **Graceful degradation**: Failures log warnings but don't crash
- **Dynamic prompts**: Image prompts generated from event data, no hardcoded scenes

## Gemini API Notes

**Important constraints discovered during development:**

1. **Search tool incompatibility**: Cannot use `response_mime_type="application/json"` with Google Search grounding tool. Must parse JSON from text response instead.

2. **Model selection**:
   - Search/text: `gemini-2.0-flash` (with `google_search` tool)
   - Image generation: `gemini-3-pro-image-preview`

3. **Grounding response**: Source URLs come from `response.candidates[0].grounding_metadata.grounding_chunks`, not the text content.

4. **Image extraction**: Generated images are in `response.parts[].inline_data`, use `part.as_image()` to convert.

## Coding Style

- Python: 4-space indentation, type hints throughout
- JSON: 2-space indentation, snake_case field names
- Use dataclasses for structured data
