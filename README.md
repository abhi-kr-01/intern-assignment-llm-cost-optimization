# ShopAssist — LLM Cost Optimization Assignment

## Overview

This repository contains my solutions to both questions of the LLM Optimization Assignment.

The objective was to optimize an AI-powered customer support system, **ShopAssist**, by reducing LLM token consumption and execution costs while preserving the expected support decisions.

The system processes customer support tickets using order information and knowledge-base articles to determine the appropriate action.

Possible actions include:

- `REFUND`
- `REPLACE`
- `SEND_ARTICLE`
- `ESCALATE_TIER2`

The assignment required both implementations to preserve the expected `action` and `kb_article` fields while staying below their respective cost limits.

## Assignment Objectives

| Question | Implementation | Maximum Cost per Ticket |
|---|---|---:|
| Question 1 | SupportCopilot | 3,000 points |
| Question 2 | SupportPipeline | 2,500 points |

The billing formula used throughout the assignment is:

\[
\text{Points} =
(\text{Uncached Input Tokens} \times 3)
+
(\text{Cached Input Tokens} \times 0.3)
+
(\text{Output Tokens} \times 15)
\]

Output tokens have a higher cost than input tokens. Therefore, reducing unnecessary output generation and redundant LLM calls was a major part of the optimization strategy.

---

# Question 1 — SupportCopilot

## Initial Implementation

The original implementation used a single LLM call to process each support ticket.

However, the prompt contained several unnecessary elements:

- A randomly generated UUID for every request.
- Instructions asking the model to think step by step.
- Instructions to generate full reasoning.
- Instructions to quote knowledge-base articles.
- A large help-center context.

These elements increased token consumption without being necessary for producing the required structured output.

## Optimizations Implemented

### 1. Removed Random UUID Generation

**Before:**

A new UUID was generated for every request and inserted into the system prompt.

**After:**

Removed UUID generation and the unused `uuid` import.

**Why?**

The random identifier did not contribute to ticket classification or response generation. Removing it eliminates unnecessary prompt tokens and avoids introducing a variable prefix.

### 2. Optimized the System Prompt

**Before:**

The original prompt instructed the model to:

- Think step by step.
- Write full reasoning.
- Quote the relevant knowledge-base article.
- Generate JSON containing the required fields.

**After:**

Replaced it with a concise instruction:

```text
Return only JSON with action, kb_article, and customer_reply.
Use the order facts and applicable policy.
Keep the response concise.
```

**Why?**

The application needs structured output, not lengthy explanations. The revised prompt focuses the model on the actual task and reduces unnecessary output generation.

## Question 1 Results

| Ticket | Optimized Cost |
|---|---:|
| T-1001 | 2,181 |
| T-1002 | 2,052 |
| T-1003 | 2,013 |
| T-1004 | 1,974 |
| **Total** | **8,220** |
| **Average** | **2,055** |

**Target:** 3,000 points per ticket.

**Result:** All four public tickets are below the required limit.

The optimized implementation reduced the measured total from 35,388 to 8,220 points, approximately a 76.77% reduction.

---

# Question 2 — SupportPipeline

## Initial Implementation

The original implementation used a four-node pipeline:

```text
Triage → Retrieve → Compose → Audit
```

Each node made a separate LLM call.

The main cost problems were:

- Multiple LLM calls for a single ticket.
- Repeated ticket and order information.
- Large help-center context passed to different nodes.
- Retrieval of eight articles, including potentially irrelevant content.
- Repeated instructions and unnecessary reasoning generation.
- Random UUID generation.

Since every LLM call incurred input and output token costs, the original pipeline was expensive.

## Optimization Strategy

Instead of removing the four-stage architecture, I retained all four logical stages and changed how each stage performs its work.

The key idea was:

**Use deterministic Python logic for tasks that do not require an LLM, and reserve the LLM for response generation.**

### Optimized Architecture

```text
              Support Ticket
                    |
                    v
          +-------------------+
          |   1. TRIAGE       |
          |                   |
          | Keyword extraction|
          | Intent detection  |
          +-------------------+
                    |
                    v
          +-------------------+
          |   2. RETRIEVE     |
          |                   |
          | KB article scoring|
          | Top 2 selection   |
          +-------------------+
                    |
                    v
          +-------------------+
          |   3. COMPOSE      |
          |                   |
          | One LLM call      |
          | Generate JSON     |
          +-------------------+
                    |
                    v
          +-------------------+
          |   4. AUDIT        |
          |                   |
          | JSON validation   |
          | Action validation |
          | KB ID validation  |
          +-------------------+
                    |
                    v
              Final Result
```

## Changes Implemented

### 1. Deterministic Triage

**Original approach:**

An LLM call was used to analyze the ticket and identify relevant policies and candidate articles.

**Optimized approach:**

Implemented Python-based keyword extraction and intent detection.

Important helper functions:

- `terms()`
- `flatten_values()`
- `_triage()`

The implementation extracts useful words from the customer conversation and order information.

It also identifies relevant intent categories, including:

- Refund
- Replacement
- Damage
- Digital products
- Custom products

**Why?**

Basic keyword extraction and intent identification do not always require an LLM. Performing these operations in Python avoids an additional model call.

### 2. Deterministic Knowledge-Base Retrieval

**Original approach:**

An LLM call was used to retrieve eight relevant help-center articles.

**Optimized approach:**

Implemented keyword-based article ranking using the existing knowledge base.

The retrieval process:

1. Loads available article IDs using `article_ids()`.
2. Loads article content using `load_article()`.
3. Extracts keywords from article IDs and content.
4. Compares article keywords against ticket keywords and detected intents.
5. Assigns higher weights to article ID matches.
6. Sorts articles by score with deterministic tie-breaking.
7. Selects the two highest-ranked articles.

The scoring logic is:

```python
score = (
    4 * len(query_words & id_words)
    + len(query_words & content_words)
)
```

**Why?**

The retrieval operation is primarily a search and ranking task. It can be implemented using deterministic algorithms without invoking an LLM.

Selecting two articles instead of eight also reduces the amount of context passed to the composition stage.

### 3. Single LLM Call for Composition

This is the only stage that invokes the LLM.

The composition stage receives:

- Ticket ID.
- Customer conversation.
- Order snapshot.
- Triage information.
- Retrieved knowledge-base articles.

The model generates a structured JSON response containing:

```json
{
  "action": "REPLACE",
  "kb_article": "damage-replacement-7-days",
  "customer_reply": "Your replacement request has been processed."
}
```

**Why?**

Natural-language response generation and combining policy information with order facts are tasks where an LLM provides meaningful value.

Instead of using separate LLM calls for triage, retrieval, composition, and audit, the optimized implementation uses one LLM call for composition.

This significantly reduces the number of model calls and token consumption.

### 4. Deterministic Audit

**Original approach:**

A separate LLM call reviewed and rewrote the generated response.

**Optimized approach:**

Implemented deterministic structural validation.

The audit checks:

- Whether the generated response is valid JSON.
- Whether the action belongs to the allowed action set.
- Whether the selected KB article ID exists.
- Whether the expected output fields are available.

**Why?**

Basic output validation does not require an LLM. Python can validate the response structure and allowed values at a much lower cost.

**Important limitation:** This audit performs structural validation. It does not independently verify that the selected action is semantically correct according to every order fact and policy rule.

## Question 2 Results

| Ticket | Path | Input Tokens | Output Tokens | Points |
|---|---|---:|---:|---:|
| T-1001 | Refund | 354 | 46 | 1,752 |
| T-1002 | Digital product / denial | 341 | 39 | 1,608 |
| T-1003 | Escalation | 308 | 39 | 1,509 |
| T-1004 | Physical replacement | 317 | 36 | 1,491 |
| **Total** | | | | **6,360** |
| **Average** | | | | **1,590** |

**Target:** 2,500 points per ticket.

**Result:** All four public tickets are below the required limit.

The optimized implementation reduced the measured cost from approximately 293,000 points to 6,360 points, a reduction of approximately 97.8%.

---

# Comparison of Both Implementations

| Metric | Question 1 | Question 2 |
|---|---:|---:|
| Original LLM calls per ticket | 1 | 4 |
| Optimized LLM calls per ticket | 1 | 1 |
| Average optimized cost | 2,055 | 1,590 |
| Required maximum | 3,000 | 2,500 |
| Public tickets passing | 4/4 | 4/4 |

## Key Engineering Ideas

The main ideas applied throughout this assignment were:

1. **Right tool for the right task:** Use deterministic Python logic for keyword extraction, search, ranking, and structural validation.
2. **LLM calls should provide value:** Reserve model calls for tasks that genuinely benefit from language understanding and generation.
3. **Context minimization:** Send only the relevant ticket information, order facts, and selected knowledge-base articles.
4. **Prompt optimization:** Remove unnecessary reasoning instructions, repeated context, and verbose prompts.
5. **Structured output:** Ask the model to return concise JSON containing the required fields.
6. **Deterministic processing:** Use reproducible algorithms for triage, retrieval, and validation wherever appropriate.

---

# Testing and Validation

The optimized implementations were tested using the public test suites.

### Question 1

```powershell
pytest -q tests/test_question1.py -k "not baseline_cost_is_high"
```

Result:

```text
2 passed, 1 deselected
```

### Question 2

```powershell
pytest -q tests/test_question2.py -k "not baseline_cost_is_high"
```

Result:

```text
2 passed, 1 deselected
```

### Additional validation

```powershell
git diff --check
```

Result: No whitespace errors.

The baseline-cost assertions were excluded from these optimized correctness runs because they check that the original baseline implementation has a high cost, which is no longer true after optimization. The original tests were not modified.

---

# Final Conclusion

Both questions were optimized successfully while preserving the expected public-ticket outputs.

The most important improvement in Question 1 was reducing unnecessary prompt and output tokens.

The most important improvement in Question 2 was redesigning the pipeline so that deterministic operations no longer require separate LLM calls.

The final result demonstrates how thoughtful prompt engineering, context management, deterministic algorithms, and selective LLM usage can substantially reduce inference costs without sacrificing the required public-test behavior.

**The central principle of this optimization:**

> Don't use an LLM for every operation. Use an LLM where language intelligence is valuable, and use deterministic code where algorithms are sufficient.