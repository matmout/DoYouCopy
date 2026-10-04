from __future__ import annotations

from mywhisper.core.types import ModelSpec

MODELS: dict[str, ModelSpec] = {
    spec.key: spec
    for spec in (
        ModelSpec(
            key="light",
            label="small (léger)",
            model_name="small",
            beam_size=5,
            condition_on_previous_text=True,
            size_gb=0.5,
            description="Pour les ordinateurs sans carte graphique : rapide sur processeur, moins précis.",
        ),
        ModelSpec(
            key="turbo",
            label="large-v3-turbo (rapide)",
            model_name="large-v3-turbo",
            beam_size=1,
            condition_on_previous_text=False,
            size_gb=1.6,
            description="Le meilleur compromis : presque aussi précis que large-v3, plusieurs fois plus rapide.",
        ),
        ModelSpec(
            key="precise",
            label="large-v3 (précis)",
            model_name="large-v3",
            beam_size=5,
            condition_on_previous_text=True,
            size_gb=3.1,
            description="La meilleure précision, et le seul modèle qui sait traduire vers l'anglais.",
        ),
    )
}

DEFAULT_MODEL_KEY = "turbo"


def get_model(key: str) -> ModelSpec:
    return MODELS.get(key, MODELS[DEFAULT_MODEL_KEY])
