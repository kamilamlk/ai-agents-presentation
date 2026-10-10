"""Render the deck spec as Markdown, so the talk is readable without PowerPoint.

The .pptx is built from a corporate template with licensed fonts and is not
published here. This script is the published renderer: it reads the same spec
the real deck is built from and writes an outline anyone can read on GitHub.

    python3 deck/render_outline.py                 # writes deck/OUTLINE.md
    python3 deck/render_outline.py --check         # fails if OUTLINE.md is stale

No dependencies. One layout per function, so adding a layout is one function.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPEC = HERE / "deck_brand.json"
OUT = HERE / "OUTLINE.md"


def chunk(items, groups):
    """Split items evenly across groups, the way the slide lays them out."""
    if not items:
        return []
    if not groups or len(items) % len(groups):
        return [(None, list(items))]
    size = len(items) // len(groups)
    return [(g, items[i * size:(i + 1) * size]) for i, g in enumerate(groups)]


def render(slide, number):
    layout = slide.get("layout", "")
    out = []

    title = slide.get("title") or slide.get("heading") or slide.get("statement") or ""
    out.append(f"## {number}. {title.replace(chr(10), ' ')}".rstrip())
    out.append("")
    out.append(f"`{layout}`")
    out.append("")

    if kicker := slide.get("kicker"):
        out.append(f"**{kicker.replace(chr(10), ' ')}**")
        out.append("")

    # A statement slide puts its line in the title; anywhere else it is the point.
    if (statement := slide.get("statement")) and statement != title:
        out.append(f"> {statement}")
        out.append("")

    if subtitle := slide.get("subtitle"):
        out.append(f"*{subtitle}*")
        out.append("")

    for name, role in slide.get("speakers", []):
        out.append(f"*{name} — {role}*")
        out.append("")

    if tags := slide.get("tags"):
        out.append(" · ".join(f"`{t}`" for t in tags))
        out.append("")

    if body := slide.get("body"):
        out.append(body)
        out.append("")

    for group, items in chunk(slide.get("items", []), slide.get("groups", [])):
        if group:
            out.append(f"**{group}**")
            out.append("")
        out.extend(f"- {i}" for i in items)
        out.append("")

    for group, stats in chunk(slide.get("stats", []), slide.get("groups", [])):
        if group:
            out.append(f"**{group}**")
            out.append("")
        out.extend(f"- **{value}** — {label}" for value, label in stats)
        out.append("")

    out.extend(f"- **{head}** — {text}" for head, text in slide.get("blocks", []))
    if slide.get("blocks"):
        out.append("")

    out.extend(f"- **{head}** — {text}" for head, text in slide.get("cards", []))
    if slide.get("cards"):
        out.append("")

    # A groups entry with no items is a label on the slide, not a list header.
    if slide.get("groups") and not slide.get("items") and not slide.get("stats"):
        out.extend(f"*{g}*" for g in slide["groups"])
        out.append("")

    if code := slide.get("code"):
        out.append("```")
        out.append(code)
        out.append("```")
        out.append("")

    return out


def build():
    spec = json.loads(SPEC.read_text())
    slides = spec["slides"]

    out = [
        "# BUILD THE HARNESS — slide by slide",
        "",
        f"{len(slides)} slides, {spec['event']}. Generated from "
        f"[`deck_brand.json`](deck_brand.json) by "
        "[`render_outline.py`](render_outline.py) — edit the spec, not this file.",
        "",
        "The rendered `.pptx` is not published: it is built from a corporate "
        "template with licensed fonts. This is the same content, as text.",
        "",
        "---",
        "",
    ]
    for number, slide in enumerate(slides, 1):
        out.extend(render(slide, number))
        out.append("---")
        out.append("")

    # Each block ends with its own blank line, so runs of them pile up.
    squeezed = [
        line for i, line in enumerate(out)
        if line.strip() or (i and out[i - 1].strip())
    ]
    return "\n".join(squeezed).rstrip() + "\n"


if __name__ == "__main__":
    text = build()

    if "--check" in sys.argv:
        current = OUT.read_text() if OUT.exists() else ""
        if current != text:
            print(f"stale: {OUT.name} does not match {SPEC.name}")
            print("       run: python3 deck/render_outline.py")
            sys.exit(1)
        print(f"ok: {OUT.name} matches {SPEC.name}")
    else:
        OUT.write_text(text)
        print(f"wrote {OUT.relative_to(HERE.parent)}  "
              f"({len(json.loads(SPEC.read_text())['slides'])} slides)")
