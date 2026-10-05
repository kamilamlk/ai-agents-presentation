"""
Code narrows the field before the model is ever called.

    python3 example_review.py
    python3 example_review.py ../some/service

Finds comments that name something the code does not have. No model, no API key,
nothing to pay, and it runs on a whole service in a fraction of a second.

Why it is here. "The comments are stale" sounds like a job for a model, and part
of it is. This part is not: a comment that names a function nobody has anymore is
a set difference. Doing that first is what makes the model part affordable -- it
arrives at a handful of candidates instead of a whole service.

The rule, stated exactly, because a check you cannot state is not a check:

    the comment marks a word as code -- backticks, snake_case, or call parens;
    that word is not a name the code uses;
    that word is not part of a name the code uses either.

The third line matters: cache_read lives inside cache_read_input_tokens, and the
code has it. Dropping that line gave twenty findings on this repository and all
twenty were noise.

What survives the rule is not automatically a bug. On this repository it finds
two, and both name real things that live outside it -- a CLI placeholder and an
API field. Deciding which absent name is stale and which is legitimately foreign
is the first thing here a model is actually needed for.

The seam is printed at the end of a run. Everything before it is this file;
everything after it is example_review_agent.py, where the model says what to do
and code checks what it said.
"""

import re
import sys
import tokenize
from pathlib import Path

# What counts as a mention: a backticked word, a snake_case word, or a word with
# call parentheses. Prose does not look like this by accident.
MENTION = re.compile(
    r"`([A-Za-z_][\w.]*)`"
    r"|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"
    r"|\b([A-Za-z_]\w*)\(\)"
)


def read(path):
    """Names the code uses, words its strings contain, and what the prose says."""
    names, prose = set(), []
    try:
        with open(path, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.NAME:
                    names.add(tok.string)
                elif tok.type == tokenize.COMMENT:
                    prose.append((tok.start[0], tok.string))
                elif tok.type == tokenize.STRING:
                    if tok.string[:3] in ('"""', "'''"):
                        prose.append((tok.start[0], tok.string))
                    else:
                        # A string value is still something the code has. "tool_use"
                        # is not a missing identifier, it is a literal.
                        names |= set(re.findall(r"[A-Za-z_]\w+", tok.string))
    except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        return set(), []        # a file we cannot parse is not a file we judge
    return names, prose


def mentioned(text):
    """Backticks and () are the author marking code, so length does not matter
    there. A bare snake_case word has to be long enough not to be prose."""
    out = []
    for tick, snake, call in MENTION.findall(text):
        word = (tick or snake or call).split(".")[-1]
        if snake and len(word) <= 3:
            continue
        if word not in out:
            out.append(word)
    return out


def check(word, vocabulary):
    """Verification. Two lookups, both exact, both cheap, both explainable."""
    if word in vocabulary:
        return f"{word} is still in the code"
    # A whole-word miss is not enough: cache_read lives inside
    # cache_read_input_tokens, and the code has it.
    if any(word in name for name in vocabulary):
        return f"{word} is part of a name the code still has"
    return None


def sources(root="."):
    """The files this check is about: Python, minus anything vendored."""
    return sorted(p for p in Path(root).rglob("*.py") if ".venv" not in p.parts)


def vocabulary(files):
    """Everything the code has. A module name is something we have too."""
    vocab = {p.stem for p in files}
    for p in files:
        names, _ = read(p)
        vocab |= names
    return vocab


def review(root=".", log=print):
    files = sources(root)
    vocab = vocabulary(files)
    prose = [(path, line, text) for path in files for line, text in read(path)[1]]

    candidates = {(p, line, w, t) for p, line, t in prose for w in mentioned(t)}
    log(f"\nSCANNED   {len(files)} files, {len(vocab)} names the code has, "
        f"{len(candidates)} mentions to judge")

    findings = []
    for path, line, word, text in sorted(candidates):
        if check(word, vocab) is None:
            findings.append((path, line, word, " ".join(text.split())[:70]))

    for path, line, word, snippet in findings:
        log(f"stale     {path}:{line}  names {word!r}, which the code does not have")
        log(f"          {snippet}")

    log(f"\nFOUND     {len(findings)} stale mention(s)")
    log("          Code got this far without a model. The model's job starts here:")
    log("          read the comment and the code around it, say what to write instead.")
    return findings


if __name__ == "__main__":
    review(sys.argv[1] if len(sys.argv) > 1 else ".")
