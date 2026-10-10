# BUILD THE HARNESS — slide by slide

22 slides, Dev Camp. Generated from [`deck_brand.json`](deck_brand.json) by [`render_outline.py`](render_outline.py) — edit the spec, not this file.

The rendered `.pptx` is not published: it is built from a corporate template with licensed fonts. This is the same content, as text.

---

## 1. BUILD THE HARNESS

`cover-center`

*Kamila Malikova — Software developer*

---

## 2. WHAT WE DO

`agenda`

- Why the code around the model
- What a harness is made of
- How a tool call works
- Verification in code
- What a run costs, and caching
- Search as a tool
- Workshop: your own task

---

## 3. A MODEL IS NOT A FEATURE. THE CODE AROUND IT IS.

`statement`

**What this is about**

---

## 4. TWO PLACES

`list`

AI shows up in your work in two places, and people mix them up. One question tells them apart: if the API key is switched off tomorrow, does the product stop, or do you just type more?

**In the product**

- The service calls a model at runtime
- It runs on every user file, every day
- The company pays for as long as it lives
- Switch the key off and the product stops

**In your process**

- You call a model while you build
- You pay once, and only for your own work
- Nothing in production depends on it
- Switch the key off and you just type more

---

## 5. IT REPEATS, AND GETTING IT WRONG IS EXPENSIVE.

`question`

**When a task earns a harness**

---

## 6. A harness does four things

`blocks4`

**Agent = model + harness**

- **The loop** — Call the model again, or stop. And when to stop by force.
- **Tools** — What the model may ask for. It never acts, it asks.
- **State** — What the model sees this turn, and what to drop.
- **Verification** — Code inspects the result before accepting it.

---

## 7. THE CHECK

`code`

The last trip crosses midnight. The model copies 00:05 from the timetable: well formed, plausible, wrong. Five lines of ordinary Python notice and send it back.

```
model  23:40, 23:47, 00:05
code   rejected
       23:47 is before 00:05
model  23:40, 23:47, 24:05
code   accepted
```

---

## 8. THE CHECK COSTS NOTHING. BEING WRONG COSTS MONEY.

`question`

**Six runs out of six**

---

## 9. TOOL CALL

`list`

The model executes nothing, it asks. Running the function is the only place your code acts, and it is where the security boundary and the spending control live.

**while stop_reason == tool_use**

- You send the messages and the tool definitions
- The model replies with stop_reason = tool_use
- Your code runs the function and appends tool_result
- You repeat until stop_reason is end_turn

---

## 10. Four of them arrive in silence

`blocks4`

**stop_reason: seven values, four silent**

- **max_tokens** — Your own limit fired. The answer is cut mid-sentence.
- **pause_turn** — The server loop asks to continue. Do not add «Continue».
- **refusal** — A safety refusal. Only here is stop_details filled in.
- **context window** — The conversation no longer fits and nothing warns you.

---

## 11. THE MESSAGES

`code-plain`

**Appended, then resent in full**

```
+ [0] user       question
+ [1] assistant  tool_use
+ [2] user       tool_result
+ [3] assistant  00:05
+ [4] user       rejected
+ [5] assistant  24:05
```

---

## 12. WHAT IT COSTS

`stats`

**Token economics**

Prices here are Opus 5, as an example. Output costs five times input, and the whole list above is resent every round: 425 input tokens, then 593, then 1247, for one question that never changed.

**Opus 5, per 1M tokens**

- **$5** — input
- **$25** — output

**One run, three rounds**

- **$0.036** — the whole run
- **56%** — was the model writing

---

## 13. THE LEVERS

`list`

A harness can pick a model per sub-task, and full delegation cannot. Every number here was measured on a real run, not taken from an article.

**Three levers you own, and one you do not**

- A cheaper model for the mechanical sub-task
- Prompt caching: 27 percent off a measured run
- Batch processing: asynchronous costs half
- How many rounds it takes is the model's decision

---

## 14. CACHING

`cards`

**Prompt caching**

- **Plain input, every call** — 1.00x
- **A cache write, once** — 1.25x
- **A cache read, after that** — 0.10x

---

## 15. PUT A DATE AT THE TOP AND THE CACHE NEVER HITS.

`statement`

**27 percent off the run**

---

## 16. Decisions move from model to code

`blocks4`

**Decisions over time**

- **You know no rules** — Model. Expensive and unpredictable, but it works today.
- **You see a pattern** — In transit. Twenty examples in, a rule shows through.
- **The rule is in code** — Code. Cheap, instant, the same answer every time.
- **A human at runtime** — Someone presses confirm. Deliberately not automated.

---

## 17. RAG

`list`

Not a separate architecture. Replace read_timetable with search and you have RAG. The weak link is retrieval, not generation.

**How it works**

- Index: cut documents into chunks
- Search: pull chunks for this question
- Answer: chunks plus the question go to the model
- Search is a tool like any other

**What actually breaks**

- If the chunk is missing, the model answers anyway
- The model decides how many searches to run
- Two questions, two and four searches, measured
- Grounding is checked in code, not requested

---

## 18. THE RAG CHECK

`code`

An honest «not in the sources» is not the default. It happened only because the output shape allowed null and the code refused any citation that was never retrieved.

```
if answer is None:
    return None
if source not in found:
    return "never retrieved"
```

---

## 19. NOW YOU BUILD ONE

`section`

`Workshop` · `Your own task` · `40 minutes`

---

## 20. Decide four things before you code

`blocks4`

**For every idea**

- **The task** — One sentence, narrow enough to finish today.
- **The tools** — What the model is allowed to ask for.
- **The check** — What code verifies, in five lines.
- **When it stops** — How many retries, and who gets it then.

---

## 21. THE FILTER

`list`

Four kinds of check: something must exist, numbers must match, code must run, and the model's own answer goes back through the check. Yours should be one of them.

**Four checks that already work**

- Triage a ticket: the component must exist
- Weekly digest: every number must match code
- Bug report into a test: red, then green
- Stale comments: the name must be in the code

**Filter your idea in this order**

- Can code check the result without a human
- Does the task repeat
- Does the check fit in five lines
- If not, it is a prompt with extra steps

---

## 22. KAMILA MALIKOVA

`closing`

**Ready for questions**

*Software developer*

---
