import pytest

from processing.errors import ColumnNotFoundError, InvalidSpecError
from processing.schema import MATCHED_COLUMN
from processing.specs import DateNormalization, RewriteRule, RuleNormalization
from processing.transforms.normalize import normalize_format

ISO_DATES = DateNormalization(("yyyy-MM-dd", "dd/MM/yyyy", "MMM d, yyyy"), "yyyy-MM-dd")
PHONE_RULES = RuleNormalization(
    (RewriteRule(r"^(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})$", "$1-$2-$3"),)
)


def values(df, column):
    return [(row[column], row[MATCHED_COLUMN]) for row in df.collect()]


def test_dates_in_mixed_formats_become_one_format(spark):
    df = spark.createDataFrame(
        [("2020-04-24",), ("25/10/2018",), ("Nov 22, 2021",), (" Jan 2, 2024 ",)], ["SignupDate"]
    )

    result = normalize_format(df, ["SignupDate"], ISO_DATES)

    assert values(result, "SignupDate") == [
        ("2020-04-24", True),
        ("2018-10-25", True),
        ("2021-11-22", True),
        ("2024-01-02", True),
    ]


def test_unrecognised_invalid_and_null_dates_are_left_unchanged(spark):
    df = spark.createDataFrame([("next tuesday",), (None,), ("2020-13-45",)], "SignupDate string")

    result = normalize_format(df, ["SignupDate"], ISO_DATES)

    assert values(result, "SignupDate") == [
        ("next tuesday", False),
        (None, False),
        ("2020-13-45", False),
    ]


def test_output_format_can_be_any_date_pattern(spark):
    df = spark.createDataFrame([("2020-04-24",)], ["D"])

    result = normalize_format(df, ["D"], DateNormalization(("yyyy-MM-dd",), "dd MMM yyyy"))

    assert result.first()["D"] == "24 Apr 2020"


def test_rules_rewrite_matching_values_with_group_references(spark):
    df = spark.createDataFrame(
        [("+1 (892) 958-9935",), ("816.227.4257",), ("not a phone",)], ["Phone"]
    )

    result = normalize_format(df, ["Phone"], PHONE_RULES)

    assert values(result, "Phone") == [
        ("892-958-9935", True),
        ("816-227-4257", True),
        ("not a phone", False),
    ]


def test_first_matching_rule_wins(spark):
    spec = RuleNormalization(
        (RewriteRule(r"^(\d+)$", "number $1"), RewriteRule(r"^(\w+)$", "word $1"))
    )
    df = spark.createDataFrame([("42",), ("abc",)], ["V"])

    result = normalize_format(df, ["V"], spec)

    assert [row["V"] for row in result.collect()] == ["number 42", "word abc"]


def test_invalid_java_date_format_is_rejected_before_reading_data(spark):
    df = spark.createDataFrame([("2020-04-24",)], ["D"])

    with pytest.raises(InvalidSpecError, match="not valid"):
        normalize_format(df, ["D"], DateNormalization(("yyyy-MM-dd",), "{bad}"))


def test_missing_column_raises(spark):
    df = spark.createDataFrame([("2020-04-24",)], ["D"])

    with pytest.raises(ColumnNotFoundError, match="SignupDate"):
        normalize_format(df, ["SignupDate"], ISO_DATES)
