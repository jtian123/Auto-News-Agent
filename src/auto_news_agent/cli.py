from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure the src/ directory is on sys.path when installed editable is misbehaving.
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from .pipeline import run_pipeline
from .image_generator import ImageGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Auto News Agent pipeline")
    parser.add_argument("--campus", default="usc_la", help="Campus profile ID (default: usc_la)")
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parents[2]), help="Project root")
    parser.add_argument("--print", dest="should_print", action="store_true", help="Print final picks to stdout")
    parser.add_argument("--generate-posters", action="store_true", help="Generate Instagram poster images after pipeline")
    parser.add_argument("--posters-only", type=str, metavar="DIGEST_PATH", help="Generate posters from existing digest JSON (skip pipeline)")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    base_dir = Path(args.base_dir)

    # If --posters-only, just generate posters from existing digest
    if args.posters_only:
        digest_path = Path(args.posters_only)
        if not digest_path.exists():
            print(f"[error] Digest file not found: {digest_path}")
            sys.exit(1)

        generator = ImageGenerator()
        output_dir = base_dir / "outputs" / "posters"
        images = generator.generate_posters(digest_path, output_dir, args.campus)
        print(f"[info] Generated {len(images)} poster images")
        return

    # Run the main pipeline
    picks = run_pipeline(args.campus, args.base_dir)

    if args.should_print:
        print(json.dumps([p.to_dict() for p in picks], indent=2))

    # Generate posters if requested
    if args.generate_posters:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        digest_path = base_dir / "outputs" / f"{args.campus}_weekly_digest_{today_str}.json"

        if digest_path.exists():
            generator = ImageGenerator()
            output_dir = base_dir / "outputs" / "posters"
            images = generator.generate_posters(digest_path, output_dir, args.campus)
            print(f"[info] Generated {len(images)} poster images")
        else:
            print(f"[warn] Digest file not found: {digest_path}")


if __name__ == "__main__":
    main()
