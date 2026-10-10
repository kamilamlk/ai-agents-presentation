# orders_service — a service with comments that lie

Four files that price a basket and charge for it. The code works; seven comments
in it do not match the code any more. The drift was put there on purpose, so the
reviewer has something to find on stage.

```bash
python3 examples/example_review.py fixtures/orders_service      # no key, no tokens
source ./anthropic-env.sh on
python3 examples/example_review_agent.py fixtures/orders_service   # seven calls, cents
```

Code alone gets to seven mentions. Which of them is a bug is the model's half.

## The answer key

| Where | Names | Truth |
|---|---|---|
| `orders.py:28` | `validate_promo` | **stale** — the function is `apply_discount` now |
| `payments.py:32` | `MAX_ATTEMPTS` | **stale** — the constant is `RETRY_LIMIT` |
| `storage.py:1` | `insert_row` | **stale** — writes go through `upsert_row`, and they do update |
| `payments.py:24` | `idempotency_key` | **foreign** — the provider's field, correct as written |
| `cli.py:31` | `cron_runner` | **foreign** — lives in another repository |
| `orders.py:38` | `finance_team` | **foreign** — a team, not a name in the code |
| `orders.py:16` | `hot_path` | **fine** — jargon in prose, not a mention of code |

Measured on 2026-10-09: 3 stale, 3 foreign, 1 fine, none sent to a human.
`finance_team` is the interesting one — it is a judgement call, and two runs may
not agree on it.

## The planted miss

`storage.py:42` names `ORDER_STATES`, which the code does not have either, and
the finder walks straight past it: a bare upper-case word is not one of the three
things it treats as a mention. That is the first thing to fix when you extend the
rule — and the reason the rule is written out in words at the top of
`example_review.py`.
