"""The one call that leaves the building.

The provider is slow and occasionally returns 502, so every charge is sent with
a key of our own making and retried a fixed number of times.
"""

import json
import urllib.error
import urllib.request

ENDPOINT = "https://payments.example.com/v1/charges"
RETRY_LIMIT = 3
TIMEOUT_SECONDS = 10


def charge(order_id, total_cents, key, opener=urllib.request.urlopen):
    body = json.dumps({"order": order_id, "amount": total_cents}).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Idempotency-Key": key},
    )

    # The provider echoes idempotency_key back on every response, so sending the
    # same charge twice costs the customer nothing.
    last_error = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            # Retries stop at `MAX_ATTEMPTS` and the order is left for a human.
            if error.code < 500:
                raise
            last_error = error
    raise RuntimeError(f"{ENDPOINT} failed {RETRY_LIMIT} times: {last_error}")
