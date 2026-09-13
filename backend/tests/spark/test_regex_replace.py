import pytest

from processing.errors import ColumnNotFoundError, InvalidPatternError
from processing.schema import MATCHED_COLUMN
from processing.transforms.regex_replace import escape_replacement, regex_replace
from tests.spark.conftest import EMAIL_PATTERN


def test_replaces_matches_only_in_target_columns(spark):
    df = spark.createDataFrame(
        [("a@x.com", "b@y.org", "note a@x.com")], ["Email", "Backup", "Notes"]
    )

    row = regex_replace(df, ["Email", "Backup"], EMAIL_PATTERN, "REDACTED").first()

    assert (row["Email"], row["Backup"], row["Notes"]) == ("REDACTED", "REDACTED", "note a@x.com")
    assert row[MATCHED_COLUMN] is True


def test_partial_matches_replace_only_the_matched_text(spark):
    df = spark.createDataFrame([("Contact a@x.com today",)], ["Notes"])

    row = regex_replace(df, ["Notes"], EMAIL_PATTERN, "[email]").first()

    assert row["Notes"] == "Contact [email] today"


def test_unmatched_and_null_values(spark):
    df = spark.createDataFrame([("no email here",), (None,)], "Email string")

    rows = regex_replace(df, ["Email"], EMAIL_PATTERN, "REDACTED").collect()

    assert [(r["Email"], r[MATCHED_COLUMN]) for r in rows] == [
        ("no email here", False),
        (None, False),
    ]


@pytest.mark.parametrize("replacement", ["$1 cost", "C:\\temp\\", "$0\\$"])
def test_replacement_special_characters_are_literal(spark, replacement):
    df = spark.createDataFrame([("price",)], ["Value"])

    row = regex_replace(df, ["Value"], "price", replacement).first()

    assert row["Value"] == replacement


def test_unicode_outside_matches_is_preserved(spark):
    df = spark.createDataFrame([("Zoë Müller → zoe@example.com",)], ["Text"])

    row = regex_replace(df, ["Text"], EMAIL_PATTERN, "✉").first()

    assert row["Text"] == "Zoë Müller → ✉"


def test_column_names_with_spaces_and_dots(spark):
    df = spark.createDataFrame([("a@x.com", "b@y.org")], ["Email Address", "contact.email"])

    row = regex_replace(df, ["Email Address", "contact.email"], EMAIL_PATTERN, "R").first()

    assert (row["Email Address"], row["contact.email"]) == ("R", "R")


def test_column_order_is_preserved_and_duplicates_applied_once(spark):
    df = spark.createDataFrame([("1", "a")], ["ID", "Letter"])

    out = regex_replace(df, ["Letter", "Letter"], "a", "aa")

    assert out.columns == ["ID", "Letter", MATCHED_COLUMN]
    assert out.first()["Letter"] == "aa"


def test_missing_column_raises(spark):
    df = spark.createDataFrame([("x",)], ["Email"])

    with pytest.raises(ColumnNotFoundError, match="Phone"):
        regex_replace(df, ["Email", "Phone"], "x", "y")


def test_python_only_syntax_is_rejected_by_java_engine(spark):
    df = spark.createDataFrame([("x",)], ["Email"])

    with pytest.raises(InvalidPatternError, match="Java regex"):
        regex_replace(df, ["Email"], r"(?P<user>\w+)", "y")


def test_escape_replacement():
    assert escape_replacement("a$b\\c") == "a\\$b\\\\c"
