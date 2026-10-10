"""
Tests for the measure. No API calls, no tokens, no network.

    python3 test_complexity.py

Three lines of source in a temporary directory is enough to corner a measure,
and a measure that cannot be cornered is not one.
"""

import tempfile
from pathlib import Path

from example_complexity import MAX_LINES, measure, scan

FIXTURE = Path(__file__).parent / "fixtures" / "billing"


def sizes(source):
    return {name: size for name, _, size in measure(source)}


def quiet(*a, **kw):
    pass


# -- length(): what counts as one statement --------------------------------

def test_a_docstring_is_not_a_statement():
    assert sizes('def f():\n    """what f is for"""\n    return 1\n') == {"f": 1}


def test_a_semicolon_hides_nothing():
    # Physical lines would say two. The point of counting statements is that
    # this is three things happening.
    assert sizes("def f():\n    a = 1; b = 2\n    return a + b\n") == {"f": 3}


def test_a_call_wrapped_over_four_lines_is_still_one():
    assert sizes("def f():\n    return max(\n        1,\n        2,\n    )\n") == {"f": 1}


def test_nesting_counts_all_the_way_down():
    assert sizes("def f():\n"
                 "    for i in range(3):\n"
                 "        if i:\n"
                 "            print(i)\n") == {"f": 3}


def test_a_nested_function_is_one_statement_and_measured_again_on_its_own():
    assert sizes("def outer():\n"
                 "    def inner():\n"
                 "        a = 1\n"
                 "        return a\n"
                 "    return inner\n") == {"outer": 2, "inner": 2}


def test_source_that_does_not_parse_has_no_answer():
    # None, not []: "cannot parse" and "no functions" are different facts, and
    # the harness needs to tell them apart.
    assert measure("def (((\n") is None
    assert measure("x = 1\n") == []


# -- scan(): the limit, on a small tree ------------------------------------

def over(source):
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text(source, encoding="utf-8")
    return [f[2] for f in scan(root, log=quiet)]


def body(statements):
    return "def f():\n" + "".join(f"    x{i} = {i}\n" for i in range(statements))


def test_exactly_the_limit_is_not_over_it():
    assert over(body(MAX_LINES)) == []


def test_one_more_than_the_limit_is():
    assert over(body(MAX_LINES + 1)) == ["f"]


def test_an_unparsable_file_is_skipped_not_crashed():
    assert over("def (((\n") == []


def test_planted_tree_is_skipped_from_above_and_read_from_inside():
    # fixtures/ is the exercise, so a run from above must not see it -- but a run
    # pointed at it must see everything in it.
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text(body(2), encoding="utf-8")
    planted = root / "fixtures" / "billing"
    planted.mkdir(parents=True)
    (planted / "long.py").write_text(body(MAX_LINES + 1), encoding="utf-8")

    assert [f[2] for f in scan(root, log=quiet)] == []
    assert [f[2] for f in scan(planted, log=quiet)] == ["f"]


# -- The fixture is part of the exercise, so the measure is pinned to it ---

def test_the_fixture_has_exactly_one_function_over_the_limit():
    found = scan(FIXTURE, log=quiet)
    assert [(name, size) for _, _, name, size in found] == [("settle_invoice", 30)]


def test_the_fixture_has_a_function_close_to_the_limit_that_is_left_alone():
    # summary() is eleven statements. A measure that flagged it would be a
    # measure nobody would keep switched on.
    source = (FIXTURE / "billing.py").read_text(encoding="utf-8")
    assert sizes(source)["summary"] == MAX_LINES - 1


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
