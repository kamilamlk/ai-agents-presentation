# deck/ — the talk as data

The deck is a spec, not a binary. Edits are made in the JSON and the deck is
rebuilt, never patched in PowerPoint.

| File | What it is |
|---|---|
| [`deck_brand.json`](deck_brand.json) | **the current deck** — 22 slides, one object per slide |
| [`OUTLINE.md`](OUTLINE.md) | the same 22 slides as readable text — generated, do not edit |
| [`render_outline.py`](render_outline.py) | the published renderer: spec → `OUTLINE.md` |
| [`deck.json`](deck.json) | the earlier 14-slide spec, kept for history |
| [`build_deck_from_miro.py`](build_deck_from_miro.py) | the standalone `python-pptx` builder that drew the first version |

```bash
python3 deck/render_outline.py            # rewrite OUTLINE.md from the spec
python3 deck/render_outline.py --check    # fail if OUTLINE.md is stale
```

## Why there is no .pptx here

The slides are rendered from a corporate template with licensed fonts. Neither
is ours to publish, so the build step is missing on purpose and `*.pptx`,
`*.pdf`, `deck/out/` and `deck/fonts/` are in `.gitignore`.

`OUTLINE.md` exists so the talk is still legible without any of that:
`render_outline.py` reads the same spec the real deck is built from, needs no
dependencies, and `--check` keeps the two from drifting apart.

`build_deck_from_miro.py` is self-contained and does render a `.pptx` — it draws
every shape itself with no template and no fonts to license. It also hardcodes
the first version of the talk rather than reading either spec, which is why it
is kept as history and not as the build step.

## The slide spec

One object per slide, `layout` picks the shape, the remaining fields are its
content:

```json
{
  "layout": "cards",
  "kicker": "Prompt caching",
  "heading": "CACHING",
  "cards": [["Plain input, every call", "1.00x"],
            ["A cache write, once", "1.25x"],
            ["A cache read, after that", "0.10x"]]
}
```

| Field | Used by |
|---|---|
| `heading`, `title` | the line at the top |
| `kicker` | the small line above it |
| `statement` | the one sentence a `statement` or `question` slide is |
| `body` | the paragraph under the heading |
| `groups` + `items` | a list, split evenly across the group labels |
| `groups` + `stats` | the same, with `["$5", "input"]` pairs |
| `blocks`, `cards` | four blocks / three cards, `[head, text]` pairs |
| `code` | a verbatim block, newlines included |
| `speakers`, `subtitle`, `tags` | cover, closing and section slides |

Twelve layouts are in use: `cover-center`, `agenda`, `statement`, `question`,
`list`, `blocks4`, `code`, `code-plain`, `stats`, `cards`, `section`, `closing`.
Adding one is one function in `render_outline.py`.

## Which slide runs which file

The mapping is in the root [`README.md`](../README.md#the-deck) — every slide
that shows a number or a log has a file in `examples/` that produced it.
