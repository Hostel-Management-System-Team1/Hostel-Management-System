"""Turn the JUnit XML and the coverage JSON into a GitHub job summary and annotations.

    python .github/scripts/ci_report.py test-results/junit.xml coverage.json

* Writes a Markdown report to ``$GITHUB_STEP_SUMMARY`` (printed to the console when the variable
  is not set, so it can be tried locally).
* Prints a ``::error`` workflow command for every failed or errored test, with the file and line
  of the deepest frame inside the repository, so the failure shows on the pull request's
  "Files changed" tab and in the run's annotations.
* Prints a ``::warning`` for a module whose coverage is below ``--warn-below`` (default 80%).

The exit code is non-zero when any test failed, so the step can run before the artefact upload.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

FRAME = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)')


def escape(text: str) -> str:
    """Escape a value for a workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def module_of(classname: str) -> str:
    """apps.fees.tests.PaymentTests -> apps.fees ; hms.test_security.X -> hms"""
    parts = classname.split(".")
    return ".".join(parts[:2]) if parts[0] == "apps" else parts[0]


def location(classname: str, trace: str, root: Path) -> tuple[str, int]:
    """Best file and line for a failure: the last traceback frame inside the repository."""
    best = None
    for match in FRAME.finditer(trace or ""):
        path = Path(match["file"])
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            continue
        if ".venv" in rel.parts or "site-packages" in rel.parts:
            continue
        best = (rel.as_posix(), int(match["line"]))
    if best:
        return best
    parts = classname.split(".")
    guess = "/".join(parts[:-1]) + ".py"
    return guess, 1


def read_tests(junit: Path, root: Path):
    tree = ET.parse(junit)
    cases = []
    for case in tree.iter("testcase"):
        outcome, detail = "passed", ""
        for tag in ("failure", "error", "skipped"):
            node = case.find(tag)
            if node is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                detail = (node.get("message") or "") + "\n" + (node.text or "")
                break
        classname = case.get("classname", "")
        cases.append(
            {
                "name": case.get("name", ""),
                "classname": classname,
                "time": float(case.get("time") or 0),
                "outcome": outcome,
                "detail": detail.strip(),
            }
        )
    return cases


def read_coverage(path: Path):
    """Read coverage.py's JSON report (``coverage json``): totals and one row per module."""
    data = json.loads(path.read_text(encoding="utf-8"))
    totals = data["totals"]
    total = {
        "line": 100 * totals["covered_lines"] / totals["num_statements"],
        "branch": 100 * totals["covered_branches"] / totals["num_branches"],
    }
    per_module = defaultdict(lambda: {"stmts": 0, "miss": 0, "br": 0, "brhit": 0})
    for filename, entry in data["files"].items():
        parts = filename.split("/")
        module = "/".join(parts[:2]) if parts[0] == "apps" else parts[0]
        s = entry["summary"]
        if not s["num_statements"]:
            continue
        m = per_module[module]
        m["stmts"] += s["num_statements"]
        m["miss"] += s["missing_lines"]
        m["br"] += s["num_branches"]
        m["brhit"] += s["covered_branches"]
    return total, per_module


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("junit", type=Path)
    ap.add_argument("coverage", type=Path, help="the file written by `coverage json`")
    ap.add_argument("--warn-below", type=float, default=80.0)
    args = ap.parse_args()
    root = Path.cwd().resolve()

    cases = read_tests(args.junit, root)
    counts = defaultdict(int)
    for c in cases:
        counts[c["outcome"]] += 1
    bad = [c for c in cases if c["outcome"] in ("failed", "error")]
    duration = sum(c["time"] for c in cases)

    for c in bad:
        file, line = location(c["classname"], c["detail"], root)
        title = f"{c['outcome'].title()}: {c['classname'].split('.')[-1]}.{c['name']}"
        first = c["detail"].splitlines()[0] if c["detail"] else "test failed"
        print(f"::error file={file},line={line},title={escape(title)}::{escape(first)}")

    total, modules = read_coverage(args.coverage)
    for name, m in sorted(modules.items()):
        covered = 100 * (m["stmts"] - m["miss"]) / m["stmts"] if m["stmts"] else 100
        if covered < args.warn_below:
            print(
                f"::warning title=Low coverage::{name} is at {covered:.1f}% "
                f"(below {args.warn_below:.0f}%)"
            )

    out = []
    verdict = "All tests passed" if not bad else f"{len(bad)} test(s) failed"
    out.append(f"## Test report: {verdict}\n")
    out.append("| Tests | Passed | Failed | Errors | Skipped | Time |")
    out.append("|---:|---:|---:|---:|---:|---:|")
    out.append(
        f"| {len(cases)} | {counts['passed']} | {counts['failed']} | {counts['error']} "
        f"| {counts['skipped']} | {duration:.0f} s |\n"
    )

    by_module = defaultdict(lambda: defaultdict(int))
    for c in cases:
        by_module[module_of(c["classname"])][c["outcome"]] += 1
    out.append("### Tests by module\n")
    out.append("| Module | Tests | Passed | Failed / errors |")
    out.append("|---|---:|---:|---:|")
    for name, r in sorted(by_module.items()):
        n = sum(r.values())
        out.append(f"| `{name}` | {n} | {r['passed']} | {r['failed'] + r['error']} |")
    out.append("")

    out.append("### Coverage\n")
    out.append(
        f"**Statement coverage {total['line']:.1f}%, branch coverage {total['branch']:.1f}%**\n"
    )
    out.append("| Module | Statements | Missed | Statement coverage | Branches | Branch coverage |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for name, m in sorted(modules.items()):
        out.append(
            f"| `{name}` | {m['stmts']} | {m['miss']} | {pct(m['stmts'] - m['miss'], m['stmts'])} "
            f"| {m['br']} | {pct(m['brhit'], m['br'])} |"
        )
    out.append("")

    icon = {"passed": "PASS", "failed": "FAIL", "error": "ERROR", "skipped": "SKIP"}
    out.append("### Unit tests\n")
    out.append(
        f"<details><summary>All {len(cases)} tests, with their result (expand to read)</summary>\n"
    )
    out.append("| Result | Module | Test | Seconds |")
    out.append("|:---:|---|---|---:|")
    for c in sorted(cases, key=lambda c: (c["classname"], c["name"])):
        short = c["classname"].split(".", 1)[-1] if "." in c["classname"] else c["classname"]
        out.append(
            f"| {icon[c['outcome']]} | `{module_of(c['classname'])}` "
            f"| `{short}.{c['name']}` | {c['time']:.2f} |"
        )
    out.append("\n</details>\n")

    slow = sorted(cases, key=lambda c: c["time"], reverse=True)[:5]
    out.append("<details><summary>Five slowest tests</summary>\n")
    out.append("| Test | Seconds |")
    out.append("|---|---:|")
    for c in slow:
        out.append(f"| `{c['classname'].split('.', 1)[-1]}.{c['name']}` | {c['time']:.2f} |")
    out.append("\n</details>\n")

    if bad:
        out.append("### Failures\n")
        for c in bad:
            out.append(f"<details><summary><code>{c['classname']}.{c['name']}</code></summary>\n")
            out.append("```text")
            out.append(c["detail"][:3000])
            out.append("```\n</details>\n")

    text = "\n".join(out)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
