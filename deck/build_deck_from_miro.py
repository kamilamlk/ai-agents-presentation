"""
Build the workshop deck straight from the Miro frames, as a plain PowerPoint file.

    python3 build_deck_from_miro.py

No brand template, no embedded fonts, no copied shapes: every slide is drawn
from ordinary rectangles and text boxes, so the file opens anywhere.

Board geometry is reused one to one. A frame on the board is 1440 x 840 px with
content between x=64 and x=1376; the slide is 13.333 x 7.5 in. One board pixel
is 0.0089286 in, which makes the vertical mapping exact and leaves a small
horizontal margin. Font sizes come from the board the same way: 1 board px of
type is 0.643 pt.
"""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

SC = 7.5 / 840          # inches per board pixel
OX = (13.333 - 1440 * SC) / 2
FONT = "Arial"
MONO = "Courier New"

INK = RGBColor(0x1A, 0x1A, 0x1A)
BODY = RGBColor(0x59, 0x59, 0x59)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLUE_D = RGBColor(0x30, 0x5B, 0xAB)
BLUE_M = RGBColor(0x65, 0x9D, 0xF2)
BLUE_L = RGBColor(0xC6, 0xDC, 0xFF)
BLUE_F = RGBColor(0xF0, 0xF5, 0xFD)
PUR_D = RGBColor(0x66, 0x31, 0xD7)
PUR_L = RGBColor(0xDE, 0xDA, 0xFF)
PUR_F = RGBColor(0xF4, 0xF2, 0xFD)
RED_D = RGBColor(0xBD, 0x0A, 0x0A)
RED_L = RGBColor(0xFF, 0xC6, 0xC6)
RED_F = RGBColor(0xFF, 0xF0, 0xF0)
GREY_F = RGBColor(0xF7, 0xF7, 0xF7)
GREY_L = RGBColor(0xE7, 0xE7, 0xE7)

EVENT = "Dev Camp"


def X(px):
    return Inches(OX + px * SC)


def Y(px):
    return Inches(px * SC)


def D(px):
    return Inches(px * SC)


def P(px):
    return Pt(round(px * 0.643, 1))


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)
        self.slides = []
        self.nofooter = set()

    def page(self, badge=None, title=None, subtitle=None):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.slides.append(s)
        if badge:
            c = s.shapes.add_shape(MSO_SHAPE.OVAL, X(64), Y(48), D(64), D(64))
            paint(c, WHITE, BLUE_M)
            label(c, badge, P(26), BLUE_D, bold=True)
        if title:
            text(s, 152, 46, 900, 60, title, P(40), INK, bold=True)
        if subtitle:
            text(s, 152, 112, 1224, 40, subtitle, P(17), BODY)
        return s

    def save(self, path):
        total = len(self.slides)
        for i, s in enumerate(self.slides, 1):
            if i in self.nofooter:
                continue
            text(s, 1130, 806, 160, 20, EVENT, P(13), BODY, align=PP_ALIGN.RIGHT)
            text(s, 1296, 806, 80, 20, f"{i:02d} — {total:02d}", P(13), BODY,
                 align=PP_ALIGN.RIGHT)
        self.prs.save(path)
        print(f"{total} слайдов → {path}")


def paint(shape, fill, line=None):
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    shape.shadow.inherit = False


def label(shape, s, size, color, bold=False, font=FONT):
    tf = shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = s
    r.font.size = size
    r.font.color.rgb = color
    r.font.bold = bold
    r.font.name = font
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE


def text(slide, x, y, w, h, s, size, color, bold=False, font=FONT,
         align=PP_ALIGN.LEFT, spacing=None):
    tb = slide.shapes.add_textbox(X(x), Y(y), D(w), D(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(s.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.line_spacing = spacing
        r = p.add_run()
        r.text = line
        r.font.size = size
        r.font.color.rgb = color
        r.font.bold = bold
        r.font.name = font
    return tb


def box(slide, x, y, w, h, fill, line=None, radius=0.06):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, X(x), Y(y), D(w), D(h))
    try:
        sh.adjustments[0] = radius
    except Exception:
        pass
    paint(sh, fill, line)
    return sh


def card(slide, x, y, w, h, title, bodytext, fill=BLUE_F, line=BLUE_L,
         tcolor=INK, tsize=20):
    box(slide, x, y, w, h, fill, line)
    text(slide, x + 28, y + 24, w - 56, 30, title, P(tsize), tcolor, bold=True)
    if bodytext:
        text(slide, x + 28, y + 60, w - 56, h - 80, bodytext, P(14), BODY)


def chip(slide, x, y, w, s, fill, color):
    sh = box(slide, x, y, w, 26, fill, None, radius=0.5)
    label(sh, s, P(11), color, bold=True)


def strip(slide, x, y, w, s, fill=RED_F, line=RED_L, color=RED_D, size=18, h=90):
    box(slide, x, y, w, h, fill, line)
    text(slide, x + 28, y + 20, w - 56, h - 32, s, P(size), color, bold=True)


def eyebrow(slide, x, y, s, w=500):
    text(slide, x, y, w, 20, s, P(13), INK, bold=True)


# ---------------------------------------------------------------- the deck

d = Deck()

# 1 -- cover
d.nofooter.add(1)
s = d.page()
box(s, 0, 0, 1440, 840, INK)
text(s, 110, 250, 1100, 120, "BUILD THE HARNESS", Pt(54), WHITE, bold=True)
text(s, 110, 400, 900, 40, "The code around the model: what it does, what it costs,\nand how you know it worked.",
     P(20), RGBColor(0xC6, 0xDC, 0xFF))
text(s, 110, 640, 600, 30, "Kamila Malikova", P(22), WHITE, bold=True)
text(s, 110, 684, 600, 24, "Должность", P(16), RGBColor(0xC6, 0xDC, 0xFF))
text(s, 1000, 684, 376, 24, EVENT, P(16), RGBColor(0xC6, 0xDC, 0xFF), align=PP_ALIGN.RIGHT)

# 2 -- A. What this is about
s = d.page("A", "What this is about",
           "The model is not charged to read the part that never changes, and it is not the part that makes a product.")
text(s, 64, 170, 1312, 60, "A model is not a feature.\nThe code around a model is the feature.",
     P(33), INK, bold=True, spacing=0.9)
eyebrow(s, 64, 300, "TWO PLACES AI SHOWS UP")
card(s, 64, 330, 640, 150, "In the product",
     "The service calls a model at runtime, on every user file. The company pays for that every day, for as long as the service lives.",
     fill=RGBColor(0xFF, 0xF5, 0xED), line=RGBColor(0xF8, 0xD3, 0xAF))
card(s, 736, 330, 640, 150, "In your process",
     "You call a model while you build, and you pay once. Nothing in production depends on it.",
     fill=BLUE_F, line=BLUE_L)
text(s, 64, 500, 1312, 24, "One question tells them apart: if the API key is switched off tomorrow, does the product stop, or do I just type more?",
     P(17), BODY)
eyebrow(s, 64, 556, "WHEN A TASK EARNS A HARNESS")
text(s, 64, 584, 1312, 24, "Two things must be true: it repeats, and getting it wrong is expensive. One file a year does not earn a harness. Four hundred files a season does.",
     P(17), BODY)
strip(s, 64, 650, 1312,
      "The question you will be asked is not whether the model can do it. It can. The question is how you know it did, and what it costs every day.")

# 3 -- B. Agent = model + harness
s = d.page("B", "Agent = model + harness",
           "The model is a function: text in, text out. Everything else is code you write.")
b = box(s, 240, 176, 280, 120, PUR_F, PUR_L); label(b, "MODEL", P(26), PUR_D, bold=True)
text(s, 516, 200, 68, 60, "+", P(40), BODY, bold=True, align=PP_ALIGN.CENTER)
b = box(s, 580, 176, 280, 120, BLUE_F, BLUE_L); label(b, "HARNESS", P(26), BLUE_D, bold=True)
text(s, 856, 200, 68, 60, "=", P(40), BODY, bold=True, align=PP_ALIGN.CENTER)
b = box(s, 920, 176, 280, 120, INK); label(b, "AGENT", P(26), WHITE, bold=True)
text(s, 240, 312, 280, 60, "Judgement for one step. No memory, no actions, no self-check.", P(14), BODY)
text(s, 580, 312, 280, 60, "Loop, tools, state, verification. Ordinary code that you write.", P(14), BODY)
text(s, 920, 312, 280, 60, "A system that carries a task to a result and knows when to stop.", P(14), BODY)
eyebrow(s, 64, 402, "WHAT IS INSIDE A HARNESS")
for i, (t, bd) in enumerate([
        ("Loop", "Call the model again, or stop. And when to stop by force."),
        ("Tools", "What the model is allowed to ask for. It never acts, it asks."),
        ("State", "What the model sees this turn, and what to drop so context stops growing."),
        ("Verification", "Code inspects the result before accepting it.")]):
    card(s, 64 + i * 336, 436, 304, 230, t, bd)
text(s, 64, 700, 1312, 24, "The fourth job is usually missing entirely. The first one is usually underestimated.", P(15), BODY)

# 4 -- C. How a tool call works
s = d.page("C", "How a tool call works", "The model executes nothing. It asks; your code acts.")
steps = [
    ("You send the messages and the tool definitions",
     "A name, a description, a JSON schema. That is all the model knows about your code.", BLUE_F, BLUE_L, BLUE_D),
    ("The model replies with stop_reason = tool_use",
     "A block saying: call read_timetable with city Tashkent. That is a request, not an action.", PUR_F, PUR_L, PUR_D),
    ("Your code runs read_timetable(city)",
     "The model is idle. This is where the security boundary and the spending control live.", BLUE_F, BLUE_L, BLUE_D),
    ("You append the result as tool_result and send everything back",
     "The model does not remember the previous turn. You carry the state between calls.", BLUE_F, BLUE_L, BLUE_D),
    ("You repeat until end_turn arrives",
     "The cap on the number of rounds is set by code. The model does not stop on its own.", BLUE_F, BLUE_L, BLUE_D),
]
for i, (t, bd, f, l, c) in enumerate(steps):
    y = 176 + i * 110
    box(s, 64, y, 1312, 100, f, l)
    n = s.shapes.add_shape(MSO_SHAPE.OVAL, X(86), Y(y + 28), D(44), D(44))
    paint(n, l, None); label(n, str(i + 1), P(20), c, bold=True)
    text(s, 156, y + 18, 900, 28, t, P(18), INK, bold=True)
    text(s, 156, y + 52, 1100, 36, bd, P(14), BODY)
b = box(s, 64, 736, 1312, 56, GREY_F)
label(b, "while stop_reason == tool_use", P(20), INK, font=MONO)

# 5 -- D. stop_reason
s = d.page("D", "stop_reason",
           "A field in the API response: why the model stopped generating. It arrives as a string on the wire; the SDK does not invent it.")
eyebrow(s, 64, 172, "SEVEN VALUES · anthropic 0.125.0")
text(s, 1040, 172, 336, 20, "typing.get_args(anthropic.types.StopReason)", P(13), BODY,
     font=MONO, align=PP_ALIGN.RIGHT)
rows = [
    ("end_turn", "the model finished on its own, the normal exit", False),
    ("tool_use", "it wants a tool: run it and return a tool_result", False),
    ("stop_sequence", "your own stop_sequences fired", False),
    ("max_tokens", "it hit your limit; the answer is cut mid-sentence", True),
    ("pause_turn", "the server loop asks to continue; do not add \"Continue\"", True),
    ("refusal", "a safety refusal; only here is stop_details populated", True),
    ("model_context_window_exceeded", "the conversation no longer fits", True),
]
for i, (name, desc, trap) in enumerate(rows):
    y = 202 + i * 48
    box(s, 64, y, 1312, 44, RED_F if trap else GREY_F)
    text(s, 96, y + 12, 330, 24, name, P(15), INK, font=MONO)
    text(s, 440, y + 12, 700, 24, desc, P(14), BODY)
    if trap:
        chip(s, 1180, y + 9, 164, "SILENT TRAP", RED_L, RED_D)
eyebrow(s, 64, 562, "DOES IT DEPEND ON THE SDK")
card(s, 64, 592, 416, 184, "The API decides the values",
     "The server sends a string in the JSON. The SDK neither picks it, checks it, nor limits it.", tsize=19)
card(s, 512, 592, 416, 184, "The SDK holds a snapshot",
     "The Literal type was frozen when that version shipped. Seven today; a newer version may list more.", tsize=19)
card(s, 960, 592, 416, 184, "So you need an else",
     "A new value arrives as a string the type has never heard of. An exhaustive if without an else falls through in silence.",
     fill=RED_F, line=RED_L, tsize=19)

# 6 -- F. Token economics
s = d.page("F", "Token economics", "Prices on the left, numbers from a real run on the right. Nothing here is invented.")
eyebrow(s, 64, 172, "PRICE PER 1M TOKENS")
box(s, 64, 202, 640, 44, BLUE_F)
for lbl, x in (("MODEL", 96), ("IN", 420), ("OUT", 560)):
    text(s, x, 216, 200, 20, lbl, P(13), BLUE_D, bold=True)
for i, (m, a, b_) in enumerate([("Claude Opus 5", "$5", "$25"),
                                ("Claude Sonnet 5", "$2", "$10"),
                                ("Claude Haiku 4.5", "$1", "$5")]):
    y = 250 + i * 48
    box(s, 64, y, 640, 44, GREY_F)
    text(s, 96, y + 12, 300, 24, m, P(16), INK)
    text(s, 420, y + 12, 100, 24, a, P(16), BODY)
    text(s, 560, y + 12, 100, 24, b_, P(16), BODY)
eyebrow(s, 736, 172, "ONE HARNESS RUN, THREE ROUNDS")
for i, (k, v) in enumerate([("Input tokens, total", "425 + 593 + 1247 = 2265"),
                            ("Output tokens, total", "72 + 601 + 321 = 994"),
                            ("Of which hidden reasoning", "346"),
                            ("Cost of the whole run", "$0.036")]):
    y = 202 + i * 48
    box(s, 736, y, 640, 44, BLUE_F if i == 3 else GREY_F)
    text(s, 768, y + 12, 330, 24, k, P(16), INK, bold=(i == 3))
    text(s, 1090, y + 12, 270, 24, v, P(16), BLUE_D if i == 3 else INK,
         font=MONO, bold=(i == 3))
eyebrow(s, 64, 420, "THREE LEVERS A DEVELOPER OWNS")
card(s, 64, 450, 416, 190, "A model per sub-task",
     "Parsing a table does not need the most expensive model. A harness can pick one per tool; full delegation cannot.", tsize=19)
card(s, 512, 450, 416, 190, "Prompt caching",
     "The instruction block is identical on every call, so cache it: measured, that was 27 percent off a run.", tsize=19)
card(s, 960, 450, 416, 190, "Batch processing",
     "Timetables arrive seasonally and are not needed in a second. Asynchronous batches cost half.", tsize=19)
strip(s, 64, 676, 1312,
      "Output costs five times input. And the conversation grows on its own: 425 input tokens on the first round, 1247 on the third, same question.")

# 7 -- G. Prompt caching
s = d.page("G", "Prompt caching",
           "The model is not charged to read the part that never changes. Draw a line through the prompt, and everything above it gets cheap.")
eyebrow(s, 64, 164, "THE PROMPT, IN THE ORDER THE MODEL READS IT")
stack = [("tools and their schemas, 380 tokens", BLUE_F, BLUE_D, FONT),
         ("the instruction block, 604 tokens", BLUE_F, BLUE_D, FONT),
         ("cache_control, the breakpoint", BLUE_M, INK, MONO),
         ("the question, about 30 tokens", GREY_F, BODY, FONT),
         ("the conversation, longer every round", GREY_F, BODY, FONT)]
for i, (t, f, c, fnt) in enumerate(stack):
    b = box(s, 64, 202 + i * 48, 640, 44, f)
    label(b, t, P(15), c, bold=(i == 2), font=fnt)
eyebrow(s, 736, 164, "WHAT EACH HALF COSTS")
text(s, 736, 204, 600, 28, "Above the line: 984 tokens", P(19), BLUE_D, bold=True)
text(s, 736, 238, 620, 50, "Byte for byte the same on every call. Written once at 1.25x, then read at 0.10x for as long as it lives.", P(15), BODY)
text(s, 736, 348, 600, 28, "Below it: everything that changes", P(19), BODY, bold=True)
text(s, 736, 382, 620, 50, "The question and the conversation so far. Billed at 1.00x, in full, on every single call.", P(15), BODY)
text(s, 64, 476, 1312, 24, "Two calls that begin the same way already pay for it: 1.25 plus 0.10 is less than 1.00 twice. Measured: 27 percent off the run.", P(16), BODY)
text(s, 64, 516, 1312, 24, "The ceiling: a cache touches input only, and 56 percent of that same bill was the model writing.", P(16), BODY)
strip(s, 64, 676, 1312,
      "Anything that changes near the top, a date or a user id, and the cache never hits. No error, no warning, just zeros in usage and a bill 25 percent higher.")

# 8 -- The whole conversation (left: what it means, right: how it sits in JSON)
s = d.page("H", "The whole conversation",
           "On the left what it means, on the right how it sits in JSON. It accumulates in your memory, not on the server.")
eyebrow(s, 64, 150, "SIX MESSAGES · THREE ROUNDS OVER THE WIRE")
eyebrow(s, 736, 150, "HOW IT SITS IN JSON")

rows = [
    (170, 130, "user", ["a string"], "SENT IN ROUND 1", BLUE_F, BLUE_L, BLUE_D,
     "List the times of the last trip of route 5A in Tashkent, stop by stop.",
     "messages[0]",
     '{\n  "role": "user",\n  "content": "List the times of the last\n              trip of route 5A in Tashkent…"\n}'),
    (310, 150, "assistant", ["text", "tool_use"], "ARRIVED IN ROUND 1", PUR_F, PUR_L, PUR_D,
     "Out loud, plus the request: read_timetable with city Tashkent.",
     "messages[1]",
     '{\n  "role": "assistant",\n  "content": [\n    {"type": "thinking", "thinking": "", "signature": "CAISuAUK…"},\n    {"type": "text", "text": "I\'ll pull the raw timetable…"},\n    {"type": "tool_use", "id": "toolu_019V6E…",\n     "name": "read_timetable", "input": {"city": "Tashkent"}}\n  ]\n}'),
    (470, 130, "user", ["tool_result"], "SENT IN ROUND 2", BLUE_F, BLUE_L, BLUE_D,
     "The raw table, exactly as the function returned it. The role is still user.",
     "messages[2]",
     '{\n  "role": "user",\n  "content": [\n    {"type": "tool_result",\n     "tool_use_id": "toolu_019V6E…",\n     "content": "Route 5A -- weekdays\\nstop  trip 1…"}\n  ]\n}'),
    (636, 130, "assistant", ["thinking", "text"], "ARRIVED IN ROUND 3", PUR_F, PUR_L, PUR_D,
     "23:40, 23:47, 24:05. Accepted. Nothing in the prompt mentioned midnight.",
     "messages[5]",
     '{\n  "role": "assistant",\n  "content": [\n    {"type": "thinking", "thinking": "", "signature": "CAISwgYK…"},\n    {"type": "text", "text": "…the final stop becomes 24:05."}\n  ]\n}'),
]

for y, h, role, chips, rnd, f, l, c, meaning, title, code in rows:
    box(s, 64, y, 636, h, f, l)
    text(s, 92, y + 14, 150, 26, role, P(17), c, bold=True, font=MONO)
    for j, ch in enumerate(chips):
        chip(s, 236 + j * 118, y + 12, 110, ch, l, c)
    text(s, 470, y + 16, 206, 18, rnd, P(12), BODY, bold=True, align=PP_ALIGN.RIGHT)
    text(s, 92, y + 52, 580, h - 60, meaning, P(14), BODY)

    box(s, 736, y, 640, h, GREY_F)
    text(s, 760, y + 10, 600, 16, title, P(11), BODY, bold=True, font=MONO)
    text(s, 760, y + 30, 600, h - 40, code, P(11), INK, font=MONO, spacing=1.0)

text(s, 64, 606, 636, 20, ". . . . . . . . . . .", P(14), BODY, bold=True,
     align=PP_ALIGN.CENTER)
text(s, 736, 606, 640, 20, "messages[3] and messages[4]: the wrong answer, and the code saying no",
     P(12), BODY, align=PP_ALIGN.CENTER)

# 9 -- I. Decisions over time
s = d.page("I", "Decisions over time", "The scale is a route, not a one-off choice. And it has three poles, not two.")
eyebrow(s, 64, 172, "DECISIONS MOVE, USUALLY FROM MODEL TOWARDS CODE")
poles = [("You know no rules", "MODEL", PUR_L, PUR_D,
          "Hand the whole thing to the model. Expensive and unpredictable, but it works today and needs no understanding."),
         ("You see a pattern", "IN TRANSIT", GREY_L, INK,
          "Twenty examples in, a rule shows through. The model still works, but you are writing the rule down."),
         ("The rule is in code", "CODE", BLUE_L, BLUE_D,
          "Cheap, instant, the same answer every time. The model is no longer needed on this step.")]
for i, (t, tag, tf_, tc, bd) in enumerate(poles):
    x = 64 + i * 448
    box(s, x, 202, 416, 180, GREY_F)
    text(s, x + 28, 222, 360, 28, t, P(19), INK, bold=True)
    chip(s, x + 28, 254, 130, tag, tf_, tc)
    text(s, x + 28, 292, 360, 80, bd, P(14), BODY)
text(s, 64, 410, 1312, 40, "It moves the other way too: when a parser has collected forty ifs for different formats and every new case needs a patch, the rule has stopped being a rule. Hand it back to the model.",
     P(15), BODY)
eyebrow(s, 64, 472, "THE THIRD POLE")
box(s, 64, 502, 640, 170, GREY_F)
text(s, 92, 524, 580, 28, "A human at runtime", P(19), INK, bold=True)
text(s, 92, 560, 584, 100, "Not \"a human wrote the code\", but a human pressing confirm while the thing runs. Publishing, deleting, sending outside. Deliberately not automated, and that is architecture, not an omission.",
     P(14), BODY)
eyebrow(s, 736, 472, "THE TRAP", w=200)
box(s, 736, 502, 640, 170, RED_F, RED_L)
text(s, 764, 524, 580, 28, "The decision lives nowhere", P(19), INK, bold=True)
text(s, 764, 560, 584, 100, "The model was told \"sort it out\", there is no check in code, the result flows on. Ask who is accountable for correctness. The model has no idea what correct means in your domain.",
     P(14), BODY)
strip(s, 64, 700, 1312,
      "Run example_harness.py and read the log: the model made 3 decisions, the code made 4, and the code was the one that decided to retry.",
      fill=BLUE_F, line=BLUE_M, color=BLUE_D, size=16, h=70)

# 10 -- J. RAG
s = d.page("J", "RAG: search as a tool", "Not a separate architecture. Replace read_timetable with search and you have RAG.")
eyebrow(s, 64, 158, "THREE STEPS")
for i, (t, bd) in enumerate([("Indexing", "Up front: cut documents into chunks."),
                             ("Search", "At runtime: pull a couple of chunks for the question."),
                             ("Answer", "Chunks plus the question go to the model.")]):
    card(s, 64 + i * 448, 196, 416, 130, t, bd, fill=GREY_F, line=None)
eyebrow(s, 64, 350, "TWO SHAPES")
card(s, 64, 380, 640, 120, "Classic", "Code searches once and puts it in the prompt. Miss, and that is that.")
card(s, 736, 380, 640, 120, "Agentic", "Search is a tool. The model searches itself and rephrases.",
     fill=PUR_F, line=PUR_L)
eyebrow(s, 64, 524, "THE CHECK, FIVE LINES")
box(s, 64, 552, 640, 150, GREY_F)
text(s, 92, 572, 600, 120,
     "def check(result, found):\n    if result[\"answer\"] is None:\n        return None\n    if result[\"source\"] not in found:\n        return \"never retrieved\"",
     P(14), INK, font=MONO, spacing=1.0)
eyebrow(s, 736, 524, "ON A REAL RUN, TWICE IN A ROW")
text(s, 736, 556, 640, 150, "Question one: the model searched twice, although the first search already held the answer. Question two: four phrasings, then an honest refusal.\n\nHow many searches happen is the model's decision, not yours, and every one is on the bill.",
     P(15), BODY)
strip(s, 64, 706, 1312,
      "An honest \"not in the sources\" is not the default. It happened only because the output shape allowed null and the code refused any citation that was not retrieved.",
      size=15, h=80)

# 11 -- K. Workshop
s = d.page("K", "Workshop: pick a task, build the harness",
           "Bring a task from your own week. The three seeded rows have checks of three different kinds: something must exist, numbers must match, code must run.")
eyebrow(s, 64, 164, "FOR EVERY IDEA, DECIDE FOUR THINGS")
cols = [(92, 330, "THE TASK"), (448, 280, "THE TOOLS"),
        (772, 400, "WHAT THE CODE CHECKS"), (1216, 160, "WHEN IT STOPS")]
for x, w, t in cols:
    text(s, x, 196, w, 20, t, P(13), BLUE_D, bold=True)
seeds = [
    ("An incoming ticket gets a queue, a priority and a component.",
     "search_similar_tickets, read_component_registry",
     "The component must exist in the registry. The priority must be one of the allowed values.",
     "One retry, then a human gets it."),
    ("A weekly digest of one queue for the team channel.",
     "search_tickets, read_ticket",
     "Every number must equal the count code computed. Every claim must cite a ticket key that was retrieved.",
     "The week is covered."),
    ("Turn a bug report into a test that proves the bug.",
     "read_bug_report, run_tests",
     "The test must fail on the broken commit and pass on the fix. Code runs it.",
     "Red, then green."),
]
for i, row in enumerate(seeds):
    y = 228 + i * 116
    box(s, 64, y, 1312, 104, BLUE_F, BLUE_L)
    for (x, w, _), cell in zip(cols, row):
        text(s, x, y + 22, w, 80, cell, P(14), BODY)
for i in range(2):
    box(s, 64, 570 + i * 64, 1312, 58, GREY_F)
strip(s, 64, 700, 1312,
      "If you cannot name what the code checks, it is not a harness yet. It is a prompt with extra steps.",
      size=16, h=80)

# 12 -- closing
d.nofooter.add(12)
s = d.page()
box(s, 0, 0, 1440, 840, INK)
text(s, 110, 300, 1100, 120, "WHAT DOES YOUR\nCODE CHECK?", Pt(48), WHITE, bold=True, spacing=0.9)
text(s, 110, 640, 600, 30, "Kamila Malikova", P(22), WHITE, bold=True)
text(s, 110, 684, 600, 24, "Должность", P(16), RGBColor(0xC6, 0xDC, 0xFF))
text(s, 1000, 684, 376, 24, EVENT, P(16), RGBColor(0xC6, 0xDC, 0xFF), align=PP_ALIGN.RIGHT)

d.save("Build_the_Harness_plain.pptx")
