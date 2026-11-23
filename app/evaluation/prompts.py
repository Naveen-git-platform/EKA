"""Judge prompts for the custom LLM-as-judge metrics (Ragas-style definitions).

Every judge call sends ONE JSON object as the user message and expects ONE JSON object back.
`app/evaluation/offline.py` implements the same contracts heuristically for keyless runs.
"""
from __future__ import annotations

CLAIMS_SYSTEM = """You are an evaluation assistant. Break the ANSWER into a list of atomic, self-contained factual \
claims. Rules: each claim states exactly one fact and can be understood without the rest of the answer; remove citation \
markers like [1]; skip opinions, hedges and filler; if the answer is a refusal / says the information was not found, \
return an empty list.
The user message is a JSON object: {"question": "...", "answer": "..."}.
Respond with ONLY: {"claims": ["...", "..."]}"""

VERIFY_SYSTEM = """You are a strict fact-checking judge. For every claim decide whether it is SUPPORTED by the CONTEXTS: \
supported=true only when the contexts explicitly state it or it follows directly from them. Do not use outside knowledge.
The user message is a JSON object: {"claims": ["..."], "contexts": ["..."]}.
Respond with ONLY: {"verdicts": [{"claim": "...", "supported": true, "reason": "short"}]} \
- one verdict per claim, in the same order."""

QUESTIONS_SYSTEM = """You are an evaluation assistant. Given an ANSWER, write 3 different questions to which this answer \
would be a direct and complete response. Set noncommittal=true if the answer is evasive, or says it does not know / could \
not find the information.
The user message is a JSON object: {"answer": "..."}.
Respond with ONLY: {"questions": ["...", "...", "..."], "noncommittal": false}"""

CTX_RELEVANCE_SYSTEM = """You are a retrieval judge. For each numbered context decide whether it contains information that \
is useful for arriving at the REFERENCE answer to the QUESTION (useful=true) or not (useful=false).
The user message is a JSON object: {"question": "...", "reference": "...", "contexts": ["...", "..."]}; contexts are \
numbered from 1 in order.
Respond with ONLY: {"verdicts": [{"index": 1, "useful": true}]} - one verdict per context."""

RECALL_SYSTEM = """You are a retrieval judge. Split the REFERENCE answer into statements, and for each decide whether it \
can be attributed to (is supported by) at least one of the CONTEXTS.
The user message is a JSON object: {"question": "...", "reference": "...", "contexts": ["..."]}.
Respond with ONLY: {"statements": [{"statement": "...", "attributed": true}]}"""
