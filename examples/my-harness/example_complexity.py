"""
Code measures. The model is not called at all.

    python3 example_complexity.py
    python3 example_complexity.py fixtures/billing

Counts the statements in every function and lists the ones over MAX_LINES. No
model, no API key, nothing to pay, and it runs on a whole service in a fraction
of a second.

Why it is here. "This function is too long" is not a judgement, it is a number,
and a number does not need a model. Which split is the right one does -- and a
split has to be checked by running it, which is example_complexity_agent.py.

The measure, stated exactly, because a check you cannot state is not a check:

    a statement counts as one, wherever it is nested;
    a docstring is not a statement;
    a nested function is one statement here and is measured again on its own.

Statements and not physical lines, because physical lines measure the formatter:
a call wrapped across four of them is one thing happening, and `a = 1; b = 2` is
two things hiding in one. A model asked to get a number down will do whichever
of those the number rewards, so the number has to reward the right one.

The limit itself is a constant below and nothing more than a convention. Twelve
is this repository's; yours is yours.
"""

import ast
import sys
from pathlib import Path

MAX_LINES = 12                                  # statements a function may have

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


def length(node):
    """How long one function is. Everything nested in it counts, except the
    bodies of functions nested in it: those belong to those functions."""
    nested = {id(s) for f in ast.walk(node) if f is not node and isinstance(f, FUNC)
              for s in ast.walk(f) if s is not f}
    doc = node.body[0] if ast.get_docstring(node) else None
    return sum(1 for s in ast.walk(node)
               if isinstance(s, ast.stmt) and s is not node and s is not doc
               and id(s) not in nested)


def measure(source):
    """Every function in a piece of source, with its size. None means the source
    does not parse -- which is not the same answer as no functions."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    return [(n.name, n.lineno, length(n))
            for n in ast.walk(tree) if isinstance(n, FUNC)]


def sources(root="."):
    """The files this check is about: Python, minus anything vendored or planted.

    fixtures/ holds a service with one function grown too long on purpose. It is
    the exercise, not this repository's code, so a run from above leaves it out
    -- and a run pointed straight at it still reads every file.
    """
    root = Path(root)
    skip = {".venv", "fixtures"}
    return sorted(p for p in root.rglob("*.py")
                  if not skip & set(p.relative_to(root).parts))


def too_long(path):
    """The functions in one file that are over the limit."""
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []           # a file we cannot read is not a file we judge
    return [(Path(path), line, name, size)
            for name, line, size in measure(source) or []
            if size > MAX_LINES]


def scan(root=".", log=print):
    files = sources(root)
    counted = sum(len(measure(p.read_text(encoding="utf-8")) or []) for p in files)
    findings = sorted(f for p in files for f in too_long(p))

    log(f"\nMEASURED  {len(files)} files, {counted} functions, "
        f"limit is {MAX_LINES} statements")
    for path, line, name, size in findings:
        log(f"over      {path}:{line}  {name} has {size} statements, "
            f"{size - MAX_LINES} over")

    log(f"\nFOUND     {len(findings)} function(s) over the limit")
    log("          Code got this far without a model. The model's job starts here:")
    log("          split it without changing what it does.")
    return findings


if __name__ == "__main__":
    scan(sys.argv[1] if len(sys.argv) > 1 else ".")
