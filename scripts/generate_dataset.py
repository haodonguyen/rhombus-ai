"""Generate a large synthetic customers CSV and upload it to the bucket.

Rows are streamed to a temporary file and sent with a multipart upload, so memory use
stays flat whatever --rows is. Run it inside the stack:

    docker compose run --rm minio-seed python /scripts/generate_dataset.py --rows 5000000
"""

import argparse
import csv
import os
import random
import tempfile
import time

from boto3.s3.transfer import TransferConfig
from seed_bucket import HEADER, ensure_bucket, make_row, s3_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and upload a large customers CSV.")
    parser.add_argument("--rows", type=int, default=1_000_000, help="number of data rows")
    parser.add_argument("--key", help="object key (default: large/customers-<rows>.csv)")
    parser.add_argument("--seed", type=int, default=7, help="random seed for reproducible data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bucket = os.environ["S3_BUCKET"]
    key = args.key or f"large/customers-{args.rows}.csv"
    s3 = s3_client()
    ensure_bucket(s3, bucket)

    rng = random.Random(args.seed)
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for index in range(1, args.rows + 1):
            writer.writerow(make_row(rng, index))
        handle.flush()
        size_mib = os.path.getsize(handle.name) / 1024**2
        generated = time.perf_counter()

        s3.upload_file(
            handle.name,
            bucket,
            key,
            Config=TransferConfig(multipart_chunksize=64 * 1024**2, max_concurrency=4),
        )

    print(
        f"Uploaded s3://{bucket}/{key}: {args.rows:,} rows, {size_mib:.1f} MiB "
        f"(generated in {generated - started:.1f}s, uploaded in "
        f"{time.perf_counter() - generated:.1f}s)"
    )


if __name__ == "__main__":
    main()
