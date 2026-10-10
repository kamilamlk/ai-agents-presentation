"""Price one basket from the command line.

    python3 cli.py 1200x2 450x1 --percent 10
"""

import sys

from orders import price
from storage import connect, upsert_row


def parse(argument):
    cents, _, quantity = argument.partition("x")
    return {"price_cents": int(cents), "quantity": int(quantity or 1)}


def main(argv):
    percent = 0
    if "--percent" in argv:
        at = argv.index("--percent")
        percent = int(argv[at + 1])
        argv = argv[:at] + argv[at + 2:]

    items = [parse(a) for a in argv]
    total = price(items, percent)

    conn = connect()
    upsert_row(conn, "cli-order", total, "priced")
    print(f"{len(items)} item(s), {total} cents")

    # The nightly repricing run is started by cron_runner in the platform repo;
    # this entry point is only ever used by hand.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
