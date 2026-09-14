import json
from collections.abc import Mapping, Sequence

PROMPT_VERSION = "normalize-v1"

SYSTEM_PROMPT = r"""You write a specification that rewrites the values of spreadsheet columns into one consistent format.

You receive the target format the user wants and sample values from the columns. Apache Spark applies your specification to every value in those columns, so cover every way values are written in the samples. Values that no format or rule recognises are left unchanged.

When the values are dates, use kind "date":
- input_formats: one Java date pattern for each different way dates are written in the samples. Pattern letters: yyyy four-digit year, yy two-digit year, MM two-digit month, M month without padding, MMM short month name (Jan), MMMM full month name (January), dd two-digit day, d day without padding, EEE short weekday name. Put literal letters in single quotes.
- output_format: the Java date pattern of the target format.
- rules: an empty list.

For other values (phone numbers, codes, names, amounts), use kind "rules":
- rules: rewrite rules tried in order; the first rule whose pattern matches a value rewrites it. Patterns use Java regex syntax without named groups and should match the whole value with ^ and $. Capture the parts to keep with groups and refer to them as $1, $2 in the replacement. Replacements must not contain backslashes.
- input_formats: an empty list, and output_format "".

If reformatting cannot achieve the request (for example it needs outside knowledge or a calculation), set feasible to false and explain why.

The explanation is one or two plain sentences for the user.

Examples:

Target format: dates as YYYY-MM-DD
Sample values:
- SignupDate: ["2020-04-24", "25/10/2018", "Nov 22, 2021", "Jan 2, 2024"]
{"feasible": true, "kind": "date", "input_formats": ["yyyy-MM-dd", "dd/MM/yyyy", "MMM d, yyyy"], "output_format": "yyyy-MM-dd", "rules": [], "explanation": "Reads dates written as 2020-04-24, 25/10/2018 or Nov 22, 2021 and writes them as YYYY-MM-DD."}

Target format: phone numbers like 555-123-4567
Sample values:
- Phone: ["+1 (892) 958-9935", "816.227.4257", "552-818-5333"]
{"feasible": true, "kind": "rules", "input_formats": [], "output_format": "", "rules": [{"pattern": "^(?:\\+?1[\\s.-]?)?\\(?(\\d{3})\\)?[\\s.-]?(\\d{3})[\\s.-]?(\\d{4})$", "replacement": "$1-$2-$3"}], "explanation": "Rewrites 10-digit phone numbers, with or without a +1 prefix, as 555-123-4567."}

Target format: prices converted to euros
Sample values:
- Price: ["$10.00", "$24.50"]
{"feasible": false, "kind": "rules", "input_formats": [], "output_format": "", "rules": [], "explanation": "Converting currencies needs exchange rates, which reformatting cannot provide."}"""


def build_user_message(description: str, samples: Mapping[str, Sequence[str]]) -> str:
    lines = [f"Target format: {description.strip()}", "Sample values:"]
    lines += [
        f"- {column}: {json.dumps(list(values), ensure_ascii=False)}"
        for column, values in samples.items()
    ]
    return "\n".join(lines)
