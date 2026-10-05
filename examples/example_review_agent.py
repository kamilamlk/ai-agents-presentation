"""
The other half of example_review.py: now with a model.

    source ./anthropic-env.sh on
    python3 example_review_agent.py
    python3 example_review_agent.py ../some/service

example_review.py stops where a set difference stops. It hands over two to four
mentions that name something the code does not have, and the question it cannot
answer: is this comment stale, or does it legitimately name something that lives
outside this repository? That one is judgement, so it goes to the model.

The four jobs of a harness are marked in this file, and every one of them is
also visible in the log:

    TOOLS         read_context and find_name. The model asks; this file acts.
    THE LOOP      one retry on a rejected verdict, then a human gets it; and a
                  hard cap on calls, so asking for files cannot run forever.
    STATE         one conversation per mention, dropped before the next.
    VERIFICATION  the model's answer goes through the same check() that found
                  the mention -- a replacement comment is not allowed to name
                  yet another thing the code does not have.

Cost: the model never sees the repository, only the handful of candidates that
code could not resolve. Two to four calls of a few thousand tokens each; cents.

The loop lives in judge(client, ...) so it can be tested with a fake client.
See test_review_agent.py.
"""

import json
import re
import sys
from pathlib import Path

import anthropic

from example_review import check, mentioned, review, sources, vocabulary

MODEL = "claude-sonnet-5"   # a lever: judging one comment is not Opus work
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

Read the comment in place before deciding. End your answer with a ```json block:

    {"verdict": "stale", "replacement": "the comment as it should read"}

replacement is the full new comment text, and only for a stale verdict; leave it
empty otherwise."""


# -- TOOLS -------------------------------------------------------------------
# What the model is allowed to ask for. It never reads a file itself: it asks,
# and the code below opens it. That is where a path check would live.

TOOLS = [
    {
        "name": "read_context",
        "description": "The lines of a file around a line number.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "line": {"type": "integer"}},
            "required": ["path", "line"],
        },
    },
    {
        "name": "find_name",
        "description": "Where a word appears in the code. Empty means nowhere.",
        "input_schema": {
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
        },
    },
]


def read_context(path, line, radius=6):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return f"no such file: {path}"
    lo, hi = max(0, line - radius - 1), min(len(lines), line + radius)
    return "\n".join(f"{i + 1:4}  {lines[i]}" for i in range(lo, hi))


def find_name(word, root="."):
    hits = [f"{p}:{i}  {text.strip()[:70]}"
            for p in sources(root)
            for i, text in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if word in text]
    return "\n".join(hits[:5]) or f"{word} appears nowhere in the code"


def call_tool(name, kwargs, root):
    if name == "read_context":
        return read_context(**kwargs)
    if name == "find_name":
        return find_name(root=root, **kwargs)
    return f"no such tool: {name}"


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

def judge(client, candidate, vocab, root=".", log=print):
    path, line, word, snippet = candidate
    log(f"\nMENTION   {path}:{line}  names {word!r}")
    log(f"          {snippet}")

    # STATE: a fresh conversation for this mention, and nothing from the last
    # one. Each is judged on its own, so the context never grows across the run
    # -- and the constant half, system and tools, is identical every time.
    messages = [{"role": "user", "content":
                 f"The comment at {path}:{line} names {word!r}.\n{snippet}\nJudge it."}]
    log(f"state     1 message; the previous mention was dropped")

    rejected = 0
    for round_ in range(1, ROUNDS + 1):
        r = client.messages.create(
            model=MODEL, max_tokens=1024,
            system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason not in ("tool_use", "end_turn"):
            raise RuntimeError(f"unexpected stop_reason: {r.stop_reason}")

        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    log(f"model     asks for {b.name}({b.input})")
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": call_tool(b.name, b.input, root)})
            messages.append({"role": "user", "content": results})
            log(f"state     {len(messages)} messages carried into round {round_ + 1}")
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        block = re.search(r"```json\s*(.*?)\s*```", text, re.S)
        answer = json.loads(block.group(1)) if block else {}
        log(f"model     says {answer.get('verdict')!r}")

        problem = verify(answer, word, vocab)
        if not problem:
            log(f"code      accepted")
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

def run(client, root=".", log=print):
    findings = review(root, log=lambda *a, **kw: None)
    vocab = vocabulary(sources(root))
    log(f"\nCODE      narrowed {root} down to {len(findings)} mention(s) without a model")

    results = [(c, judge(client, c, vocab, root, log)) for c in findings]

    log("")
    for (path, line, word, _), answer in results:
        verdict = answer["verdict"] if answer else "needs a human"
        log(f"RESULT    {path}:{line}  {word}  ->  {verdict}")
    log(f"\n          {sum(1 for _, a in results if a is None)} of {len(results)} "
        f"went to a human. Everything else, code checked.")
    return results


if __name__ == "__main__":
    run(anthropic.Anthropic(), sys.argv[1] if len(sys.argv) > 1 else ".")
