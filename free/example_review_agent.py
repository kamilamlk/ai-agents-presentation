"""
The stale-comment reviewer on a free model.

    export GROQ_API_KEY=gsk_...
    python3 free/example_review_agent.py fixtures/orders_service

The code half is not ported, it is imported: check(), mentioned() and review()
come straight out of examples/example_review.py. A set difference does not have
a provider. That is half the point of this file -- the cheap half of the task is
the half that never changes.

The four jobs are marked here as they are in the paid version, and the log says
which one is speaking:

    TOOLS         read_context and find_name. The model asks; this file acts.
    THE LOOP      one retry on a rejected verdict, then a human gets it; and a
                  hard cap on calls, so asking for files cannot run forever.
    STATE         one conversation per mention, dropped before the next.
    VERIFICATION  the model's answer goes through the same check() that found
                  the mention.

Expect the free model to be refused more often than the paid one, and that is
the demo: the retry and the handover to a human stop being a slide and start
being a line in the log. Measured numbers for the paid run are in
fixtures/orders_service/README.md -- yours will differ, so print both.

The loop lives in judge(call, ...) so it can be tested with a fake.
See test_free.py.
"""

import json
import re
import sys
from pathlib import Path

from wire import arguments, create, spent, text

# The code half lives next door and is used as it is.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
from example_review import check, mentioned, review, sources, vocabulary  # noqa: E402

RETRIES = 1                 # rejected verdicts before a human gets it
ROUNDS = 8                  # hard cap on calls, so asking for files cannot loop
VERDICTS = ("stale", "foreign", "fine")

SYSTEM = """You judge one comment at a time.

Code has already established that the comment names something the code does not
have. You decide which of three it is:

    stale    the comment describes code that no longer exists; it must be rewritten
    foreign  the name is real but lives outside this repository (an API field, a
             CLI flag, another service); the comment is correct as written
    fine     the mention is not about code at all

Read the comment in place with read_context before deciding. End your answer
with a ```json block:

    {"verdict": "stale", "replacement": "the comment as it should read"}

replacement is the full new comment text, and only for a stale verdict; leave it
empty otherwise."""


# -- TOOLS -------------------------------------------------------------------
# What the model is allowed to ask for. It never reads a file itself: it asks,
# and the code below opens it. That is where a path check would live.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_context",
            "description": "The lines of a file around a line number.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "line": {"type": "integer"}},
                "required": ["path", "line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_name",
            "description": "Where a word appears in the code. Empty means nowhere.",
            "parameters": {
                "type": "object",
                "properties": {"word": {"type": "string"}},
                "required": ["word"],
            },
        },
    },
]


def read_context(path, line, radius=6):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return f"no such file: {path}"
    line = int(line)        # a free model sometimes sends the number as a string
    lo, hi = max(0, line - radius - 1), min(len(lines), line + radius)
    return "\n".join(f"{i + 1:4}  {lines[i]}" for i in range(lo, hi))


def find_name(word, root="."):
    hits = [f"{p}:{i}  {text_.strip()[:70]}"
            for p in sources(root)
            for i, text_ in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if word in text_]
    return "\n".join(hits[:5]) or f"{word} appears nowhere in the code"


def call_tool(name, kwargs, root):
    """A bad call is not a crash. The error goes back as the tool result and the
    model gets another turn -- which it needs more often on a smaller model."""
    try:
        if name == "read_context":
            return read_context(**kwargs)
        if name == "find_name":
            return find_name(root=root, **kwargs)
        return f"no such tool: {name}"
    except TypeError as error:
        return f"wrong arguments for {name}: {error}"


# -- VERIFICATION ------------------------------------------------------------
# The model answered. Now code inspects the answer before anything is accepted,
# and it inspects it with the same rule that produced the candidate.

def verify(answer, word, vocab):
    """Returns the reason to reject, or None to accept."""
    verdict = answer.get("verdict")
    if verdict not in VERDICTS:
        return f"verdict must be one of {', '.join(VERDICTS)}, not {verdict!r}"

    replacement = (answer.get("replacement") or "").strip()
    if verdict != "stale":
        if replacement:
            return f"a {verdict} verdict leaves the comment alone, so replacement must be empty"
        return None

    if not replacement:
        return "a stale verdict needs the replacement comment"
    if word in replacement:
        return f"the replacement still names {word}, which is the thing the code does not have"
    unknown = [w for w in mentioned(replacement) if check(w, vocab) is None]
    if unknown:
        return (f"the replacement names {unknown[0]}, which the code does not have either: "
                f"name something that exists, or describe it in prose")
    return None


# -- THE LOOP ----------------------------------------------------------------
# Call the model again, or stop, or give up. The model never decides this.

def judge(call, candidate, vocab, root=".", log=print):
    path, line, word, snippet = candidate
    log(f"\nMENTION   {path}:{line}  names {word!r}")
    log(f"          {snippet}")

    # STATE: a fresh conversation for this mention, and nothing from the last
    # one. Each is judged on its own, so the context never grows across the run.
    messages = [{"role": "user", "content":
                 f"The comment at {path}:{line} names {word!r}.\n{snippet}\nJudge it."}]
    log("state     1 message; the previous mention was dropped")

    rejected = 0
    for round_ in range(1, ROUNDS + 1):
        # temperature=0: this is a verdict on one comment, not a draft. The one
        # place in the four examples where the lever is worth pulling.
        message, finish_reason = call(messages, tools=TOOLS, system=SYSTEM,
                                      temperature=0)
        messages.append(message)

        if finish_reason == "tool_calls":
            for tool_call in message["tool_calls"]:
                name = tool_call["function"]["name"]
                try:
                    kwargs = arguments(tool_call)
                    result = call_tool(name, kwargs, root)
                except ValueError as error:
                    kwargs, result = tool_call["function"]["arguments"], str(error)
                log(f"model     asks for {name}({kwargs})")
                messages.append({"role": "tool", "tool_call_id": tool_call["id"],
                                 "content": result})
            log(f"state     {len(messages)} messages carried into round {round_ + 1}")
            continue

        block = re.search(r"```json\s*(.*?)\s*```", text(message), re.S)
        try:
            answer = json.loads(block.group(1)) if block else {}
        except json.JSONDecodeError:
            answer = {}
        log(f"model     says {answer.get('verdict')!r}")

        problem = verify(answer, word, vocab)
        if not problem:
            log("code      accepted")
            if answer["verdict"] == "stale":
                log(f"          rewrite: {answer['replacement']}")
            return answer

        log(f"code      rejected: {problem}")
        rejected += 1
        if rejected > RETRIES:
            break
        messages.append({"role": "user",
                         "content": f"Not good: {problem}. Return the JSON again."})

    log(f"loop      {rejected} verdict(s) refused in {round_} call(s) — a human gets it")
    return None


# -- The run -----------------------------------------------------------------

def run(call=create, root=".", log=print):
    findings = review(root, log=lambda *a, **kw: None)
    vocab = vocabulary(sources(root))
    log(f"\nCODE      narrowed {root} down to {len(findings)} mention(s) without a model")

    results = [(c, judge(call, c, vocab, root, log)) for c in findings]

    log("")
    for (path, line, word, _), answer in results:
        verdict = answer["verdict"] if answer else "needs a human"
        log(f"RESULT    {path}:{line}  {word}  ->  {verdict}")
    log(f"\n          {sum(1 for _, a in results if a is None)} of {len(results)} "
        f"went to a human. Everything else, code checked.")
    log(f"          {spent()}")
    return results


if __name__ == "__main__":
    run(root=sys.argv[1] if len(sys.argv) > 1 else ".")
