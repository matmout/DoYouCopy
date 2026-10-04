from doyoucopy.core.models import DEFAULT_MODEL_KEY, MODELS, get_model


def test_registry():
    assert MODELS["turbo"].model_name == "large-v3-turbo"
    assert MODELS["precise"].model_name == "large-v3"
    assert DEFAULT_MODEL_KEY == "turbo"


def test_unknown_key_falls_back_to_default():
    assert get_model("nope") is MODELS[DEFAULT_MODEL_KEY]
