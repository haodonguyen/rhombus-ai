from pydantic import BaseModel, Field


class RegexSuggestion(BaseModel):
    """Structured output requested from the model (enforced with a JSON schema)."""

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
