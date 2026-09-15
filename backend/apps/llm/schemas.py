"""Structured outputs requested from the model. Each is enforced with its JSON schema.

List fields carry a maximum length. Ollama turns it into `maxItems` in the decoding grammar,
so a small model that starts repeating a list item has to close the list instead of looping.
"""

from typing import Literal, get_args

from pydantic import BaseModel, Field

from processing.specs import MAX_DATE_FORMATS, MAX_RULES


class RegexSuggestion(BaseModel):
    """Output for find and replace: one pattern for the user's description."""

    feasible: bool = Field(
        description="False when the description cannot be expressed as a regular expression."
    )
    pattern: str = Field(
        description=(
            "The regular expression, without delimiters or inline flags. Empty when not feasible."
        )
    )
    case_insensitive: bool = Field(description="Match letters regardless of case.")
    multiline: bool = Field(description="Make ^ and $ match at line breaks within a cell.")
    dotall: bool = Field(description="Make . also match line breaks.")
    explanation: str = Field(
        description=(
            "One or two plain sentences for the user: what the pattern matches, or why the "
            "description is not feasible."
        )
    )


class RewriteRuleSuggestion(BaseModel):
    pattern: str = Field(description="Java regular expression; capture the parts to keep.")
    replacement: str = Field(description="Replacement text; refer to captured parts as $1, $2.")


class NormalizationSuggestion(BaseModel):
    """Output for format normalization: date formats, or rewrite rules for other text."""

    feasible: bool = Field(description="False when reformatting cannot achieve the request.")
    kind: Literal["date", "rules"] = Field(description='"date" for dates, "rules" otherwise.')
    input_formats: list[str] = Field(
        description='For "date": one Java date pattern per date format seen in the samples.',
        max_length=MAX_DATE_FORMATS,
    )
    output_format: str = Field(description='For "date": Java date pattern of the target format.')
    rules: list[RewriteRuleSuggestion] = Field(
        description='For "rules": rewrite rules; the first rule that matches a value applies.',
        max_length=MAX_RULES,
    )
    explanation: str = Field(description="One or two plain sentences for the user.")


PiiTypeName = Literal[
    "none", "email", "phone", "person_name", "credit_card", "identifier", "address", "other"
]


class ColumnPiiSuggestion(BaseModel):
    column: str = Field(description="Column name exactly as given.")
    pii_types: list[PiiTypeName] = Field(
        description='Kinds of personal data in the column, or ["none"].',
        max_length=len(get_args(PiiTypeName)),
    )


class PiiClassificationSuggestion(BaseModel):
    """Output for PII masking: the kinds of personal data in each column."""

    columns: list[ColumnPiiSuggestion]
    explanation: str = Field(description="One short sentence for the user.")
