"""CLI: thin wrapper over the library. No new logic lives here."""

import argparse
import json
import sys

from .client import build_payload, classify, summarize
from .config import BRANCHES, NOT_IN_LIST
from .questions import build_questions


def selftest():
    """Offline check of the routing logic using a hand-made response in the shape
    the client reads (answers -> choice / probabilities / confidence).
    This does NOT test the live endpoint."""
    def ans(choice, conf):
        return {"type": "choice", "choice": choice, "probabilities": {choice: conf}, "confidence": conf}
    good = {"answers": {"branch": ans("DBS_TOA_PAYOH", 0.97), "department": ans("CUSTOMER_SERVICE", 0.91),
                        "recipient": ans("tan_wei_ming", 0.95)}}
    bad = {"answers": {"branch": ans("DBS_TOA_PAYOH", 0.97), "department": ans("CUSTOMER_SERVICE", 0.91),
                       "recipient": ans(NOT_IN_LIST, 0.88)}}
    g, b = summarize(good), summarize(bad)
    assert g["qc"]["tier"] == 1 and b["qc"]["tier"] == 0, (g, b)
    assert len(build_questions()["branch"]["criteria"]) == len(BRANCHES) + 1  # + unclear
    print("selftest ok")
    print(json.dumps(g, indent=2))
    print(json.dumps(b, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Classify the first page of a scanned mail item.")
    ap.add_argument("image", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
    elif a.image and a.dry_run:
        from .client import FIELDS
        for field in FIELDS:
            p = build_payload(a.image, only=[field])
            p["images"] = [p["images"][0][:60] + "...<truncated>"]
            print(f"### {field}")
            print(json.dumps(p, indent=2))
    elif a.image:
        print(json.dumps(classify(a.image), indent=2))
    else:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
