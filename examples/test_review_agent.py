"""
Tests for the review agent. No API calls, no tokens, no network.

    python3 test_review_agent.py

The model is replaced by the same stub the harness tests use, so these tests are
about the four jobs and nothing else: what the tool returned, what the loop did,
what state was carried, and what verification refused to accept.
"""

import json
import tempfile
from pathlib import Path

from example_review_agent import RETRIES, ROUNDS, judge, run, verify
from test_harness import FakeClient, quiet, reply, text_block, tool_block

VOCAB = {"keep_me", "cache_read_input_tokens", "run"}
CANDIDATE = (Path("service.py"), 12, "old_billing_hook", "# old_billing_hook runs first")


def says(verdict, replacement=""):
    body = json.dumps({"verdict": verdict, "replacement": replacement})
    return reply("end_turn", text_block(f"```json\n{body}\n```"))


def tree(source):
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text(source, encoding="utf-8")
    return root


# -- VERIFICATION: what the code refuses to take from the model --------------

def test_an_invented_verdict_is_refused():
    assert "verdict must be one of" in verify({"verdict": "probably"}, "x", VOCAB)


def test_stale_without_a_replacement_is_refused():
    assert "needs the replacement" in verify({"verdict": "stale"}, "x", VOCAB)


def test_a_replacement_that_keeps_the_dead_name_is_refused():
    answer = {"verdict": "stale", "replacement": "old_billing_hook still runs first"}
    assert "still names" in verify(answer, "old_billing_hook", VOCAB)


def test_a_replacement_naming_another_absent_thing_is_refused():
    # The point of the whole file: the model's own text goes through the check
    # that found the candidate in the first place.
    answer = {"verdict": "stale", "replacement": "the work moved to legacy_dispatch"}
    assert "legacy_dispatch" in verify(answer, "old_billing_hook", VOCAB)


def test_a_replacement_naming_something_real_is_accepted():
    answer = {"verdict": "stale", "replacement": "`keep_me` runs first"}
    assert verify(answer, "old_billing_hook", VOCAB) is None


def test_foreign_must_not_rewrite_anything():
    answer = {"verdict": "foreign", "replacement": "something else entirely"}
    assert "leaves the comment alone" in verify(answer, "resume_flag", VOCAB)


def test_foreign_with_nothing_to_rewrite_is_accepted():
    assert verify({"verdict": "foreign", "replacement": ""}, "resume_flag", VOCAB) is None


# -- TOOLS: the model asks, the code reads the file --------------------------

def test_tool_result_carries_the_real_lines():
    root = tree("# old_billing_hook runs first\ndef keep_me():\n    return 1\n")
    c = FakeClient(
        reply("tool_use", tool_block("read_context", path=str(root / "service.py"), line=1)),
        says("stale", "`keep_me` runs first"),
    )
    judge(c, (root / "service.py", 1, "old_billing_hook", ""), VOCAB, root, quiet)

    sent = c.sent[1]["messages"][-1]
    assert sent["role"] == "user"
    assert sent["content"][0]["type"] == "tool_result"
    assert "def keep_me" in sent["content"][0]["content"]


def test_a_missing_file_is_answered_not_raised():
    c = FakeClient(
        reply("tool_use", tool_block("read_context", path="nowhere.py", line=3)),
        says("fine"),
    )
    judge(c, CANDIDATE, VOCAB, ".", quiet)
    assert "no such file" in c.sent[1]["messages"][-1]["content"][0]["content"]


# -- THE LOOP: who decides to call again, and who gives up -------------------

def test_a_refused_answer_is_sent_back_and_the_second_accepted():
    c = FakeClient(
        says("stale", "the work moved to legacy_dispatch"),   # names a ghost
        says("stale", "`keep_me` runs first"),
    )
    answer = judge(c, CANDIDATE, VOCAB, ".", quiet)
    assert answer["replacement"] == "`keep_me` runs first"
    assert "Not good" in c.sent[1]["messages"][-1]["content"]


def test_one_retry_then_a_human_gets_it():
    c = FakeClient(*[says("stale", "see legacy_dispatch") for _ in range(ROUNDS)])
    assert judge(c, CANDIDATE, VOCAB, ".", quiet) is None
    assert len(c.sent) == RETRIES + 1          # the first try, then one retry


def test_asking_for_files_cannot_loop_forever():
    # Tool calls do not spend the retry budget, so they need a cap of their own.
    asks = tool_block("find_name", word="old_billing_hook")
    c = FakeClient(*[reply("tool_use", asks) for _ in range(ROUNDS)])
    assert judge(c, CANDIDATE, VOCAB, ".", quiet) is None
    assert len(c.sent) == ROUNDS


def test_an_unexpected_stop_reason_is_not_an_answer():
    c = FakeClient(reply("max_tokens", text_block("```json")))
    try:
        judge(c, CANDIDATE, VOCAB, ".", quiet)
    except RuntimeError as e:
        assert "max_tokens" in str(e)
        return
    raise AssertionError("a truncated answer must fail, not be accepted")


# -- STATE: what the next mention does not see -------------------------------

def test_each_mention_starts_from_an_empty_conversation():
    root = tree("# old_billing_hook runs first\n"
                "# legacy_dispatch handles the rest\n"
                "def keep_me():\n"
                "    return 1\n")
    c = FakeClient(says("foreign"), says("foreign"))
    results = run(c, root, quiet)

    assert len(results) == 2
    assert len(c.sent[1]["messages"]) == 1          # nothing from the first mention
    assert "old_billing_hook" not in json.dumps(c.sent[1]["messages"])


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
