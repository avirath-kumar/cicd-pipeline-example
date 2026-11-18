"""Shared eval setup: a fixed judge, and the threshold config CI gates on."""

import json
import os

from agents.simple_text2sql import build_llm

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL") or "custom/gpt-5.6-luna-prod-gateway"


def build_judge_llm():
    """Judge pinned apart from ``LLM_MODEL``, so a model upgrade can't regrade itself."""
    # Luna is a reasoning model and rejects temperature.
    return build_llm(model=JUDGE_MODEL, temperature="none")


def write_eval_config(experiment_name: str, criteria: dict[str, str]) -> str:
    """Write ``evaluation_config__<experiment>.json`` and return its filename.

    ``criteria`` maps a feedback key to a threshold expression such as ``">=0.8"``.
    """
    safe_name = experiment_name.replace(":", "-").replace("/", "-")
    config_filename = f"evaluation_config__{safe_name}.json"
    config = {"experiment_name": experiment_name, "criteria": criteria}
    with open(config_filename, "w") as f:
        json.dump(config, f)
    return config_filename
