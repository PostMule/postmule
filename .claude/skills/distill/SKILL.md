---
name: distill
description: Extract the hidden methodology from any expert content (transcript, article, book excerpt). Names the framework, surfaces the steps, and produces a reusable reference. Use when the user pastes a transcript or text and wants the underlying system extracted.
---

# Distill — Framework Extraction

You are running the Distill skill. Your job is to reverse-engineer the expert methodology inside the provided content and produce a clean, reusable framework document.

---

## Step 1: ABSORB (silent)

Read the full content. Identify:

- **The core problem being solved** — what pain or question does this expertise address?
- **The implied sequence** — are there stages, phases, or an order of operations?
- **The key distinctions** — what does the expert separate that most people conflate?
- **The decision criteria** — what tells you which path to take?
- **The named concepts** — any terms the expert coined or uses in a specific way?
- **What is NOT said** — constraints, failure modes, or edge cases the expert skips over

---

## Step 2: NAME AND STRUCTURE

Construct the framework:

1. **Give it a name** — short, memorable, describes the transformation (e.g. "The 3-Layer Diagnosis", "The Outcome-First Stack"). If the expert already named it, use that.
2. **Write a one-sentence summary** — what does this framework help someone do?
3. **Extract the steps or principles** — numbered list, in order if sequential, or grouped if parallel. Use the expert's language where precise; paraphrase where clearer.
4. **Identify the core insight** — the single non-obvious thing that makes this framework work. Most frameworks have one idea that everything else follows from.
5. **Name the failure mode** — what does someone do wrong when they skip or misapply this?

---

## Step 3: DELIVER

Output exactly this structure:

---

## [Framework Name]

**What it does:** [one sentence — the transformation or outcome it produces]

**Core insight:** [the one non-obvious idea the whole thing rests on]

---

### The Steps / Principles

1. **[Step name]** — [what to do and why it matters]
2. **[Step name]** — [what to do and why it matters]
3. *(continue as needed)*

---

### How to Apply It

A short paragraph (3–5 sentences) describing a concrete use case. Write it in second person ("You..."), grounded in a realistic scenario.

---

### Failure Mode

**What goes wrong:** [the most common misapplication]
**Why it happens:** [root cause — usually a skipped step or a misread principle]
**Fix:** [what to do instead]

---

### Limitations

- [What this framework doesn't cover]
- [Context where it breaks down or needs modification]
- [Any assumptions baked in that may not hold]

---

### Source

[Title or description of the original content, if provided. Otherwise: "Source not specified."]

---

**Rules:**
- Do not pad. If the framework has 3 real steps, output 3 — not 5.
- Use the expert's own terms where they are precise. Paraphrase only where their language is unclear.
- If the content does not contain a coherent methodology (it's pure opinion, narrative, or anecdote with no extractable system), say so plainly and describe what IS there.
- Do not invent steps that aren't in the source. If something is implied but not stated, note it as "(implied)" next to that step.
