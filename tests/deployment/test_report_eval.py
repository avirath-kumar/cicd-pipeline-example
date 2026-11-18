"""The evaluation report must fail CI when a threshold is missed or never scored."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import _load

report_eval = _load("report_eval")

pytestmark = pytest.mark.deployment


def _client_with_scores(scores_by_key: dict) -> MagicMock:
    client = MagicMock()
    client.list_runs.return_value = [SimpleNamespace(id="run-1")]
    client.list_feedback.return_value = [
        SimpleNamespace(key=key, score=score)
        for key, scores in scores_by_key.items()
        for score in scores
    ]
    return client


def _process(tmp_path, criteria: dict, scores_by_key: dict) -> dict:
    config_path = tmp_path / "evaluation_config__exp.json"
    config_path.write_text(json.dumps({"experiment_name": "exp", "criteria": criteria}))
    return report_eval.process_config(
        str(config_path), _client_with_scores(scores_by_key)
    )


def test_passes_when_every_threshold_is_met(tmp_path):
    result = _process(tmp_path, {"correctness": ">=0.8"}, {"correctness": [1, 1]})

    assert report_eval.failed_experiments([result]) == []


def test_fails_when_a_threshold_is_missed(tmp_path):
    result = _process(tmp_path, {"correctness": ">=0.8"}, {"correctness": [1, 0]})

    assert report_eval.failed_experiments([result]) == ["exp"]


def test_fails_when_a_thresholded_metric_has_no_scores(tmp_path):
    # An erroring judge writes no feedback; that must not read as a pass.
    result = _process(tmp_path, {"correctness": ">=0.8"}, {})

    assert result["num_failed"] == 1
    assert report_eval.failed_experiments([result]) == ["exp"]
