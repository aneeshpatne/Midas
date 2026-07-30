from midas.deepagents.model import get_main_model


def test_model_profile_uses_configurable_cost_context(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_CONTEXT_BUDGET_TOKENS", "64000")
    model = get_main_model()

    assert model.profile["max_input_tokens"] == 64_000
    assert model.profile["provider_max_input_tokens"] >= 64_000


def test_invalid_cost_context_uses_safe_default(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_CONTEXT_BUDGET_TOKENS", "invalid")
    model = get_main_model()

    assert model.profile["max_input_tokens"] == 75_000
