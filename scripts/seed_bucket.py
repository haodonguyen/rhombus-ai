"""Create the dev bucket and upload sample CSV/XLSX datasets. Safe to run repeatedly.

The data deliberately mixes formats (dates, phone numbers, emails embedded in free
text) so later transforms have something realistic to work on.
"""

import csv
import io
import os
import random

import boto3
from botocore.exceptions import ClientError
from openpyxl import Workbook

HEADER = ["ID", "Name", "Email", "Phone", "SignupDate", "Notes"]

# The first rows reproduce the example scenario from the assessment brief.
BRIEF_ROWS = [
    ["1", "John Doe", "john.doe@example.com"],
    ["2", "Jane Smith", "jane_smith@domain.com"],
    ["3", "Alice Brown", "alice.brown@website.org"],
]

FIRST_NAMES = ["John", "Jane", "Alice", "Bob", "Maria", "Wei", "Priya", "Omar", "Lena", "Kofi"]
LAST_NAMES = ["Doe", "Smith", "Brown", "Nguyen", "Garcia", "Chen", "Patel", "Khan", "Muller"]
DOMAINS = ["example.com", "domain.com", "website.org", "mail.co.uk", "company.io"]
DATE_FORMATS = ["{y}-{m:02d}-{d:02d}", "{d:02d}/{m:02d}/{y}", "{mon} {d}, {y}"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PHONE_FORMATS = ["+1 ({a}) {b}-{c}", "{a}-{b}-{c}", "{a}.{b}.{c}"]


def sample_rows(count: int, seed: int = 42) -> list[list[str]]:
    rng = random.Random(seed)
    rows = []
    for index in range(1, count + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{first}.{last}{index}@{rng.choice(DOMAINS)}".lower()
        if index <= len(BRIEF_ROWS):
            _, name, email = BRIEF_ROWS[index - 1]
        else:
            name = f"{first} {last}"
        month = rng.randint(1, 12)
        date = rng.choice(DATE_FORMATS).format(
            y=rng.randint(2018, 2025), m=month, d=rng.randint(1, 28), mon=MONTHS[month - 1]
        )
        phone = rng.choice(PHONE_FORMATS).format(
            a=rng.randint(200, 999), b=rng.randint(200, 999), c=rng.randint(1000, 9999)
        )
        notes = rng.choice(
            ["", "VIP customer", f"Contact backup at {email}", "Prefers phone", f"Call {phone}"]
        )
        rows.append([str(index), name, email, phone, date, notes])
    return rows


def to_csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def to_xlsx(rows: list[list[str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "customers"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"Created bucket {bucket}")


def main() -> None:
    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    ensure_bucket(s3, bucket)

    rows = sample_rows(int(os.environ.get("SEED_ROWS", "1000")))
    objects = {
        "samples/customers.csv": to_csv(rows),
        "samples/customers.xlsx": to_xlsx(rows),
        # Unsupported type: lets the file browser prove it filters by extension.
        "samples/README.txt": b"Sample datasets for local development.\n",
    }
    for key, body in objects.items():
        s3.put_object(Bucket=bucket, Key=key, Body=body)
        print(f"Uploaded s3://{bucket}/{key} ({len(body)} bytes)")


if __name__ == "__main__":
    main()
