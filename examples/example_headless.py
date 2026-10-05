"""
The same harness, with a whole agent behind the call instead of the API.

    python3 example_headless.py
    python3 example_headless.py "When does 5A leave Chorsu?"

Claude Code runs headless: `claude -p` prints an answer and exits. No terminal,
no interaction, a subprocess that takes a prompt and returns JSON.

Nothing else changes. The loop is the same loop, and `check` is imported from
example_harness unmodified -- the same five lines that reject 00:05. A harness
does not care what is behind the call: your own API loop, a colleague's service,
or an agent with its own tools.

Two things it does care about, and both are visible in the log.

COST. The API version of this run was $0.036. Here every call carries the agent's
whole preamble, tools and project files -- about 74,000 tokens -- so a cold run
costs around $0.49 and a warm one around $0.03. The difference is the cache, not
the work.

HANGING. A function either returns or raises. A subprocess can do neither: it can
sit there. The timeout and what happens after it are the harness's job, not the
model's, and that is the second of the four jobs -- the loop owns termination.
"""

import json
import os
import re
import signal
import subprocess
import sys

from example_harness import QUESTION, TIMETABLE, check

MODEL = "sonnet"
TIMEOUT = 120          # seconds a single call is allowed to take
MAX_HANGS = 1          # how many hangs the run tolerates before giving up

SYSTEM = (
    "You extract public transport timetables. "
    "Answer about the trip that was asked for and no other, one time per stop. "
    'End your answer with a ```json block shaped like {"times": ["06:15", "06:47"]} '
    "and nothing after it."
)


class Hung(Exception):
    """Nothing came back in time. Not a model error: there is no answer to judge."""


def ask(prompt, log):
    """One call to the agent. Returns its text, prints what it cost."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", MODEL,
        "--append-system-prompt", SYSTEM,
        "--allowedTools", "",          # it needs no tools: the table is in the prompt
    ]
    # The gateway token is for the API, not for this CLI. Leaving it set makes the
    # call fail in a way that looks like a model problem and is not one.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_AUTH_TOKEN"}

    # start_new_session puts the agent in its own process group. Without it a
    # timeout kills `claude` and leaves its children running -- MCP servers,
    # helpers. Measured: one orphan survives every hung call, and they accumulate.
    agent = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env, start_new_session=True)
    try:
        out, err = agent.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(agent.pid), signal.SIGKILL)
        # Whatever it managed to say before it stopped answering is the only
        # evidence there is. Throwing it away leaves you with "it hung" and
        # nothing to act on.
        out, err = agent.communicate()
        said = (err or out or "").strip().replace("\n", " ")[:300]
        raise Hung(f"no answer in {TIMEOUT}s, process group killed"
                   + (f"; it did say: {said}" if said else "; it said nothing at all"))

    if agent.returncode != 0:
        raise RuntimeError(f"claude exited {agent.returncode}: {err.strip()[:200]}")

    body = json.loads(out)
    if body.get("is_error"):
        raise RuntimeError(f"agent reported an error: {body.get('result')}")

    log(f"agent     {body['num_turns']} turn(s), {body['duration_ms'] / 1000:.1f}s, "
        f"${body['total_cost_usd']:.4f}")
    return body["result"]


def run(question=QUESTION, log=print):
    log(f"\nQUESTION  {question}")
    prompt = f"{TIMETABLE}\n\n{question}"
    hangs = 0

    for _ in range(4):
        try:
            text = ask(prompt, log)
        except Hung as why:
            hangs += 1
            log(f"code      the agent hung: {why}")
            if hangs > MAX_HANGS:
                raise RuntimeError(f"the agent hung {hangs} times; giving up")
            continue       # the decision to try again belongs to the code

        found = re.search(r"```json\s*(.*?)\s*```", text, re.S)
        if not found:
            raise RuntimeError(f"no json block in the answer: {text[:200]}")

        times = json.loads(found.group(1))["times"]
        log(f"model     proposes {', '.join(times) or 'nothing'}")

        problem = check(times)
        if not problem:
            log(f"code      accepted: {', '.join(times)}")
            return times

        log(f"code      rejected: {problem}")
        # Each call is stateless on purpose: the harness carries the state, the
        # same way it does against the API. `claude --resume <session_id>` would
        # hand that job to the agent instead.
        # The correction is appended, never substituted for the task. Replace the
        # task with the complaint and the agent answers the complaint: on one run
        # it returned every time in the table, which increases and passes the check.
        prompt = (
            f"{TIMETABLE}\n\n{question}\n\n"
            f"Your previous answer {', '.join(times)} was rejected: {problem}. "
            f"Same question, same stops, corrected JSON."
        )

    raise RuntimeError("did not finish within the allotted turns")


if __name__ == "__main__":
    # A harness that gives up says why in one line. A traceback here would be the
    # script reporting its own surprise, and giving up is not a surprise.
    try:
        run(" ".join(sys.argv[1:]) or QUESTION)
    except (RuntimeError, Hung) as why:
        print(f"code      gave up: {why}")
        raise SystemExit(1)
