"""
Tests for the free-tier port. No key, no network, not a single token.

    python3 free/test_free.py

The model is replaced by a fake that returns prepared replies in the OpenAI
shape and remembers what it was asked. The transport is replaced too, so the
body-building in wire.py is checked without leaving the machine.
"""

import copy
import json

import wire
from example_harness import check, run as run_harness
from example_rag import ask
from example_review_agent import judge, verify


# -- The fake model ---------------------------------------------------------

def tool_call(name, call_id="call_1", **kwargs):
    # arguments are a string of JSON on this wire, not an object
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(kwargs)}}


def asks(*calls):
    return ({"role": "assistant", "content": None, "tool_calls": list(calls)}, "tool_calls")


def says(text):
    return ({"role": "assistant", "content": text, "tool_calls": None}, "stop")


def answers(payload):
    return says(f"here you go\n```json\n{json.dumps(payload)}\n```")


class FakeCall:
    """Stands in for wire.create and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def __call__(self, messages, tools=None, system=None, **kw):
        # The snapshot is mandatory: messages is mutated as the loop runs.
        self.sent.append({"messages": copy.deepcopy(messages),
                          "tools": tools, "system": system})
        return self.replies.pop(0)


def quiet(*a, **kw):
    pass


# -- wire.py: the body we actually send -------------------------------------

def fake_transport(captured, response=None):
    def post(path, body):
        captured.append({"path": path, "body": body})
        return response or {
            "choices": [{"message": {"role": "assistant", "content": "hi",
                                     "tool_calls": None}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3},
        }
    return post


def test_system_is_sent_as_the_first_message():
    sent = []
    wire.post = fake_transport(sent)
    wire.create([{"role": "user", "content": "q"}], system="be brief")
    assert sent[0]["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent[0]["body"]["messages"][1]["content"] == "q"


def test_tools_are_left_out_when_there_are_none():
    sent = []
    wire.post = fake_transport(sent)
    wire.create([{"role": "user", "content": "q"}])
    assert "tools" not in sent[0]["body"]


def test_usage_adds_up_across_calls():
    wire.post = fake_transport([])
    wire.USAGE.update(calls=0, prompt_tokens=0, completion_tokens=0)
    wire.create([{"role": "user", "content": "q"}])
    wire.create([{"role": "user", "content": "q"}])
    assert wire.USAGE["calls"] == 2
    assert wire.USAGE["prompt_tokens"] == 22
    assert "0.00 to pay" in wire.spent()


def test_arguments_come_out_of_a_string():
    assert wire.arguments(tool_call("read_context", path="a.py", line=3)) == {
        "path": "a.py", "line": 3}


def test_arguments_that_are_not_json_are_refused_not_crashed():
    broken = {"id": "call_1", "function": {"name": "find_name", "arguments": "{word:"}}
    try:
        wire.arguments(broken)
    except ValueError as error:
        assert "not JSON" in str(error)
        return
    raise AssertionError("malformed arguments must raise, not pass silently")


# -- The harness: check() is provider-independent ---------------------------

def test_check_catches_the_midnight_step_backwards():
    assert "23:47" in check(["23:40", "23:47", "00:05"])


def test_tool_result_is_its_own_message_tied_back_by_id():
    call = FakeCall(
        asks(tool_call("read_timetable", call_id="call_abc", city="Tashkent")),
        answers({"times": ["23:40", "23:47", "24:05"]}),
    )
    run_harness(call, log=quiet)

    result = call.sent[1]["messages"][-1]
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_abc"
    assert "5A" in result["content"]


def test_retry_after_a_failed_check():
    call = FakeCall(
        answers({"times": ["23:40", "23:47", "00:05"]}),   # copied as printed
        answers({"times": ["23:40", "23:47", "24:05"]}),   # corrected
    )
    assert run_harness(call, log=quiet) == ["23:40", "23:47", "24:05"]
    assert "Not good" in call.sent[1]["messages"][-1]["content"]


def test_loop_is_not_infinite():
    call = FakeCall(*[answers({"times": ["09:00", "08:00"]}) for _ in range(6)])
    try:
        run_harness(call, log=quiet)
    except RuntimeError:
        return
    raise AssertionError("the loop should have given up")


def test_truncated_answer_is_not_success():
    call = FakeCall(({"role": "assistant", "content": "```json"}, "length"))
    try:
        run_harness(call, log=quiet)
    except RuntimeError as error:
        assert "length" in str(error)
        return
    raise AssertionError("a truncated answer must fail, not be accepted")


# -- RAG: the citation has to have been retrieved ---------------------------

def test_a_source_that_was_never_retrieved_is_refused():
    call = FakeCall(
        answers({"answer": "at 04:00 UTC", "source": "d9"}),
        answers({"answer": None, "source": None}),
    )
    ask("when is the data refreshed?", call, log=quiet)
    assert "not among the retrieved" in call.sent[1]["messages"][-1]["content"]


def test_an_honest_no_answer_is_accepted():
    call = FakeCall(answers({"answer": None, "source": None}))
    assert ask("what does it cost?", call, log=quiet) == {"answer": None, "source": None}


# -- The reviewer: the same check, turned on the model's answer -------------

VOCAB = {"upsert_row", "orders", "connect"}


def test_a_replacement_naming_another_missing_word_is_refused():
    problem = verify({"verdict": "stale", "replacement": "# written by insert_row"},
                     "insert_row", VOCAB)
    assert "still names insert_row" in problem

    problem = verify({"verdict": "stale", "replacement": "# written by write_row"},
                     "insert_row", VOCAB)
    assert "write_row" in problem

    assert verify({"verdict": "stale", "replacement": "# written by upsert_row"},
                  "insert_row", VOCAB) is None


def test_a_foreign_verdict_may_not_carry_a_rewrite():
    assert verify({"verdict": "foreign", "replacement": "# anything"},
                  "idempotency_key", VOCAB) is not None
    assert verify({"verdict": "foreign", "replacement": ""},
                  "idempotency_key", VOCAB) is None


def test_judge_reads_the_file_then_gets_accepted():
    candidate = ("storage.py", 1, "insert_row", "# written by insert_row")
    call = FakeCall(
        asks(tool_call("find_name", call_id="call_x", word="insert_row")),
        answers({"verdict": "stale", "replacement": "# written by upsert_row"}),
    )
    answer = judge(call, candidate, VOCAB, root="free", log=quiet)
    assert answer["verdict"] == "stale"
    assert call.sent[1]["messages"][-1]["tool_call_id"] == "call_x"


def test_two_refused_verdicts_go_to_a_human():
    candidate = ("storage.py", 1, "insert_row", "# written by insert_row")
    call = FakeCall(
        answers({"verdict": "stale", "replacement": ""}),
        answers({"verdict": "nonsense", "replacement": ""}),
    )
    assert judge(call, candidate, VOCAB, root="free", log=quiet) is None


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
