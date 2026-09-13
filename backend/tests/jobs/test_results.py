from apps.jobs.results import MAX_PAGE_SIZE, read_results_page

# Spark's monotonically_increasing_id encodes the partition in the upper bits, so ids jump
# between part files; pagination must not assume consecutive ids.
PARTS = [
    [(0, "John", "REDACTED", True), (1, "Jane", "jane", False), (2, "Ann", "REDACTED", True)],
    [(8589934592, "Bob", "bob", False), (8589934593, "Eve", "REDACTED", True)],
]


def test_first_page_is_ordered_and_numbered(write_result_parts):
    page = read_results_page(write_result_parts(PARTS), total_rows=5, page=1, page_size=2)

    assert page.columns == ["Name", "Email"]
    assert [(r.row_number, r.matched, r.values) for r in page.rows] == [
        (1, True, ["John", "REDACTED"]),
        (2, False, ["Jane", "jane"]),
    ]
    assert page.total_pages == 3


def test_page_spanning_part_files(write_result_parts):
    page = read_results_page(write_result_parts(PARTS), total_rows=5, page=2, page_size=2)

    assert [r.values[0] for r in page.rows] == ["Ann", "Bob"]
    assert [r.row_number for r in page.rows] == [3, 4]


def test_page_past_the_end_is_empty(write_result_parts):
    page = read_results_page(write_result_parts(PARTS), total_rows=5, page=10, page_size=2)

    assert page.rows == []
    assert page.columns == ["Name", "Email"]


def test_page_size_is_clamped(write_result_parts):
    page = read_results_page(write_result_parts(PARTS), total_rows=5, page=1, page_size=10_000)

    assert page.page_size == MAX_PAGE_SIZE
    assert len(page.rows) == 5


def test_empty_output_has_columns_but_no_rows(write_result_parts):
    page = read_results_page(write_result_parts([[]]), total_rows=0, page=1, page_size=50)

    assert page.rows == []
    assert page.columns == ["Name", "Email"]
    assert page.total_pages == 1
