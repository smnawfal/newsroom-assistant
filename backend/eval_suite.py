"""
eval_suite.py — Automated Newsroom Evaluation Benchmark.

Evaluates search retrieval recall, citation accuracy, supporting excerpt/link
completeness, multi-outlet framing representation, and insufficient-evidence
guardrails against known ground-truth articles in the local archive.
"""

import json
from pathlib import Path
from typing import Optional

from config import EVALUATION_CASES_PATH
import llm
import search as search_module

try:
    BENCHMARK_CASES = json.loads(EVALUATION_CASES_PATH.read_text(encoding="utf-8"))
except FileNotFoundError as exc:
    raise RuntimeError(f"Evaluation cases file not found: {EVALUATION_CASES_PATH}") from exc
except json.JSONDecodeError as exc:
    raise RuntimeError(f"Invalid evaluation cases JSON: {exc}") from exc

if not isinstance(BENCHMARK_CASES, list) or not all(
    isinstance(case, dict)
    and all(key in case for key in ("id", "category", "question", "expected_sources", "expected_article_ids", "expected_facts", "expect_insufficient_evidence"))
    for case in BENCHMARK_CASES
):
    raise RuntimeError("Evaluation cases must be a list of complete case objects")


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
        "llm_mode": f"{llm.MODE} API" if llm.is_api_key_configured() else "Deterministic Extractive Verification Mode",
        "failures_tracked": failures_tracked,
        "cases": results,
    }


if __name__ == "__main__":
    summary = run_evaluation()
    print(f"Evaluation Pass Rate: {summary['passed_cases']}/{summary['total_cases']} ({summary['pass_rate_pct']}%)")
    for c in summary["cases"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['id']} ({c['category']}) -> retrieved IDs: {c['retrieved_article_ids']}")
