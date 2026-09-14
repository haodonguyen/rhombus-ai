from processing.schema import MATCHED_COLUMN
from processing.specs import PiiMaskingSpec, PiiType
from processing.transforms.mask_pii import REDACTED, mask_pii


def spec(**columns: list[PiiType]) -> PiiMaskingSpec:
    return PiiMaskingSpec(columns={name: frozenset(types) for name, types in columns.items()})


def masked(spark, column, rows, types):
    df = spark.createDataFrame([(value,) for value in rows], f"`{column}` string")
    return [row[column] for row in mask_pii(df, spec(**{column: types})).collect()]


def test_emails_keep_their_first_letter_and_domain(spark):
    result = masked(
        spark,
        "Email",
        ["john.doe@example.com", "Contact backup at a_b@mail.co.uk today"],
        [PiiType.EMAIL],
    )

    assert result == ["j***@example.com", "Contact backup at a***@mail.co.uk today"]


def test_phone_numbers_keep_their_last_four_digits(spark):
    result = masked(
        spark, "Phone", ["+1 (892) 958-9935", "Call 816.227.4257", "552-818-5333"], [PiiType.PHONE]
    )

    assert result == ["***-***-9935", "Call ***-***-4257", "***-***-5333"]


def test_card_numbers_keep_their_last_four_digits(spark):
    result = masked(
        spark, "Card", ["4111 1111 1111 1234", "4111-1111-1111-1234"], [PiiType.CREDIT_CARD]
    )

    assert result == ["**** **** **** 1234", "**** **** **** 1234"]


def test_names_become_initials(spark):
    result = masked(spark, "Name", ["John Doe", "Zoë Müller"], [PiiType.PERSON_NAME])

    assert result == ["J. D.", "Z. M."]


def test_several_kinds_in_one_text_column(spark):
    result = masked(
        spark,
        "Notes",
        ["Call 816.227.4257 or mail jane@example.com"],
        [PiiType.PHONE, PiiType.EMAIL],
    )

    assert result == ["Call ***-***-4257 or mail j***@example.com"]


def test_whole_value_types_are_redacted_but_nulls_stay_null(spark):
    df = spark.createDataFrame([("P1234567",), (None,)], "Passport string")

    rows = mask_pii(df, spec(Passport=[PiiType.IDENTIFIER])).collect()

    assert [(row["Passport"], row[MATCHED_COLUMN]) for row in rows] == [
        (REDACTED, True),
        (None, False),
    ]


def test_other_columns_are_untouched_and_unmasked_rows_are_not_counted(spark):
    df = spark.createDataFrame([("1", "VIP customer"), ("2", "jane@example.com")], ["ID", "Notes"])

    rows = mask_pii(df, spec(Notes=[PiiType.EMAIL])).collect()

    assert [(row["ID"], row["Notes"], row[MATCHED_COLUMN]) for row in rows] == [
        ("1", "VIP customer", False),
        ("2", "j***@example.com", True),
    ]


def test_no_personal_data_leaves_the_data_unchanged(spark):
    df = spark.createDataFrame([("1",)], ["ID"])

    result = mask_pii(df, PiiMaskingSpec(columns={}))

    assert result.columns == ["ID", MATCHED_COLUMN]
    assert (result.first()["ID"], result.first()[MATCHED_COLUMN]) == ("1", False)
