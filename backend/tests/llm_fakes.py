"""Fake LLM and suggestion builders shared by the LLM, job and Spark tests."""

from pydantic import BaseModel

from apps.llm.schemas import (
    ColumnPiiSuggestion,
    NormalizationSuggestion,
    PiiClassificationSuggestion,
    RegexSuggestion,
)

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
DATE_FORMATS = ["yyyy-MM-dd", "dd/MM/yyyy", "MMM d, yyyy"]


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


def make_date_normalization(**overrides) -> NormalizationSuggestion:
    fields = {
        "feasible": True,
        "kind": "date",
        "input_formats": DATE_FORMATS,
        "output_format": "yyyy-MM-dd",
        "rules": [],
        "explanation": "Writes dates as YYYY-MM-DD.",
        **overrides,
    }
    return NormalizationSuggestion(**fields)


def make_pii_classification(
    columns: dict[str, list[str]], explanation: str = "Found personal data."
) -> PiiClassificationSuggestion:
    return PiiClassificationSuggestion(
        columns=[
            ColumnPiiSuggestion(column=name, pii_types=types) for name, types in columns.items()
        ],
        explanation=explanation,
    )


class FakeLLM:
    """Returns the configured suggestion for each output type and records every call."""

    def __init__(self) -> None:
        self.responses: dict[type[BaseModel], BaseModel] = {}
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    def respond_with(self, suggestion: BaseModel) -> None:
        self.responses[type(suggestion)] = suggestion

    def complete(self, system: str, user: str, output_type: type[BaseModel]) -> BaseModel:
        self.calls.append((system, user, output_type))
        return self.responses[output_type]
