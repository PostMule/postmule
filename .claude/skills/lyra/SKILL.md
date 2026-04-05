---
name: lyra
description: Prompt engineering framework using Deconstruct → Diagnose → Develop → Deliver. Use when user asks to generate a prompt, write a prompt, create a prompt, build a prompt, make a prompt, or draft a prompt for use with any AI or LLM system.
---

# Lyra — Prompt Engineering Framework

You are running the Lyra framework. Follow all four phases in sequence. Do not skip phases or collapse them.

---

## Phase 1: DECONSTRUCT (silent)

Analyze the request without showing your work yet. Extract:

- **Core task** — What must the prompt make an LLM do?
- **Target model** — Claude, Gemini, GPT-4, or unspecified?
- **Runtime input** — What data or context will be injected at runtime?
- **Expected output** — Format, structure, length, schema?
- **Constraints** — Tone, guardrails, things to avoid, length limits
- **Reusability** — One-off use or a reusable template with variable slots?
- **Implicit goals** — What outcome matters beyond the literal request?

---

## Phase 2: DIAGNOSE (show your work, ask only what you must)

Display a concise summary in this format:

**What I inferred:**
- [bullet per key assumption]

**Gaps that would change the prompt:**
- [only flag things that genuinely affect prompt design]
- If nothing is missing, say so and proceed immediately

Rules:
- Do not ask for information you can reasonably infer from context
- Scale questions to complexity: 0 for simple/clear requests, 1–2 for moderate, up to 3 for genuinely complex multi-part prompts. Never exceed 3.
- If you have enough information, say "I have enough to proceed" and move directly to Phase 3
- Wait for user input only if critical gaps exist

---

## Phase 3: DEVELOP

Build the prompt using these principles. Track which choices below you actively made — these feed directly into the Design notes in Phase 4:

**Role/persona:** Add only if it meaningfully shapes behavior. Avoid cargo-cult framing like "You are an expert X" unless the role genuinely changes output style or scope.

**Task definition:** Clear, unambiguous instruction in active voice. One sentence if possible.

**Context block:** Only what the model needs that it won't have at runtime. Cut everything else.

**Input format:** Describe or show the structure of runtime inputs. If using variables, use `{{double_braces}}` as substitution markers.

**Output format:** Be explicit — schema, length, structure, or a brief example. Never leave output format implicit.

**Constraints:** What to avoid, edge cases to handle, tone guardrails. Phrase as positive instructions where possible ("respond in plain language") over prohibitions ("don't use jargon").

**Reasoning scaffolding:** Add chain-of-thought instructions only when the task requires multi-step reasoning. Do not add it by default — it increases token cost and can hurt simple tasks.

**Few-shot examples:** Include 1–2 examples only when the pattern is non-obvious or the output format needs demonstration. Never pad with examples for tasks that are self-explanatory.

**Model-specific tuning:**
- **Claude:** Direct instruction style, XML tags (`<context>`, `<input>`, `<output>`) for complex structure, explicit output format
- **Gemini:** Explicit role framing helps; step-by-step breakdowns improve consistency
- **GPT-4:** Leverage system/user separation; markdown structure works well
- **Unspecified:** Write model-agnostic — prefer plain structure, avoid model-specific syntax

---

## Phase 4: DELIVER

Return only this structure:

---

**Prompt:**
```
[complete, ready-to-use prompt — copy-pasteable, nothing omitted]
```

**Construction logic:**
- [For each active choice made in Phase 3: what you did and why — e.g. "Added reasoning scaffolding: task requires multi-step comparison, chain-of-thought reduces hallucination risk"]
- [Only include components you actively decided on; omit ones that didn't apply]
- [Be specific enough that the user could challenge or override the decision]

**Assumptions to verify:**
- [list assumptions from Phase 1 the user should confirm before deploying this prompt]
- If no meaningful assumptions were made, omit this section

**Suggested test cases:**
- [1–2 example inputs that would confirm the prompt behaves correctly]

---

Deliver the output cleanly. The user should be able to copy the prompt block and use it immediately.
