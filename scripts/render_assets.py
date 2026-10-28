"""Regenerate README assets from the example migrations.

Usage:  python scripts/render_assets.py
Writes: docs/lint-summary.json, docs/images/lint-report.png, docs/images/findings-map.svg
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sql_migration_linter.lint import lint_directory  # noqa: E402
from sql_migration_linter.report import render_json, render_text  # noqa: E402
from sql_migration_linter.rules import RULES, SEVERITY_ORDER  # noqa: E402

BG = "#0d1117"
CHROME = "#161b22"
FG = "#e6edf3"
MUTED = "#8b949e"
SEVERITY_COLORS = {
    "critical": "#f85149",
    "high": "#db6d28",
    "medium": "#d29922",
    "low": "#2f81f7",
}


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_terminal(text: str, out_path: Path, title: str) -> None:
    font = load_font(14)
    lines = text.expandtabs(4).splitlines() or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    char_width = probe.textlength("M", font=font)
    line_height = 20
    pad = 22
    width = int(max(len(line) for line in lines) * char_width) + pad * 2
    height = pad * 2 + len(lines) * line_height + 42
    image = Image.new("RGB", (max(width, 760), height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, image.width, 34], fill=CHROME)
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        draw.ellipse([16 + index * 22, 10, 28 + index * 22, 22], fill=color)
    draw.text((92, 9), title, font=load_font(13), fill=MUTED)

    for row, line in enumerate(lines):
        color = FG
        stripped = line.strip()
        if row == 0:
            color = "#79c0ff"
        elif stripped in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            color = SEVERITY_COLORS[stripped.lower()]
        elif "fix:" in line:
            color = "#3fb950"
        elif line.startswith("="):
            color = "#30363d"
        elif "risk" in line and "grade" in line:
            color = "#d29922"
        draw.text((pad, 48 + row * line_height), line, font=font, fill=color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def render_findings(result, out_path: Path) -> None:
    per_rule: dict[str, int] = {}
    for finding in result.findings:
        per_rule[finding.code] = per_rule.get(finding.code, 0) + 1
    ordered = sorted(per_rule.items(), key=lambda item: item[1], reverse=True)[:11]
    names = [code for code, _ in ordered][::-1]
    counts = [count for _, count in ordered][::-1]
    colors = [SEVERITY_COLORS[RULES[code].severity] for code in names]

    per_file: dict[str, dict[str, int]] = {}
    for finding in result.findings:
        row = per_file.setdefault(finding.file, {severity: 0 for severity in SEVERITY_ORDER})
        row[finding.severity] += 1
    files = [
        migration.filename
        for migration in result.migrations
        if migration.filename in per_file
    ]
    files = list(reversed(files))

    fig, (ax_rule, ax_file) = plt.subplots(
        1, 2, figsize=(13.6, 5.0), gridspec_kw={"width_ratios": [1.25, 1]}
    )
    fig.patch.set_facecolor("#ffffff")

    ax_rule.barh(names, counts, color=colors)
    for index, count in enumerate(counts):
        ax_rule.text(count + 0.05, index, str(count), va="center", fontsize=8, color="#24292f")
    ax_rule.set_xlabel("findings")
    ax_rule.set_title("Findings by rule", fontsize=11, loc="left")
    ax_rule.set_xlim(0, max(counts) + 1)
    ax_rule.tick_params(axis="y", labelsize=8)
    ax_rule.grid(axis="x", linestyle=":", alpha=0.45)
    for spine in ("top", "right"):
        ax_rule.spines[spine].set_visible(False)

    left = [0] * len(files)
    for severity in ("critical", "high", "medium", "low"):
        values = [per_file[name].get(severity, 0) for name in files]
        ax_file.barh(files, values, left=left, color=SEVERITY_COLORS[severity], label=severity)
        left = [a + b for a, b in zip(left, values, strict=True)]
    ax_file.set_xlabel("findings")
    ax_file.set_title("Findings per migration file", fontsize=11, loc="left")
    ax_file.tick_params(axis="y", labelsize=8)
    ax_file.legend(fontsize=8, frameon=False, ncol=4, loc="upper center",
                   bbox_to_anchor=(0.5, -0.13))
    ax_file.grid(axis="x", linestyle=":", alpha=0.45)
    for spine in ("top", "right"):
        ax_file.spines[spine].set_visible(False)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format=out_path.suffix.lstrip(".") or "svg", transparent=False)
    plt.close(fig)


def main() -> int:
    images = ROOT / "docs" / "images"
    images.mkdir(parents=True, exist_ok=True)
    result = lint_directory(ROOT / "examples" / "migrations")

    (ROOT / "docs" / "lint-summary.json").write_text(
        json.dumps(json.loads(render_json(result)), indent=2), encoding="utf-8"
    )
    header = "migration-lint lint --dir examples/migrations\n\n"
    render_terminal(
        header + render_text(result, root_label="examples/migrations"),
        images / "lint-report.png",
        "migration-lint  -  examples/migrations",
    )
    render_findings(result, images / "findings-map.svg")
    print(
        f"files={result.files} findings={len(result.findings)} score={result.score} "
        f"grade={result.grade} critical={result.counts['critical']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
