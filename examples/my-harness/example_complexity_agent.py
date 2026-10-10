"""
The other half of example_complexity.py: now with a model, and the last check is
a subprocess.

    source ../../anthropic-env.sh on
    python3 example_complexity_agent.py fixtures/billing

example_complexity.py stops at a number: this function has thirty statements and
the limit is twelve. Which split is the right one is judgement, so it goes to
the model.

What makes this example different from the other two harnesses here: in those,
code reads the model's answer. Here code runs it. A refactor can parse, keep the
name and the signature, be shorter than the limit, read better than the original
and satisfy every sentence in the system prompt -- and still return something
else on one input out of eight. Nothing short of executing it finds that out.

The four jobs, marked in this file and visible in the log:

    TOOLS         measure_code. The model can count its own draft. It cannot run
                  it: the golden cases are not reachable from in there, on
                  purpose. A model does not get to write its own exam.
    THE LOOP      two refused refactors and a human gets it; and a hard cap on
                  calls, so asking to be measured cannot run forever.
    STATE         one conversation per function, dropped before the next.
    VERIFICATION  five checks, cheapest first. Four of them never start a
                  process. The fifth runs the function on inputs that came with
                  the fixture and compares what came back -- the return value,
                  the exception, and the arguments after the call.

Nothing is written to disk. An accepted refactor is printed.

Cost: the model sees one file and one function name, twice if it is refused. A
meter sits at the one seam every call goes through, so the last table in the log
says what the run cost -- and how much of it bought nothing.

The loop lives in refactor(client, ...) so it can be tested with a fake client.
See test_complexity_agent.py.
"""

import ast
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic

from example_complexity import FUNC, MAX_LINES, length, measure, scan

MODEL = "claude-sonnet-5"   # a lever: splitting one function is not Opus work
RETRIES = 2                 # refused refactors before a human gets it
ROUNDS = 6                  # hard cap on calls, so being measured cannot loop
RUN_TIMEOUT = 10            # seconds the golden cases get before it is a failure

PRICE_IN = 2.00             # dollars per 1,000,000 tokens, at MODEL's rate above
PRICE_OUT = 10.00           # writing costs five times reading, per token
CACHE_WRITE_MULT = 1.25     # a cache write costs more than plain input
CACHE_READ_MULT = 0.10      # a cache read costs far less

# Two constants, and they belong to MODEL: priced at Opus rates this run reads as
# two and a half times dearer than it was. Check them before you present.

SYSTEM = f"""You split one function that is too long.

A function may have at most {MAX_LINES} statements. A statement counts as one
wherever it is nested, a docstring does not count, and a nested function counts
as one statement and is then measured on its own.

You get the whole file and the name of one function in it. Return that function
rewritten, plus any helpers it needs, all at module level, in one ```python
block and nothing else in that block. Everything else in the file stays as it
is, so do not repeat it.

Keep the behaviour identical. Keep the name and the signature. Add no imports.

measure_code gives you the count this harness uses. Use it before you answer."""


# -- TOOLS -------------------------------------------------------------------
# What the model is allowed to ask for: the measure, applied to its own draft.
# Not the golden cases. Those are the exam, and this file invigilates it.

TOOLS = [
    {
        "name": "measure_code",
        "description": "Statements per function in a draft, by the same count the limit uses.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    }
]


def measure_code(code):
    found = measure(code)
    if found is None:
        return "that draft does not parse"
    if not found:
        return "there are no functions in that draft"
    return "\n".join(
        f"{name} has {size} statements" + (" -- over the limit" if size > MAX_LINES else "")
        for name, _, size in found)


def call_tool(name, kwargs):
    if name == "measure_code":
        return measure_code(**kwargs)
    return f"no such tool: {name}"


# -- VERIFICATION, part one: four checks that never start a process ----------

def find(source, name):
    """One function node by name, or None."""
    return next((n for n in ast.walk(ast.parse(source))
                 if isinstance(n, FUNC) and n.name == name), None)


def signature(node):
    return ast.unparse(node.args)


def imports(tree):
    return {ast.unparse(n) for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))}


def splice(source, target, proposal):
    """The file with the target function replaced by the proposal. Running needs
    a whole module; the model answered with a fragment."""
    node = find(source, target)
    lines = source.splitlines()
    first = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    return "\n".join(lines[:first] + proposal.strip().splitlines()
                     + lines[node.end_lineno:]) + "\n"


# -- VERIFICATION, part two: the one that runs the code ----------------------
# A fresh interpreter, the golden cases loaded from the fixture, a timeout. The
# original goes through this same driver, so both sides are measured the same
# way and a difference is a difference in the code, not in how it was observed.

DRIVER = Path(__file__).parent / "driver.py"


def behaviour(source, target, cases_path):
    """Run the target on every golden case, out of process. Returns the records
    and None, or None and the reason there are none."""
    with tempfile.TemporaryDirectory() as tmp:
        subject = Path(tmp) / "subject.py"
        subject.write_text(source, encoding="utf-8")
        try:
            done = subprocess.run(
                [sys.executable, str(DRIVER), str(subject), str(cases_path), target],
                capture_output=True, text=True, timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return None, f"it did not finish the golden cases in {RUN_TIMEOUT}s"
    if done.returncode != 0:
        last = (done.stderr.strip().splitlines() or ["no output"])[-1]
        return None, f"it did not run at all: {last}"
    return json.loads(done.stdout), None


def compare(before, after, cases):
    """The golden cases, one by one. The first difference is the reason, and it
    names the input, so the model can see what it broke."""
    for case, was, now in zip(cases, before, after):
        if was == now:
            continue
        where = repr(case)[:120]
        if was.get("value") != now.get("value"):
            return (f"on {where} it returned {now.get('value')}, "
                    f"and before the split it returned {was.get('value')}")
        if was.get("error") != now.get("error"):
            return (f"on {where} it raised {now.get('error') or 'nothing'}, "
                    f"and before the split it raised {was.get('error') or 'nothing'}")
        return (f"on {where} the argument came back as {now['args_after']}, "
                f"and before the split it came back as {was['args_after']}")
    return None


def verify(proposal, target, source, cases_path, baseline, cases):
    """Returns the reason to reject, or None to accept."""
    try:
        drafted = ast.parse(proposal)
    except (SyntaxError, ValueError) as e:
        return f"it does not parse: {e}"

    functions = [n for n in ast.walk(drafted) if isinstance(n, FUNC)]
    rewritten = next((n for n in functions if n.name == target), None)
    if rewritten is None:
        return (f"{target} is not in the answer, and the rest of the file calls it "
                f"by that name")

    original = find(source, target)
    if signature(rewritten) != signature(original):
        return (f"the signature changed: callers pass {target}({signature(original)}), "
                f"not {target}({signature(rewritten)})")

    added = imports(drafted) - imports(ast.parse(source))
    if added:
        return f"it adds an import the file does not have: {sorted(added)[0]}"

    # The rule from example_complexity.py, turned on the model's own answer: the
    # thing that made this a candidate is not allowed back in the fix.
    over = [(n.name, length(n)) for n in functions if length(n) > MAX_LINES]
    if over:
        return (f"{over[0][0]} has {over[0][1]} statements, "
                f"so it is over the limit of {MAX_LINES} as well")

    after, failed = behaviour(splice(source, target, proposal), target, cases_path)
    return failed or compare(baseline, after, cases)


# -- WHAT IT COST ------------------------------------------------------------
# Arithmetic, like the measure itself. It goes at the client seam -- the same
# one the tests use to slip in a fake -- so the loop below does no bookkeeping
# and nothing has to be threaded through it.

def prompt_size(usage):
    """The whole prompt. input_tokens is only the part that missed the cache."""
    if usage is None:
        return 0                # a stub with no usage on it: the tests
    return (usage.input_tokens
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + (getattr(usage, "cache_read_input_tokens", 0) or 0))


def money(usage):
    """What one response cost, in dollars. Four rates, because a cache write and
    a cache read are not priced like the input that missed both."""
    if usage is None:
        return 0.0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (usage.input_tokens * PRICE_IN
            + written * PRICE_IN * CACHE_WRITE_MULT
            + read * PRICE_IN * CACHE_READ_MULT
            + usage.output_tokens * PRICE_OUT) / 1_000_000


REFUSED = "the code refused the round before"


def why(messages):
    """Why this round exists, and the last message says which: a rejection, a
    tool result, or neither -- in which case it is the first ask."""
    content = messages[-1].get("content")
    if isinstance(content, str) and content.startswith("Not good"):
        return REFUSED
    if isinstance(content, list) and any(b.get("type") == "tool_result" for b in content):
        return "the model asked to be measured"
    return ""


class Meter:
    """Stands where the client stands and remembers what each round cost."""

    def __init__(self, client):
        self.client = client
        self.rows = []
        self.label = ""        # the function being split, set by run()
        self.messages = self   # so meter.messages.create(...) works

    def create(self, **kw):
        response = self.client.messages.create(**kw)
        usage = getattr(response, "usage", None)
        self.rows.append({
            "function": self.label,
            "round": sum(1 for r in self.rows if r["function"] == self.label) + 1,
            "msgs": len(kw["messages"]),
            "in": prompt_size(usage),
            "out": getattr(usage, "output_tokens", 0),
            "cost": money(usage),
            "why": why(kw["messages"]),
        })
        return response


def report(rows, log):
    """The bottom line. Silent when there is nothing priced to report -- which is
    every test in test_complexity_agent.py, since a stub costs nothing."""
    if not any(r["cost"] for r in rows):
        return
    log(f"\n{'FUNCTION':<17}{'ROUND':>6}{'MSGS':>6}{'IN':>8}{'OUT':>7}{'COST':>11}  WHY")
    for r in rows:
        log(f"{r['function']:<17}{r['round']:>6}{r['msgs']:>6}{r['in']:>8}{r['out']:>7}"
            f"{'$%.4f' % r['cost']:>11}  {r['why']}")
    log(f"{'TOTAL':<17}{'':>6}{'':>6}{sum(r['in'] for r in rows):>8}"
        f"{sum(r['out'] for r in rows):>7}"
        f"{'$%.4f' % sum(r['cost'] for r in rows):>11}")

    # MSGS and IN climb while the question stays the same: the whole conversation
    # is resent every round, so a second round is never a second round's worth.
    refused = [r for r in rows if r["why"] == REFUSED]
    log(f"\n          {len(refused)} of {len(rows)} round(s) existed only because a "
        f"refactor was refused: ${sum(r['cost'] for r in refused):.4f}, and it bought "
        f"nothing."
        if refused else
        "\n          No refactor was refused this time, so nothing was paid for twice.")
    log("          The five checks cost nothing to run. Being wrong is what costs money.")


# -- THE LOOP ----------------------------------------------------------------
# Call the model again, or stop, or give up. The model never decides this.

def refactor(client, finding, source, cases_path, cases, baseline, log=print):
    path, line, target, size = finding
    log(f"\nFUNCTION  {path}:{line}  {target} has {size} statements, "
        f"limit is {MAX_LINES}")

    # STATE: a fresh conversation for this function, and nothing from the last
    # one. Each is split on its own, so the context never grows across the run
    # -- and the constant half, system and tools, is identical every time.
    messages = [{"role": "user", "content":
                 f"{path} reads:\n\n```python\n{source}```\n\n"
                 f"Split {target}. It has {size} statements."}]
    log("state     1 message; the previous function was dropped")

    rejected = 0
    for round_ in range(1, ROUNDS + 1):
        r = client.messages.create(
            model=MODEL, max_tokens=4096,
            system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason not in ("tool_use", "end_turn"):
            raise RuntimeError(f"unexpected stop_reason: {r.stop_reason}")

        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    draft = b.input.get("code", "")
                    log(f"model     asks for {b.name} on {len(draft.splitlines())} "
                        f"lines of draft")
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": call_tool(b.name, b.input)})
            messages.append({"role": "user", "content": results})
            log(f"state     {len(messages)} messages carried into round {round_ + 1}")
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        block = re.search(r"```python\s*(.*?)\s*```", text, re.S)
        proposal = block.group(1) if block else ""
        sizes = measure(proposal) or []
        log(f"model     proposes {', '.join(f'{n} at {s}' for n, _, s in sizes) or 'nothing'}")

        problem = verify(proposal, target, source, cases_path, baseline, cases)
        if not problem:
            log(f"code      accepted: {len(cases)} golden case(s) came back identical")
            return proposal

        log(f"code      rejected: {problem}")
        rejected += 1
        if rejected > RETRIES:
            break
        messages.append({"role": "user",
                         "content": f"Not good: {problem}. Return the block again."})

    log(f"loop      {rejected} refactor(s) refused in {round_} call(s) — a human gets it")
    return None


# -- The run -----------------------------------------------------------------

def run(client, root="fixtures/billing", log=print):
    root = Path(root)
    cases_path = root / "cases.py"
    if not cases_path.exists():
        raise SystemExit(f"no {cases_path}: with nothing to check a refactor against "
                         f"there is nothing to delegate")
    cases = load_cases(cases_path)
    meter = Meter(client)

    findings = scan(root, log=lambda *a, **kw: None)
    log(f"\nCODE      measured {root} and found {len(findings)} function(s) "
        f"over {MAX_LINES}, with no model")

    results = []
    for finding in findings:
        path, line, target, _ = finding
        meter.label = target
        source = path.read_text(encoding="utf-8")
        results.append((finding, delegate(meter, finding, source, cases, cases_path, log)))

    log("")
    for (path, line, target, _), proposal in results:
        split = measure(proposal) or [] if proposal else []
        log(f"RESULT    {path}:{line}  {target}  ->  "
            f"{f'{len(split)} functions, all within the limit' if proposal else 'needs a human'}")
    log(f"\n          {sum(1 for _, p in results if p is None)} of {len(results)} "
        f"went to a human. Everything else, code ran.")

    for (_, _, target, _), proposal in results:
        if proposal:
            log(f"\n-- {target}, accepted ------------------------------------------")
            log(proposal)
    log("\n          Printed, not written: the file on disk is untouched.")

    report(meter.rows, log)
    return results


def delegate(client, finding, source, cases, cases_path, log):
    """One function: establish what it does now, then ask for the split."""
    path, line, target, _ = finding
    if target not in cases:
        log(f"\nFUNCTION  {path}:{line}  {target} — skipped: no golden cases for it, "
            f"so a refactor could not be checked")
        return None

    baseline, failed = behaviour(source, target, cases_path)
    if failed:
        log(f"\nFUNCTION  {path}:{line}  {target} — skipped: as it stands, {failed}")
        return None

    log(f"\nBASELINE  {target} on {len(cases[target])} golden case(s), "
        f"before anything is touched")
    return refactor(client, finding, source, cases_path, cases[target], baseline, log)


def load_cases(path):
    """The golden inputs that came with the fixture."""
    spec = importlib.util.spec_from_file_location("cases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CASES


if __name__ == "__main__":
    run(anthropic.Anthropic(), sys.argv[1] if len(sys.argv) > 1 else "fixtures/billing")
