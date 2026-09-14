"""Mask personal data in the columns a classification marked as containing it.

Wholly personal values (identifiers, addresses, other personal data) are replaced outright,
and names are reduced to initials. Emails, phone numbers and card numbers are masked wherever
they appear in the text, keeping just enough to recognise the value: the first letter and
domain of an email, the last four digits of a number. The masks are fixed, tested Spark
expressions; the LLM only decides which columns hold which kinds of data.
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from processing.specs import PiiMaskingSpec, PiiType
from processing.transforms.columns import require_columns, rewrite_columns

REDACTED = "[REDACTED]"

CARD_PATTERN = r"\b(?:\d[ -]?){12,15}(\d{4})\b"
PHONE_PATTERN = r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?(\d{4})\b"
EMAIL_PATTERN = r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
NAME_PATTERN = r"(\p{L})[\p{L}'’-]*"

# Applied in this order: card numbers first, so their digits are not taken for a phone.
IN_TEXT_MASKS = (
    (PiiType.CREDIT_CARD, CARD_PATTERN, "**** **** **** $1"),
    (PiiType.PHONE, PHONE_PATTERN, "***-***-$1"),
    (PiiType.EMAIL, EMAIL_PATTERN, "$1***$2"),
)
WHOLE_VALUE_TYPES = frozenset({PiiType.IDENTIFIER, PiiType.ADDRESS, PiiType.OTHER})


def mask_pii(df: DataFrame, spec: PiiMaskingSpec) -> DataFrame:
    """Mask the spec's columns. Adds MATCHED_COLUMN, true when any value was masked."""
    targets = require_columns(df, list(spec.columns))
    return rewrite_columns(df, targets, lambda name, value: _mask(value, spec.columns[name]))


def _mask(value: Column, types: frozenset[PiiType]) -> tuple[Column, Column]:
    if types & WHOLE_VALUE_TYPES:
        masked = F.when(value.isNull(), value).otherwise(F.lit(REDACTED))
    elif PiiType.PERSON_NAME in types:
        masked = F.regexp_replace(value, NAME_PATTERN, "$1.")
    else:
        masked = value
        for pii_type, pattern, replacement in IN_TEXT_MASKS:
            if pii_type in types:
                masked = F.regexp_replace(masked, pattern, replacement)
    return masked, masked != value
