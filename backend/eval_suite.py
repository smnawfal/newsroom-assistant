"""
eval_suite.py — Automated Newsroom Evaluation Benchmark.

Evaluates search retrieval recall, citation accuracy, supporting excerpt/link
completeness, multi-outlet framing representation, and insufficient-evidence
guardrails against known ground-truth articles in the local archive.
"""

from pathlib import Path
from typing import Optional

import llm
import search as search_module

BENCHMARK_CASES = [
    {
        "id": "eval_nepal_rescue",
        "category": "Single-Event Factual Lookup",
        "question": "What happened in the Nepal hydropower workers rescue operation and what is the flooding death toll?",
        "expected_sources": ["BBC World"],
        "expected_article_ids": [1],
        "expected_facts": ["explosives", "939"],
        "expect_insufficient_evidence": False,
    },
    {
        "id": "eval_us_iran_strikes",
        "category": "Cross-Outlet Geopolitics",
        "question": "What are the latest reports on US and Iran trading military strikes?",
        "expected_sources": ["BBC World"],
        "expected_article_ids": [2],
        "expected_facts": ["iran", "strikes"],
        "expect_insufficient_evidence": False,
    },
    {
        "id": "eval_israel_west_bank",
        "category": "Framing & Internal Disagreement",
        "question": "What are former Israeli generals and intelligence officials saying about West Bank settlers?",
        "expected_sources": ["NYT World"],
        "expected_article_ids": [28],
        "expected_facts": ["generals", "west bank", "settlers"],
        "expect_insufficient_evidence": False,
    },
    {
        "id": "eval_india_kerala_politics",
        "category": "National Political Coverage",
        "question": "What accusation did Pinarayi make regarding the Taliparamba MLA and CPI(M) leadership?",
        "expected_sources": ["The Hindu"],
        "expected_article_ids": [111],
        "expected_facts": ["pinarayi", "cpi(m)"],
        "expect_insufficient_evidence": False,
    },
    {
        "id": "eval_india_factory_blast",
        "category": "Breaking Incident Verification",
        "question": "How many children were killed in the firecracker factory blast in India?",
        "expected_sources": ["Al Jazeera"],
        "expected_article_ids": [86],
        "expected_facts": ["8", "children", "firecracker"],
        "expect_insufficient_evidence": False,
    },
    {
        "id": "eval_guardrail_unanswerable",
        "category": "Insufficient-Evidence Guardrail",
        "question": "What did the Central Bank of Mars announce about lunar thorium tariffs in Antarctica?",
        "expected_sources": [],
        "expected_article_ids": [],
        "expected_facts": ["insufficient evidence"],
        "expect_insufficient_evidence": True,
    },
]


def run_evaluation(db_path: Optional[Path] = None) -> dict:
    """
    Run all benchmark cases and compute pass/fail metrics plus failure diagnostics.
    """
    results = []
    passed_count = 0
    failures_tracked = []

    for case in BENCHMARK_CASES:
        q = case["question"]
        matches = search_module.search(q, limit=8, db_path=db_path)
        qa_res = llm.answer_query(q, matches)

        answer_text = qa_res.get("answer", "")
        insufficient = bool(qa_res.get("insufficient_evidence", False))
        citations = qa_res.get("citations", [])
        retrieved_ids = [c["id"] for c in citations]
        retrieved_sources = list(dict.fromkeys(c["source"] for c in citations))

        checks = {}
        if case["expect_insufficient_evidence"]:
            checks["guardrail_triggered"] = insufficient is True
            checks["no_false_citations"] = len(citations) == 0
            checks["explicit_refusal_message"] = "insufficient evidence" in answer_text.lower()
        else:
            checks["sufficient_evidence_detected"] = insufficient is False
            checks["expected_article_retrieved"] = any(
                eid in retrieved_ids for eid in case["expected_article_ids"]
            )
            checks["expected_source_retrieved"] = any(
                es in retrieved_sources for es in case["expected_sources"]
            )
            checks["links_and_excerpts_present"] = bool(citations) and all(
                bool(c.get("url")) and bool(c.get("excerpt")) for c in citations
            )
            combined_evidence = (
                answer_text + " " + " ".join(c.get("excerpt", "") for c in citations)
            ).lower()
            checks["expected_facts_covered"] = all(
                fact.lower() in combined_evidence for fact in case["expected_facts"]
            )
            checks["inline_source_citation"] = any(
                es.lower() in answer_text.lower() for es in case["expected_sources"]
            )

        case_passed = all(checks.values())
        if case_passed:
            passed_count += 1
        else:
            failed_keys = [k for k, v in checks.items() if not v]
            failures_tracked.append(
                {
                    "case_id": case["id"],
                    "failed_checks": failed_keys,
                    "retrieved_ids": retrieved_ids,
                }
            )

        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": q,
                "passed": case_passed,
                "checks": checks,
                "expected_sources": case["expected_sources"],
                "expected_article_ids": case["expected_article_ids"],
                "retrieved_article_ids": retrieved_ids,
                "retrieved_sources": retrieved_sources,
                "insufficient_evidence": insufficient,
                "answer_preview": answer_text[:360] + ("…" if len(answer_text) > 360 else ""),
                "citation_count": len(citations),
                "sample_citation": citations[0] if citations else None,
            }
        )

    total = len(BENCHMARK_CASES)
    return {
        "total_cases": total,
        "passed_cases": passed_count,
        "failed_cases": total - passed_count,
        "pass_rate_pct": round((passed_count / total) * 100, 1) if total else 0.0,
        "llm_mode": "Claude Sonnet 4.6 API" if llm.is_api_key_configured() else "Deterministic Extractive Verification Mode",
        "failures_tracked": failures_tracked,
        "cases": results,
    }


if __name__ == "__main__":
    summary = run_evaluation()
    print(f"Evaluation Pass Rate: {summary['passed_cases']}/{summary['total_cases']} ({summary['pass_rate_pct']}%)")
    for c in summary["cases"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['id']} ({c['category']}) -> retrieved IDs: {c['retrieved_article_ids']}")
