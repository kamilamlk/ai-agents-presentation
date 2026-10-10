"""
Tests for the review finder. No API calls, no tokens, no network, no git.

    python3 test_review.py

Each repository test writes two or three lines into a temporary directory and
runs the finder on it. That is enough: the rule is a set difference, and a set
difference is cheap to corner.
"""

import tempfile
from pathlib import Path

from example_review import mentioned, review


# -- mentioned(): what counts as naming something --------------------------

def test_picks_up_snake_case():
    assert "read_timetable" in mentioned("# calls read_timetable once per city")


def test_picks_up_backticks_and_short_calls():
    # Backticks and parens are the author marking code, so three letters is fine.
    assert mentioned("# `check` is five lines") == ["check"]
    assert mentioned("# then run() takes over") == ["run"]


def test_ignores_ordinary_prose():
    assert mentioned("# this is a perfectly ordinary English sentence") == []


def test_strips_the_owner():
    assert mentioned("# see usage.input_tokens") == ["input_tokens"]


# -- review(): the finder on a small tree ----------------------------------

def tree(source):
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text(source, encoding="utf-8")
    return root


def quiet(*a, **kw):
    pass


def names_found(source):
    return [f[2] for f in review(tree(source), log=quiet)]


def names_found_in(root):
    return [f[2] for f in review(root, log=quiet)]


def test_a_name_the_code_does_not_have_is_flagged():
    assert names_found(
        "# old_billing_hook runs first\n"
        "def keep():\n"
        "    return 1\n"
    ) == ["old_billing_hook"]


def test_a_name_the_code_still_has_is_not_flagged():
    assert names_found(
        "# keep_me runs first\n"
        "def keep_me():\n"
        "    return 1\n"
    ) == []


def test_part_of_a_longer_name_is_not_flagged():
    # cache_read lives inside cache_read_input_tokens, and the code has it.
    assert names_found(
        "# cache_read tells you it worked\n"
        'value = {"cache_read_input_tokens": 0}\n'
    ) == []


def test_a_word_only_in_a_string_counts_as_had():
    # "tool_use" is a literal, not a missing identifier.
    assert names_found(
        "# branch on tool_use\n"
        'if reason == "tool_use":\n'
        "    pass\n"
    ) == []


def test_planted_tree_is_skipped_from_above_and_read_from_inside():
    # fixtures/ is the exercise, so a run from the root must not see it -- but a
    # run pointed at it must see everything in it.
    root = Path(tempfile.mkdtemp())
    (root / "service.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    planted = root / "fixtures" / "orders_service"
    planted.mkdir(parents=True)
    (planted / "orders.py").write_text(
        "# gone_name runs first\ndef keep():\n    return 1\n", encoding="utf-8")

    assert names_found_in(root) == []
    assert names_found_in(planted) == ["gone_name"]


def test_unparsable_file_is_skipped_not_crashed():
    root = Path(tempfile.mkdtemp())
    (root / "broken.py").write_text("def (((\n", encoding="utf-8")
    assert review(root, log=quiet) == []


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
