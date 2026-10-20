"""Accuracy probe: the tight red/green loop for classification quality.

One command that goes red on the reported symptom (wrong proposal for a
known scan) and green once fixed. Run from the repo root with creds in the
environment (`.env` with AI_* names):

    set -a; source .env; set +a
    uv run python scripts/probe_accuracy.py letter.png \\
        --expect-branch "DBS Kovan" \\
        --expect-department "Wealth & Investment Advisory" \\
        --expect-recipient "Lim Hui Ling"

Blank control (does the model even look at the image? If a blank page gets
~the same answers as a real letter, vision input is being ignored):

    uv run python scripts/probe_accuracy.py --control-blank \\
        --expect-branch "branch cannot be determined from this page" \\
        --expect-department "none of the listed departments fits" \\
        --expect-recipient "recipient missing or not one of the listed people"

Exit 0 = all expectations met. Exit 1 = mismatch (prints diff).
Never prints credentials.
"""

import argparse
import json
import sys

from PIL import Image

from mailroom_clf import (
    classify_with_raw_bytes,
    top_choices,
)


def _blank_png():
    img = Image.new("RGB", (1200, 1500), "white")
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Probe classification accuracy.")
    ap.add_argument("image", nargs="?", help="scan to classify")
    ap.add_argument("--control-blank", action="store_true",
                    help="classify a blank white page instead of a file")
    ap.add_argument("--expect-branch", default=None)
    ap.add_argument("--expect-department", default=None)
    ap.add_argument("--expect-recipient", default=None)
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args(argv)

    if a.control_blank:
        raw, mime = _blank_png(), "image/png"
    elif a.image:
        with open(a.image, "rb") as f:
            raw = f.read()
        mime = "image/png" if a.image.lower().endswith(".png") else "image/jpeg"
    else:
        ap.print_help()
        return 2

    try:
        summary, data = classify_with_raw_bytes(raw, mime)
    except Exception as e:
        print(f"PROBE-ERROR: {e}")
        return 2

    print("CHOICES:", json.dumps({k: summary[k]
                                  for k in ("branch", "department", "recipient")}))
    print("CONF:", json.dumps(summary["confidence"]))
    print("USAGE:", json.dumps(summary.get("usage")))
    for field, q in data["answers"].items():
        print(f"TOP{a.top}-{field}:",
              json.dumps([[k, round(v, 3)] for k, v in
                          top_choices(q["probabilities"], a.top)]))

    expected = {"branch": a.expect_branch, "department": a.expect_department,
                "recipient": a.expect_recipient}
    failures = {f: (summary[f], exp) for f, exp in expected.items()
                if exp is not None and summary[f] != exp}
    if failures:
        print("MISMATCH:", json.dumps({f: {"got": g, "want": w}
                                       for f, (g, w) in failures.items()}))
        return 1
    print("PROBE-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
