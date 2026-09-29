"""Pure metric computation from evaluate.py (PROJECT_PLAN.md Phase 3.7 /
10.1). No database needed: QueryResult rows are constructed directly."""

from __future__ import annotations

from backend.app.services.screening.evaluate import QueryResult, ThresholdMetrics, compute_metrics


def test_true_match_above_threshold_on_correct_entity_is_a_true_positive():
    results = [QueryResult(label="true_match", true_entity_uid=1, top_entity_uid=1, top_score=95)]
    metrics = compute_metrics(results, [90])[0]
    assert metrics.true_positives == 1
    assert metrics.false_negatives == 0
    assert metrics.recall == 1.0


def test_true_match_on_wrong_entity_is_a_false_negative_even_if_alerted():
    results = [QueryResult(label="true_match", true_entity_uid=1, top_entity_uid=2, top_score=95)]
    metrics = compute_metrics(results, [90])[0]
    assert metrics.false_negatives == 1
    assert metrics.true_positives == 0


def test_true_match_below_threshold_is_a_false_negative():
    results = [QueryResult(label="true_match", true_entity_uid=1, top_entity_uid=1, top_score=50)]
    metrics = compute_metrics(results, [90])[0]
    assert metrics.false_negatives == 1


def test_hard_negative_above_threshold_is_a_false_positive():
    results = [QueryResult(label="hard_negative", true_entity_uid=None, top_entity_uid=5, top_score=95)]
    metrics = compute_metrics(results, [90])[0]
    assert metrics.false_positives == 1
    assert metrics.true_negatives == 0


def test_clean_below_threshold_is_a_true_negative():
    results = [QueryResult(label="clean", true_entity_uid=None, top_entity_uid=None, top_score=10)]
    metrics = compute_metrics(results, [90])[0]
    assert metrics.true_negatives == 1


def test_metrics_are_computed_independently_per_threshold():
    results = [QueryResult(label="true_match", true_entity_uid=1, top_entity_uid=1, top_score=75)]
    metrics = {m.threshold: m for m in compute_metrics(results, [50, 90])}
    assert metrics[50].true_positives == 1
    assert metrics[90].false_negatives == 1


def test_recall_precision_f1_are_zero_when_denominator_is_zero():
    metrics = ThresholdMetrics(threshold=90, true_positives=0, false_positives=0, false_negatives=0, true_negatives=5)
    assert metrics.recall == 0.0
    assert metrics.precision == 0.0
    assert metrics.f1 == 0.0
    assert metrics.false_positive_rate == 0.0


def test_false_positive_rate_formula():
    metrics = ThresholdMetrics(threshold=90, true_positives=0, false_positives=3, false_negatives=0, true_negatives=7)
    assert metrics.false_positive_rate == 0.3
