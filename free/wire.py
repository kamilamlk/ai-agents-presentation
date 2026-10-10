"""
The free tier, and the whole wire in sight.

    export GROQ_API_KEY=gsk_...
    python3 free/wire.py          # which models this key can reach today

Groq's free tier speaks the OpenAI chat-completions shape, and that shape fits
into one urllib POST -- so there is no SDK in this directory at all. Every
request the examples here make goes through create() below, and you can read all
of it.

The harness does not change. The envelope does:

    tools         {"type": "function", "function": {..., "parameters": schema}}
    the ask       message["tool_calls"]; arguments arrive as a JSON *string*
    done or not   finish_reason == "tool_calls", not stop_reason == "tool_use"
    the result     {"role": "tool", "tool_call_id": ...}, not a user content block
    the system    the first message in the list, not a parameter of its own

Which is the point of this directory: tools, the loop, state and the check are
the same four jobs on any provider. Only the shipping label is different.

    diff examples/example_harness.py free/example_harness.py

Another base URL and the same four files run against something else:

    Ollama        FREE_BASE_URL=http://localhost:11434/v1  FREE_MODEL=qwen2.5-coder
    OpenRouter    FREE_BASE_URL=https://openrouter.ai/api/v1  FREE_MODEL=...:free
"""

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("FREE_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
# What a free key could reach on 2026-10-10. The Llama ids every tutorial names
# are not on that list any more -- they moved behind a sales conversation. Check
# with `python3 free/wire.py` before you trust any id, including this one.
MODEL = os.environ.get("FREE_MODEL", "openai/gpt-oss-120b")
TIMEOUT_SECONDS = 60

# Measured, not decorative. urllib introduces itself as "Python-urllib/3.9", and
# Groq sits behind Cloudflare, which refuses that signature: 403 with the body
# "error code: 1010" -- before the key is ever looked at. Same URL, same network,
# same moment: curl -A "Python-urllib/3.9" -> 403, curl -A "Mozilla/5.0" -> 401.
# The SDK in examples/ sends its own header and never meets this.
USER_AGENT = "build-the-harness/1.0 (workshop example; python-urllib)"

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}


def key():
    """A local model needs no key. A hosted free tier does, and it is free."""
    token = os.environ.get("GROQ_API_KEY") or os.environ.get("FREE_API_KEY")
    if token:
        return token
    if "localhost" in BASE_URL or "127.0.0.1" in BASE_URL:
        return "local"
    raise SystemExit(
        "No key. Get a free one at https://console.groq.com/keys, then:\n"
        "    export GROQ_API_KEY=gsk_...\n"
        "Or point FREE_BASE_URL at a local model and no key is needed."
    )


HINTS = {
    401: "The key is missing or wrong. Check GROQ_API_KEY.",
    403: "Refused before the key was read. Two causes, in this order:\n"
         "  error code: 1010  -- Cloudflare does not like the User-Agent. That is\n"
         "                       what USER_AGENT above is for; if you removed it,\n"
         "                       put it back.\n"
         "  anything else     -- where the request came from. A VPN exiting in a\n"
         "                       country the provider does not serve gets a 403.",
    404: "No such path or model id for this key. `python3 free/wire.py` lists\n"
         "what this key can reach today; free tiers retire ids without warning.",
    429: "Free-tier rate limit. Wait a minute, or set FREE_MODEL to a smaller one.",
}


def fetch(request):
    """Every call goes through here, so every failure is explained the same way.
    The server's own text is worth more than ours, so it is read out and shown."""
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace").strip()[:400]
        raise SystemExit("\n".join(filter(None, [
            f"{error.code} {error.reason} from {request.full_url}",
            body, "", HINTS.get(error.code, "")])))  from None
    except urllib.error.URLError as error:
        raise SystemExit(f"cannot reach {request.full_url}: {error.reason}") from None


def post(path, body):
    return fetch(urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        headers={**HEADERS, "Content-Type": "application/json",
                 "Authorization": f"Bearer {key()}"},
    ))


def create(messages, tools=None, system=None, model=None, max_tokens=1024,
           temperature=None):
    """One call. Returns (message, finish_reason).

    temperature is left out of the body unless a caller asks for one, so these
    examples run on whatever the provider defaults to -- exactly like the ones in
    examples/, which do not set it either. Sending 0 by default would have been a
    second difference between the two directories, and the only difference worth
    showing there is the envelope.

    It is still a lever, and the reviewer uses it: judging one comment is not a
    place to sample. Note what it does not buy you -- "steadier", not
    "reproducible". The same prompt at 0 can still come back different.
    """
    body = {
        "model": model or MODEL,
        "max_tokens": max_tokens,          # OpenAI now calls this max_completion_tokens
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
    }
    if tools:
        body["tools"] = tools
    if temperature is not None:
        body["temperature"] = temperature

    data = post("/chat/completions", body)
    choice = data["choices"][0]

    usage = data.get("usage") or {}
    USAGE["calls"] += 1
    USAGE["prompt_tokens"] += usage.get("prompt_tokens", 0)
    USAGE["completion_tokens"] += usage.get("completion_tokens", 0)

    return choice["message"], choice["finish_reason"]


def arguments(tool_call):
    """The arguments of a tool call arrive as a string of JSON, not as an object.

    Small models sometimes send something that is not JSON at all, and that is a
    tool result like any other: hand the error back and let the model retry.
    """
    raw = tool_call["function"]["arguments"] or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"arguments are not JSON: {raw!r} ({error})") from None


def text(message):
    """The assistant's prose. Absent when the model only asked for a tool."""
    return message.get("content") or ""


def spent():
    return (f"{USAGE['calls']} call(s), {USAGE['prompt_tokens']} tokens in, "
            f"{USAGE['completion_tokens']} out, 0.00 to pay")


def models():
    data = fetch(urllib.request.Request(
        f"{BASE_URL}/models",
        headers={**HEADERS, "Authorization": f"Bearer {key()}"}))
    return sorted(m["id"] for m in data["data"])


if __name__ == "__main__":
    print(f"{BASE_URL}  (FREE_MODEL={MODEL})\n")
    for name in models():
        print(" ", name)
    print("\nA model id that is not on this list is the most common first error:"
          "\nfree tiers retire them without warning.")
