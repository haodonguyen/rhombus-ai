import json
from collections.abc import Mapping, Sequence

PROMPT_VERSION = "pii-v1"

SYSTEM_PROMPT = r"""You decide which spreadsheet columns contain personal data that must be masked.

You receive column names with sample values. For every column, list the kinds of personal data it contains in pii_types:
- email: email addresses, alone or inside other text
- phone: phone numbers, alone or inside other text
- person_name: names of people
- credit_card: payment card numbers
- identifier: personal identifiers such as passport, national ID, tax, social security or bank account numbers
- address: postal or street addresses
- other: other personal data, such as dates of birth
Use ["none"] when a column has no personal data, for example row numbers, product codes, dates of events, statuses or free text without personal details.

Judge by the sample values, not only the column name. Return every column exactly once, with its name exactly as given. The explanation is one short sentence for the user.

Example:

Columns:
- ID: ["1", "2", "3"]
- Customer: ["John Doe", "Jane Smith"]
- Notes: ["VIP customer", "Call 816.227.4257", "Contact backup at jane@example.com"]
- Status: ["active", "closed"]
{"columns": [{"column": "ID", "pii_types": ["none"]}, {"column": "Customer", "pii_types": ["person_name"]}, {"column": "Notes", "pii_types": ["phone", "email"]}, {"column": "Status", "pii_types": ["none"]}], "explanation": "Customer holds names, and Notes contains phone numbers and email addresses."}"""


def build_user_message(samples: Mapping[str, Sequence[str]]) -> str:
    lines = ["Columns:"]
    lines += [
        f"- {column}: {json.dumps(list(values), ensure_ascii=False)}"
        for column, values in samples.items()
    ]
    return "\n".join(lines)
