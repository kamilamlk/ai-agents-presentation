"""
Tests for the complexity harness. No API calls, no tokens, no network.

    python3 test_complexity_agent.py

The model is replaced by the same stub the other harnesses use, so these tests
are about the four jobs and nothing else: what the tool returned, what the loop
did, what state was dropped, and what verification refused to accept.

The verification tests are the ones worth reading. Every rejected refactor below
is GOOD with one thing about it changed, so the change is the whole test -- and
the last two are changes that no amount of reading the answer would catch. They
are caught because the code gets run.
"""

import ast
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parent.parent))   # the stub lives with the other examples

from example_complexity import MAX_LINES, measure
from example_complexity_agent import (PRICE_IN, PRICE_OUT, REFUSED, RETRIES, ROUNDS,
                                      behaviour, find, load_cases, measure_code,
                                      money, prompt_size, refactor, run, verify, why)
from test_harness import FakeClient, quiet, reply, text_block, tool_block

FIXTURE = Path(__file__).parent / "fixtures" / "billing"
CASES_PATH = FIXTURE / "cases.py"
SOURCE = (FIXTURE / "billing.py").read_text(encoding="utf-8")
CASES = load_cases(CASES_PATH)["settle_invoice"]
BASELINE, _ = behaviour(SOURCE, "settle_invoice", CASES_PATH)


# -- The refactors the tests are made of ------------------------------------
# One that is right -- fixtures/billing/refactored.py, a file you can read --
# and then one thing at a time changed about it.

def code_only(path):
    """A file without its module docstring. A proposal is functions and no more."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    first = tree.body[1] if ast.get_docstring(tree) else tree.body[0]
    return "\n".join(source.splitlines()[first.lineno - 1:]) + "\n"


GOOD = code_only(FIXTURE / "refactored.py")

CANCELLED_BRANCH = ('    if invoice.get("status") == "cancelled":\n'
                    '        history.append("settled: cancelled, nothing owed")\n'
                    '        return 0\n')

HISTORY_IN_PLACE = '    history = invoice.setdefault("history", [])\n'


def changed(old, new):
    """GOOD, with one thing about it different. The diff is the test."""
    assert old in GOOD, "the refactor these tests are built on has moved"
    return GOOD.replace(old, new)


# The branch is lifted into a helper that reads perfectly well. The helper
# returns 0; the caller does not, and carries on pricing a cancelled invoice.
LOST_RETURN = (
    'def _note_cancelled(invoice, history):\n'
    '    if invoice.get("status") == "cancelled":\n'
    '        history.append("settled: cancelled, nothing owed")\n'
    '        return 0\n'
    + changed(CANCELLED_BRANCH, "    _note_cancelled(invoice, history)\n"))

# One word: setdefault becomes a copy. Every return value stays right, and the
# caller's history list is never written to again.
LOST_MUTATION = changed(HISTORY_IN_PLACE,
                        '    history = list(invoice.get("history", []))\n')

RENAMED = changed("def settle_invoice(invoice):", "def settle(invoice):")
RESIGNED = changed("def settle_invoice(invoice):",
                   'def settle_invoice(invoice, region="UZ"):')
IMPORTED = "import math\n" + changed("max(subtotal, 0)", "math.floor(max(subtotal, 0))")

# The body moved and nothing was split: the thing that made it a candidate is
# still in the answer, under another name.
MOVED = (ast.get_source_segment(SOURCE, find(SOURCE, "settle_invoice"))
         .replace("def settle_invoice(invoice):", "def _everything(invoice):")
         + "\n\ndef settle_invoice(invoice):\n    return _everything(invoice)\n")

BROKEN = "def settle_invoice(invoice):\n    return (\n"


def rejected(proposal):
    return verify(proposal, "settle_invoice", SOURCE, CASES_PATH, BASELINE, CASES)


def says(proposal):
    return reply("end_turn", text_block(f"```python\n{proposal}\n```"))


FINDING = (FIXTURE / "billing.py", 39, "settle_invoice", 30)


def split(client, log=quiet):
    return refactor(client, FINDING, SOURCE, CASES_PATH, CASES, BASELINE, log)


# -- VERIFICATION: the four checks that read the answer ---------------------

def test_a_refactor_that_does_not_parse_is_refused():
    assert "does not parse" in rejected(BROKEN)


def test_losing_the_name_is_refused():
    assert "is not in the answer" in rejected(RENAMED)


def test_changing_the_signature_is_refused():
    assert "the signature changed" in rejected(RESIGNED)


def test_a_new_import_is_refused():
    assert "adds an import" in rejected(IMPORTED)


def test_moving_the_body_without_splitting_it_is_refused():
    # The measure from example_complexity.py, turned on the model's own answer.
    problem = rejected(MOVED)
    assert "_everything has 30 statements" in problem
    assert f"limit of {MAX_LINES}" in problem


# -- VERIFICATION: the check that runs the answer ---------------------------
# Neither of these two can be found by reading. Both parse, both keep the name
# and the signature, both are well under the limit, and both are wrong.

def test_an_early_return_left_behind_in_a_helper_is_refused():
    assert rejected(LOST_RETURN) == (
        "on [{'status': 'cancelled', 'region': 'UZ', "
        "'lines': [{'price_cents': 1999, 'quantity': 2}]}] it returned 4500, "
        "and before the split it returned 0")


def test_a_mutation_that_stopped_reaching_the_caller_is_refused():
    # The return value is right on every single case. Only the argument shows it.
    problem = rejected(LOST_MUTATION)
    assert "the argument came back as" in problem
    assert "'history': ['settled: 4500 cents, region UZ, capped False']" in problem


def test_the_measure_alone_would_have_accepted_both_of_them():
    # Without the subprocess this harness is an opinion about line counts.
    for proposal in (LOST_RETURN, LOST_MUTATION):
        assert max(size for _, _, size in measure(proposal)) <= MAX_LINES


def test_a_refactor_that_survives_all_five_is_accepted():
    assert rejected(GOOD) is None


# -- TOOLS: the model counts its draft, and the count is the real one -------

def test_the_tool_returns_the_same_count_the_limit_uses():
    assert measure_code("def f():\n    a = 1\n    return a\n") == "f has 2 statements"
    assert "over the limit" in measure_code(MOVED)
    assert "does not parse" in measure_code(BROKEN)


def test_tool_result_carries_the_count_back_to_the_model():
    c = FakeClient(
        reply("tool_use", tool_block("measure_code", code="def f():\n    a = 1\n")),
        says(GOOD),
    )
    split(c)

    sent = c.sent[1]["messages"][-1]
    assert sent["role"] == "user"
    assert sent["content"][0]["type"] == "tool_result"
    assert sent["content"][0]["content"] == "f has 1 statements"


def test_a_tool_nobody_has_is_answered_not_raised():
    c = FakeClient(reply("tool_use", tool_block("run_the_tests")), says(GOOD))
    split(c)
    assert "no such tool" in c.sent[1]["messages"][-1]["content"][0]["content"]


# -- THE LOOP: who decides to call again, and who gives up ------------------

def test_a_refused_refactor_is_sent_back_and_the_second_accepted():
    c = FakeClient(says(LOST_RETURN), says(GOOD))
    assert split(c).strip() == GOOD.strip()
    assert "Not good" in c.sent[1]["messages"][-1]["content"]
    assert "it returned 4500" in c.sent[1]["messages"][-1]["content"]


def test_two_retries_then_a_human_gets_it():
    c = FakeClient(*[says(LOST_MUTATION) for _ in range(ROUNDS)])
    assert split(c) is None
    assert len(c.sent) == RETRIES + 1          # the first try, then two retries


def test_asking_to_be_measured_cannot_loop_forever():
    # Tool calls do not spend the retry budget, so they need a cap of their own.
    asks = tool_block("measure_code", code="def f():\n    pass\n")
    c = FakeClient(*[reply("tool_use", asks) for _ in range(ROUNDS)])
    assert split(c) is None
    assert len(c.sent) == ROUNDS


def test_an_answer_with_no_block_in_it_is_not_an_answer():
    c = FakeClient(*[reply("end_turn", text_block("I split it, it is fine now."))
                     for _ in range(ROUNDS)])
    assert split(c) is None


def test_an_unexpected_stop_reason_is_not_an_answer():
    c = FakeClient(reply("max_tokens", text_block("```python\ndef settle_invoice(")))
    try:
        split(c)
    except RuntimeError as e:
        assert "max_tokens" in str(e)
        return
    raise AssertionError("a truncated answer must fail, not be accepted")


# -- STATE: what the next function does not see -----------------------------

def two_long_functions():
    """A fixture of its own: two functions over the limit, and cases for both."""
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text(
        "def first(n):\n" + "".join(f"    n += {i}\n" for i in range(1, 14)) + "    return n\n"
        "\n\n"
        "def second(n):\n" + "".join(f"    n -= {i}\n" for i in range(1, 14)) + "    return n\n",
        encoding="utf-8")
    (root / "cases.py").write_text('CASES = {"first": [[1]], "second": [[5]]}\n',
                                   encoding="utf-8")
    return root


def test_each_function_starts_from_an_empty_conversation():
    root = two_long_functions()
    c = FakeClient(says("def first(n):\n    return n + 91\n"),
                   says("def second(n):\n    return n - 91\n"))
    results = run(c, root, quiet)

    assert [r[1] is not None for r in results] == [True, True]
    assert len(c.sent[1]["messages"]) == 1          # nothing from the first function
    assert [m["role"] for m in c.sent[1]["messages"]] == ["user"]
    # The file is in both prompts -- a function cannot be split without it. What
    # is dropped is the exchange: the first answer is nowhere in the second call.
    assert "n + 91" not in json.dumps(c.sent[1]["messages"])


def test_a_function_with_no_golden_cases_is_not_delegated():
    root = two_long_functions()
    (root / "cases.py").write_text('CASES = {"first": [[1]]}\n', encoding="utf-8")
    c = FakeClient(says("def first(n):\n    return n + 91\n"))
    results = run(c, root, quiet)

    assert [r[1] is not None for r in results] == [True, False]
    assert len(c.sent) == 1                         # second was never asked about


# -- WHAT IT COST: arithmetic, so it is testable like any other -------------

def usage(fresh=0, out=0, written=0, read=0):
    return NS(input_tokens=fresh, output_tokens=out,
              cache_creation_input_tokens=written, cache_read_input_tokens=read)


def test_the_prompt_is_bigger_than_input_tokens_says():
    # The field everyone reads is only the part that missed the cache.
    u = usage(fresh=0, written=1000, read=1000)
    assert u.input_tokens == 0
    assert prompt_size(u) == 2000


def test_writing_costs_five_times_reading_per_token():
    assert money(usage(fresh=1000)) == 1000 * PRICE_IN / 1e6
    assert money(usage(out=1000)) == 1000 * PRICE_OUT / 1e6
    assert money(usage(written=1000, read=1000)) == (1000 * 1.25 + 1000 * 0.10) * PRICE_IN / 1e6


def test_a_round_says_which_decision_bought_it():
    assert why([{"content": "Not good: it does not parse. Return the block again."}]) == REFUSED
    assert "measured" in why([{"content": [{"type": "tool_result", "content": "f has 1"}]}])
    assert why([{"content": "Split settle_invoice."}]) == ""


def test_a_stub_costs_nothing_so_no_table_is_printed():
    # The meter is on in every run, including these: a reply with no usage on it
    # prices at zero, and a table of zeroes would be a lie about a free run.
    lines = []
    run(FakeClient(says(GOOD)), FIXTURE, lines.append)
    assert "COST" not in "".join(lines)


# -- Runner ----------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok     {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAILED {t.__name__}: {e}")
    print(f"\n{len(tests) - failed} of {len(tests)} passed")
