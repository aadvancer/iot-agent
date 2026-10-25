"""Metrics shared by the proposed agent and comparison baselines."""
from collections import Counter


def _repeated_questions(row):
    asked = []
    for event in row.get("log", []):
        if event.get("tool") != "ask_user":
            continue
        question = event.get("args", {}).get("question", "")
        normalized = " ".join(question.casefold().split())
        if normalized:
            asked.append(normalized)
    counts = Counter(asked)
    return sum(count - 1 for count in counts.values()), len(asked)


def calculate_metrics(rows):
    """Calculate case-level accuracy and support-interaction metrics."""
    if not rows:
        raise ValueError("Cannot calculate evaluation metrics for an empty result set")

    n = len(rows)
    correct_causes = sum(
        row.get("pred_root_cause") == row.get("gt_root_cause") for row in rows
    )
    correct_tiers = sum(row.get("pred_tier") == row.get("gt_tier") for row in rows)
    repeated = total_questions = 0
    for row in rows:
        duplicate_count, question_count = _repeated_questions(row)
        repeated += duplicate_count
        total_questions += question_count
    scores = [
        row["usability_score"] for row in rows
        if isinstance(row.get("usability_score"), (int, float))
        and not isinstance(row.get("usability_score"), bool)
    ]

    return {
        "case_count": n,
        "diagnosis_success_rate": correct_causes / n,
        "average_interaction_rounds": sum(row.get("user_turns", 0) for row in rows) / n,
        "redundant_inquiry_rate": repeated / total_questions if total_questions else 0.0,
        "fault_classification_accuracy": correct_tiers / n,
        "support_usability_score": sum(scores) / len(scores) if scores else None,
        "usability_scored_cases": len(scores),
    }


def judge_usability(row):
    """Obtain an explicitly model-judged 1-5 usability score for one case."""
    import config
    import llm

    prompt = f"""Rate the usability of this technical-support response on a 1-5 scale.
Judge only clarity, politeness, actionability, and whether the response avoids
claiming checks or fixes that are not shown as completed. Do not reward a correct
root-cause label by itself. Return JSON: {{"score": integer, "reason": string}}.

Customer complaint: {row.get('complaint', '')}
Support response: {row.get('output', {})}"""
    result = llm.chat_json(
        [{"role": "user", "content": prompt}],
        model=config.JUDGE_MODEL,
        role="judge",
    )
    score = result.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        raise ValueError(f"Usability judge returned invalid score: {score!r}")
    return {"score": score, "reason": result.get("reason", "")}
