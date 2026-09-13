import pytest

from apps.llm.schemas import RegexSuggestion

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


def make_suggestion(**overrides) -> RegexSuggestion:
    fields = {
        "feasible": True,
        "pattern": EMAIL_PATTERN,
        "case_insensitive": False,
        "multiline": False,
        "dotall": False,
        "explanation": "Matches email addresses.",
        **overrides,
    }
    return RegexSuggestion(**fields)


class FakeGenerator:
    def __init__(self, suggestion: RegexSuggestion) -> None:
        self.suggestion = suggestion
        self.descriptions: list[str] = []

    def generate(self, description: str) -> RegexSuggestion:
        self.descriptions.append(description)
        return self.suggestion


@pytest.fixture
def fake_generator(monkeypatch):
    """Install a fake generator; set `.suggestion` to control what it returns."""
    from apps.llm import service

    generator = FakeGenerator(make_suggestion())
    monkeypatch.setattr(service, "get_regex_generator", lambda: generator)
    return generator
