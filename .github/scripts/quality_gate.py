"""Quality gate for the pipeline: every test must pass and coverage must reach the threshold.

    python .github/scripts/quality_gate.py coverage.json test-results/junit.xml --min 80

Exits 1 when a test failed, or when total coverage (statements and branches together, the figure
`coverage report` prints) is below ``--min``. Writes the verdict to ``$GITHUB_STEP_SUMMARY`` when
it is set, otherwise to the console.
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def failed_tests(junit: Path) -> tuple[int, int]:
    """Return (number of tests, number that failed or errored)."""
    cases = list(ET.parse(junit).iter("testcase"))
    bad = sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)
    return len(cases), bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("coverage", type=Path, help="coverage.json from `coverage json`")
    ap.add_argument("junit", type=Path, help="junit.xml from the test run")
    ap.add_argument("--min", type=float, default=80.0)
    args = ap.parse_args()

    totals = json.loads(args.coverage.read_text(encoding="utf-8"))["totals"]
    coverage = totals["percent_covered"]
    statements = 100 * totals["covered_lines"] / totals["num_statements"]
    branches = 100 * totals["covered_branches"] / totals["num_branches"]
    count, bad = failed_tests(args.junit)

    rows = [
        ("Tests passed", f"{count - bad} of {count}", "PASS" if bad == 0 else "FAIL"),
        (
            f"Total coverage (threshold {args.min:.0f}%)",
            f"{coverage:.1f}%",
            "PASS" if coverage >= args.min else "FAIL",
        ),
        ("Statement coverage", f"{statements:.1f}%", "info"),
        ("Branch coverage", f"{branches:.1f}%", "info"),
    ]
    ok = bad == 0 and coverage >= args.min
    lines = [
        f"## Coverage & quality gate: {'passed' if ok else 'failed'}",
        "",
        "| Check | Value | Result |",
        "|---|---:|:---:|",
        *(f"| {name} | {value} | {result} |" for name, value, result in rows),
        "",
    ]
    text = "\n".join(lines)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)

    if bad:
        print(f"::error title=Quality gate::{bad} test(s) failed")
    if coverage < args.min:
        print(f"::error title=Quality gate::coverage {coverage:.1f}% is below {args.min:.0f}%")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
