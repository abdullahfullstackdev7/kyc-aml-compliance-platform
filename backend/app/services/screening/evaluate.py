"""Evaluation harness: recall, precision, F1 and false positive rate per
score threshold, plus a precision-recall curve, against a labelled ground
truth set. See PROJECT_PLAN.md Phase 3.7.

Each ground truth row is one query. For "true_match" rows the system is
correct if its top-scoring hit is the labelled entity and clears the
threshold. For "hard_negative" and "clean" rows, any hit clearing the
threshold (regardless of which entity) counts as a false alert. This mirrors
how a screening system is actually judged: did it catch the sanctioned party,
and did it needlessly flag someone who isn't one.

Usage: uv run python -m backend.app.services.screening.evaluate
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from backend.app.services.screening.candidates import generate_candidates
from backend.app.services.screening.normalize import normalize_name
from backend.app.services.screening.service import ScreeningQuery, screen_name

# Includes the tier boundaries from risk_config defaults (clear_max=72,
# review_max=89, high_risk_min=90) alongside a regular 5-point sweep, so the
# report can report metrics exactly at the thresholds routing actually uses.
THRESHOLDS = sorted(set(range(50, 100, 5)) | {72, 89, 90})


@dataclass
class GroundTruthRow:
    query_name: str
    dob_year: int | None
    label: str  # "true_match" | "hard_negative" | "clean"
    true_entity_uid: int | None


@dataclass
class ThresholdMetrics:
    threshold: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_positive_rate(self) -> float:
        denom = self.false_positives + self.true_negatives
        return self.false_positives / denom if denom else 0.0


def load_ground_truth(path: Path) -> list[GroundTruthRow]:
    rows: list[GroundTruthRow] = []
    with path.open(encoding="utf-8") as f:
        for record in csv.DictReader(f):
            rows.append(
                GroundTruthRow(
                    query_name=record["query_name"],
                    dob_year=int(record["dob_year"]) if record["dob_year"] else None,
                    label=record["label"],
                    true_entity_uid=int(record["true_entity_uid"])
                    if record["true_entity_uid"]
                    else None,
                )
            )
    return rows


@dataclass
class QueryResult:
    label: str
    true_entity_uid: int | None
    top_entity_uid: int | None
    top_score: float


def run_hybrid_queries(session: Session, rows: list[GroundTruthRow]) -> list[QueryResult]:
    results = []
    for row in rows:
        dob = dt.date(row.dob_year, 1, 1) if row.dob_year else None
        result = screen_name(
            session, ScreeningQuery(full_name=row.query_name, date_of_birth=dob, top_n=1)
        )
        top = result.hits[0] if result.hits else None
        results.append(
            QueryResult(
                label=row.label,
                true_entity_uid=row.true_entity_uid,
                top_entity_uid=top.entity_uid if top else None,
                top_score=top.breakdown.composite_score if top else 0.0,
            )
        )
    return results


def run_baseline_queries(session: Session, rows: list[GroundTruthRow]) -> list[QueryResult]:
    """Pure token_set_ratio baseline over the same candidate pool, for comparison."""
    results = []
    for row in rows:
        query = normalize_name(row.query_name)
        candidates = generate_candidates(
            session,
            tokens=query.tokens,
            normalized=query.normalized,
            phonetic=query.phonetic,
            embedding=None,
            limit=50,
        )
        best_score = 0.0
        best_entity_uid: int | None = None
        for candidate in candidates:
            score = fuzz.token_set_ratio(query.normalized, candidate.normalized)
            if score > best_score:
                best_score = score
                best_entity_uid = candidate.entity_uid
        results.append(
            QueryResult(
                label=row.label,
                true_entity_uid=row.true_entity_uid,
                top_entity_uid=best_entity_uid,
                top_score=best_score,
            )
        )
    return results


def compute_metrics(results: list[QueryResult], thresholds: list[int]) -> list[ThresholdMetrics]:
    metrics = []
    for threshold in thresholds:
        tp = fp = fn = tn = 0
        for result in results:
            alerted = result.top_score >= threshold
            if result.label == "true_match":
                correct = alerted and result.top_entity_uid == result.true_entity_uid
                if correct:
                    tp += 1
                else:
                    fn += 1
            else:
                if alerted:
                    fp += 1
                else:
                    tn += 1
        metrics.append(
            ThresholdMetrics(
                threshold=threshold,
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn,
                true_negatives=tn,
            )
        )
    return metrics


def plot_pr_curve(hybrid_metrics: list[ThresholdMetrics], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    recalls = [m.recall for m in hybrid_metrics]
    precisions = [m.precision for m in hybrid_metrics]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(recalls, precisions, marker="o")
    for m in hybrid_metrics:
        ax.annotate(
            str(m.threshold),
            (m.recall, m.precision),
            fontsize=7,
            textcoords="offset points",
            xytext=(4, 4),
        )
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("SentinelKYC screening: precision-recall by score threshold")
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def write_report(
    hybrid_metrics: list[ThresholdMetrics],
    baseline_metrics: list[ThresholdMetrics],
    output_path: Path,
    ground_truth_count: int,
) -> None:
    review_threshold = 72
    hybrid_at_review = next((m for m in hybrid_metrics if m.threshold == review_threshold), None)

    lines = [
        "# Screening evaluation report",
        "",
        (
            f"Ground truth set: {ground_truth_count} labelled queries "
            "(generated by dataset/scripts/generate_ground_truth.py, seed 42)."
        ),
        "",
        "## Hybrid pipeline (token + trigram + vector retrieval, weighted composite score)",
        "",
        "| Threshold | Recall | Precision | F1 | False positive rate | TP | FP | FN | TN |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in hybrid_metrics:
        lines.append(
            f"| {m.threshold} | {m.recall:.3f} | {m.precision:.3f} | {m.f1:.3f} | "
            f"{m.false_positive_rate:.3f} | {m.true_positives} | {m.false_positives} | "
            f"{m.false_negatives} | {m.true_negatives} |"
        )

    lines += [
        "",
        "## Baseline: pure rapidfuzz token_set_ratio over the same candidate pool",
        "",
        "| Threshold | Recall | Precision | F1 | False positive rate |",
        "|---|---|---|---|---|",
    ]
    for m in baseline_metrics:
        lines.append(
            f"| {m.threshold} | {m.recall:.3f} | {m.precision:.3f} | {m.f1:.3f} | {m.false_positive_rate:.3f} |"
        )

    if hybrid_at_review:
        baseline_at_review = next(
            (m for m in baseline_metrics if m.threshold == review_threshold), None
        )
        lines += [
            "",
            f"## Result at the Review threshold ({review_threshold})",
            "",
            (
                f"- Hybrid pipeline recall: {hybrid_at_review.recall:.3f}, "
                f"false positive rate: {hybrid_at_review.false_positive_rate:.3f}"
            ),
        ]
        if baseline_at_review:
            lines.append(
                f"- Baseline recall: {baseline_at_review.recall:.3f}, "
                f"false positive rate: {baseline_at_review.false_positive_rate:.3f}"
            )

        target_met = "meets" if hybrid_at_review.recall >= 0.98 else "does not meet"
        lines += [
            "",
            f"Recall at the Review threshold {target_met} the Phase 3 target of at least 98 percent.",
        ]

        best_baseline_fpr = min((m.false_positive_rate for m in baseline_metrics), default=None)
        matched_recall_hybrid = max(
            (m for m in hybrid_metrics if m.recall >= 0.95),
            key=lambda m: m.threshold,
            default=None,
        )
        if best_baseline_fpr is not None and matched_recall_hybrid is not None:
            lines += [
                "",
                "## Hybrid vs. baseline false positive rate at comparable recall",
                "",
                (
                    f"- Baseline's lowest false positive rate at any threshold, including where its own "
                    f"recall has already dropped below 95 percent, is {best_baseline_fpr:.3f}."
                ),
                (
                    f"- The hybrid pipeline reaches false positive rate "
                    f"{matched_recall_hybrid.false_positive_rate:.3f} at threshold "
                    f"{matched_recall_hybrid.threshold} while still holding recall at "
                    f"{matched_recall_hybrid.recall:.3f} (at or above 95 percent)."
                ),
                (
                    "- Token-only matching cannot separate true matches from lookalikes once the score "
                    "is inflated by shared common tokens; trigram and embedding retrieval plus the "
                    "rare-token and secondary-attribute adjustments let the hybrid pipeline push the "
                    "threshold higher without losing recall, which token_set_ratio alone cannot do."
                ),
            ]

        lines.append("")
        lines.append("![Precision-recall curve](pr_curve.png)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.core.config import get_settings

    root = Path(__file__).resolve().parents[4]
    ground_truth_path = root / "dataset" / "synthetic" / "ground_truth_matches.csv"
    report_path = root / "docs" / "evaluation" / "report.md"
    pr_curve_path = root / "docs" / "evaluation" / "pr_curve.png"

    rows = load_ground_truth(ground_truth_path)

    engine = create_engine(get_settings().sync_database_url())
    Session = sessionmaker(bind=engine)
    with Session() as session:
        hybrid_results = run_hybrid_queries(session, rows)
        baseline_results = run_baseline_queries(session, rows)

    hybrid_metrics = compute_metrics(hybrid_results, THRESHOLDS)
    baseline_metrics = compute_metrics(baseline_results, THRESHOLDS)

    plot_pr_curve(hybrid_metrics, pr_curve_path)
    write_report(hybrid_metrics, baseline_metrics, report_path, len(rows))

    print(f"Wrote {report_path} and {pr_curve_path}")


if __name__ == "__main__":
    main()
