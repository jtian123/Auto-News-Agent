from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple


def get_school_style(campus_id: str) -> Dict[str, str]:
    """Get school-specific style keywords."""
    styles = {
        "usc": {"school": "USC", "city": "Los Angeles", "colors": "cardinal red and gold"},
        "ucla": {"school": "UCLA", "city": "Los Angeles", "colors": "blue and gold"},
        "ucb": {"school": "UC Berkeley", "city": "Berkeley", "colors": "blue and gold"},
        "uw": {"school": "UW", "city": "Seattle", "colors": "purple and gold"},
        "columbia": {"school": "Columbia", "city": "New York", "colors": "Columbia blue and white"},
        "nyu": {"school": "NYU", "city": "New York", "colors": "purple and white"},
        "stanford": {"school": "Stanford", "city": "Palo Alto", "colors": "cardinal red and white"},
    }
    return styles.get(campus_id, {"school": "University", "city": "City", "colors": "blue and white"})


def pair_events_by_score(events: List[Dict[str, Any]]) -> List[Tuple[Dict, Dict]]:
    """
    Pair events for poster generation by score (Strategy 1).

    Events are already sorted by score from the pipeline.
    Pair adjacent events so each poster has similarly-important events:
    - Poster 1: Event #1 + Event #2 (highest scores)
    - Poster 2: Event #3 + Event #4
    - Poster 3: Event #5 + Event #6
    - etc.
    """
    if len(events) < 2:
        return [(events[0], None)] if events else []

    pairs = []

    # Pair adjacent events (already sorted by score)
    for i in range(0, len(events) - 1, 2):
        pairs.append((events[i], events[i + 1]))

    # Handle odd event (single-event poster)
    if len(events) % 2 == 1:
        pairs.append((events[-1], None))

    return pairs


def format_date(date_str: str) -> str:
    """Format date string for display."""
    if not date_str or date_str in ["TBD", "TBA"]:
        return "Date TBD"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return date_str


def generate_prompt(
    event1: Dict[str, Any],
    event2: Dict[str, Any] | None,
    campus_id: str,
    pair_index: int,
) -> str:
    """Generate image prompt for a pair of events."""

    style = get_school_style(campus_id)
    school = style["school"]
    city = style["city"]
    colors = style["colors"]

    # Event 1 details
    title1 = event1.get("title", "Event")
    date1_raw = event1.get("date", "TBD")
    time1_raw = event1.get("time", "TBD")
    venue1 = event1.get("venue", "TBD")
    cost1 = event1.get("cost", "")
    desc1 = event1.get("description", "")
    cat1 = event1.get("category", "EVENT")

    # Format date/time, hide if TBD or TBA
    date1 = format_date(date1_raw) if date1_raw and date1_raw not in ["TBD", "TBA"] else None
    time1 = time1_raw if time1_raw and time1_raw not in ["TBD", "TBA"] else None

    # Build date/time line (only show if at least one exists)
    datetime1_line = ""
    if date1 and time1:
        datetime1_line = f'- Medium text: "{date1} · {time1}"'
    elif date1:
        datetime1_line = f'- Medium text: "{date1}"'
    elif time1:
        datetime1_line = f'- Medium text: "{time1}"'

    cost1_badge = f'- Small badge: "{cost1}"' if cost1 else ""

    # Build sections
    if event2:
        title2 = event2.get("title", "Event")
        date2_raw = event2.get("date", "TBD")
        time2_raw = event2.get("time", "TBD")
        venue2 = event2.get("venue", "TBD")
        cost2 = event2.get("cost", "")
        desc2 = event2.get("description", "")
        cat2 = event2.get("category", "EVENT")

        # Format date/time, hide if TBD or TBA
        date2 = format_date(date2_raw) if date2_raw and date2_raw not in ["TBD", "TBA"] else None
        time2 = time2_raw if time2_raw and time2_raw not in ["TBD", "TBA"] else None

        # Build date/time line (only show if at least one exists)
        datetime2_line = ""
        if date2 and time2:
            datetime2_line = f'- Medium text: "{date2} · {time2}"'
        elif date2:
            datetime2_line = f'- Medium text: "{date2}"'
        elif time2:
            datetime2_line = f'- Medium text: "{time2}"'

        cost2_badge = f'- Small badge: "{cost2}"' if cost2 else ""

        bottom_section = f"""
================================================
BOTTOM SECTION — EVENT 2
================================================

EVENT INFO (use this to inspire the scene):
- Title: {title2}
- Category: {cat2}
- Description: {desc2}
- Venue: {venue2}

SCENE REQUIREMENTS:
- Create a DIFFERENT voxel-style scene from Event 1
- Main subjects should have strong blocky/cubic Minecraft aesthetic
- Background/environment can blend voxel style with semi-realistic elements
- Use a different camera angle (e.g., if Event 1 is left-angled, make this right-angled)
- Use Minecraft-style blocky characters for any people in the scene

TEXT OVERLAY (top-aligned within this section):
- Large bold title: "{title2}"
{datetime2_line}
- Small text: "{venue2}"
{cost2_badge}
- CRITICAL: DO NOT show "TBD" or "TBA" text on the image. If date/time is missing, simply omit that line entirely.
"""
    else:
        bottom_section = "(Single event poster - Event 1 takes full height)"

    prompt = f"""Create an illustrated poster in MINECRAFT VOXEL style for students at {school} in {city}.

CRITICAL STYLE REQUIREMENTS - MINECRAFT VOXEL AESTHETIC:
- Main subjects & focal points: Strong voxel/blocky style
  • People: Minecraft-style blocky characters (cubic heads, rectangular bodies)
  • Key objects: Blocky, pixelated forms with visible cubic structure
  • Featured buildings/venues: Voxelized architecture with cubic blocks

- Environment & background: Subtle voxel effect blended with realism
  • Sky, distant buildings, landscapes: Softer voxel treatment
  • Can use realistic textures with slight pixelation/blockiness
  • Ground/terrain: Minecraft-inspired but not pure cubes

- Overall feel: Minecraft world aesthetic, NOT pure LEGO plastic
  • Blocky/pixelated forms, but not necessarily "plastic bricks with studs"
  • Mix of voxel art and semi-realistic illustration
  • Color palette: depends on secene, school and city vibe.
  • Think: Minecraft promotional art or stylized voxel game renders

CANVAS & LAYOUT:
- Aspect ratio: 4:5 (Instagram feed format)
- HEADER at top: Minecraft-style badge/banner showing "{school} Weekly News"
  • Blocky, voxel-style badge design (like Minecraft UI element or name tag)
  • Use {school} official colors: {colors}
  • Should feel like a game menu header or title card
- Padding/margins on all edges - don't go edge-to-edge
- Vertical poster with TWO main event sections stacked below the header
- Top section = Event 1
- Bottom section = Event 2
- Clean background with clear separation between sections
- Leave breathing room around event sections (not full width)

ADDITIONAL STYLE NOTES:
- {school} campus and {city} city aesthetic with voxel treatment
- Characters should be clearly blocky/cubic (Minecraft-style)
- Text must be readable on a phone screen
- Isometric or slight 3/4 view angle to show depth

CRITICAL - VISUAL VARIETY RULES:
- The TWO sections MUST look DIFFERENT from each other
- Even if both events are similar (e.g., both career fairs), create DISTINCT visual scenes
- Vary: camera angle, color palette, scene composition, background elements
- Think of them as two different worlds/settings

================================================
TOP SECTION — EVENT 1
================================================

EVENT INFO (use this to inspire the scene):
- Title: {title1}
- Category: {cat1}
- Description: {desc1}
- Venue: {venue1}

SCENE REQUIREMENTS:
- Create a unique voxel-style scene that captures the essence of this specific event
- Main subjects (people, key objects) should have strong blocky/cubic Minecraft aesthetic
- Background/environment can blend voxel style with semi-realistic elements
- Include relevant visual elements based on the event type and description
- Use Minecraft-style blocky characters for any people in the scene

TEXT OVERLAY (top-aligned within this section):
- Large bold title: "{title1}"
{datetime1_line}
- Small text: "{venue1}"
{cost1_badge}
- CRITICAL: DO NOT show "TBD" or "TBA" text on the image. If date/time is missing, simply omit that line entirely.
{bottom_section}
================================================
FOOTER
================================================

- Optional: Small, minimal footer if needed for balance
  (Header already shows "{school} Weekly News")

FINAL RENDERING NOTES:
- CRITICAL: NEVER show "TBD" or "TBA" text on the image. If date or time information is missing, omit that text line completely.
- Main subjects (people, featured objects) must have clear blocky/voxel structure
- Environment/background can be more subtle - blend voxel with semi-realistic style
- Think Minecraft promotional art: recognizable voxel aesthetic without being 100% cubes
- Balance between stylized voxel art and readability/appeal
- Vibrant colors but natural tones (not toy plastic)
- Balanced spacing so text does not overlap important visuals
- Instagram-ready, clean composition with margins/padding
- IMPORTANT: Make each section visually unique and interesting on its own
"""
    return prompt


class ImageGenerator:
    """Generates Instagram poster images using Gemini 3 Pro Image Preview."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = None
        self.model_name = "gemini-3-pro-image-preview"

        if not self.api_key:
            print("[warn] GEMINI_API_KEY is missing; image generation is disabled.")
            return

        try:
            from google import genai

            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"[warn] Failed to initialize Gemini client: {e}")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def generate_image(self, prompt: str, output_path: Path) -> bool:
        """Generate an image from prompt and save to output_path."""
        if not self.enabled:
            print("[warn] Image generation is disabled")
            return False

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
            )

            # Extract and save image
            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(str(output_path))
                    print(f"[info] Generated image: {output_path}")
                    return True

            print(f"[warn] No image in response for {output_path}")
            return False

        except Exception as e:
            print(f"[warn] Image generation failed: {e}")
            return False

    def generate_posters(
        self,
        digest_path: Path,
        output_dir: Path,
        campus_id: str,
    ) -> List[Path]:
        """
        Generate poster images from a weekly digest JSON file.

        Returns list of generated image paths.
        """
        # Load digest
        digest = json.loads(digest_path.read_text())
        if not digest:
            print("[warn] Empty digest, no images to generate")
            return []

        # Create output directories
        output_dir.mkdir(parents=True, exist_ok=True)
        prompts_dir = output_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        # Pair events by score (adjacent pairing)
        pairs = pair_events_by_score(digest)
        print(f"[info] Paired {len(digest)} events into {len(pairs)} poster groups (by score)")

        # Generate date string for filenames
        today_str = datetime.utcnow().strftime("%Y-%m-%d")

        generated_images = []

        for i, (event1, event2) in enumerate(pairs):
            pair_num = i + 1

            # Generate prompt
            prompt = generate_prompt(event1, event2, campus_id, i)

            # Save prompt
            prompt_path = prompts_dir / f"{campus_id}_poster_{pair_num}_{today_str}.txt"
            prompt_path.write_text(prompt)
            print(f"[info] Saved prompt: {prompt_path}")

            # Generate image
            image_path = output_dir / f"{campus_id}_poster_{pair_num}_{today_str}.png"
            success = self.generate_image(prompt, image_path)

            if success:
                generated_images.append(image_path)

        return generated_images


def generate_posters_from_digest(
    digest_path: str | Path,
    output_dir: str | Path,
    campus_id: str,
) -> List[Path]:
    """Convenience function to generate posters from a digest file."""
    generator = ImageGenerator()
    return generator.generate_posters(
        Path(digest_path),
        Path(output_dir),
        campus_id,
    )
