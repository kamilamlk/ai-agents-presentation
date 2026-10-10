"""
The fifth check, from the inside. Not imported: run.

    python3 driver.py <module> <cases.py> <function>

A fresh interpreter, the module under test loaded by path, the golden cases
loaded by path, one line of JSON on stdout. example_complexity_agent.py starts
this twice per refactor -- once on the file as it stands and once on the file
with the model's answer spliced in -- and compares the two.

It is a file and not a string in the harness so that it is readable, and so the
stale-comment reviewer in examples/ reads it as code, which it is.
"""

import importlib.util
import json
import sys


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(subject_path, cases_path, target):
    function = getattr(load(subject_path, "subject"), target)
    records = []

    for args in load(cases_path, "cases").CASES[target]:
        record = {}
        try:
            record["value"] = repr(function(*args))
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
        # After the call, so a mutated argument shows. This is the half of
        # behaviour that a return value says nothing about.
        record["args_after"] = repr(args)
        records.append(record)

    print(json.dumps(records))


if __name__ == "__main__":
    main(*sys.argv[1:4])
