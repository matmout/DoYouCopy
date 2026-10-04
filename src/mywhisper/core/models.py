from __future__ import annotations

from mywhisper.core.types import ModelSpec

MODELS: dict[str, ModelSpec] = {
    spec.key: spec
    for spec in (
        ModelSpec(
            key="turbo",
            label="large-v3-turbo (rapide)",
            model_name="large-v3-turbo",
            beam_size=1,
            condition_on_previous_text=False,
        ),
        ModelSpec(
            key="precise",
            label="large-v3 (précis)",
            model_name="large-v3",
            beam_size=5,
            condition_on_previous_text=True,
        ),
    )
}

DEFAULT_MODEL_KEY = "turbo"


def get_model(key: str) -> ModelSpec:
    return MODELS.get(key, MODELS[DEFAULT_MODEL_KEY])
