"""Build the blind human-review packet from a WORK-04 runs.jsonl (spec rev. 1 §5.2).

    python labs/work04_cognitive/build_review_packet.py <runs.jsonl> <packet_dir> <key.json>

The key file must be kept away from the reviewer until the forms are returned.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w04lab import human_review  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    key = human_review.build_packet(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(f"packet: {len(key)} reports -> {sys.argv[2]} (key: {sys.argv[3]})")
