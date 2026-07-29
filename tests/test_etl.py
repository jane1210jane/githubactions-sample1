import json
from decimal import Decimal
from pathlib import Path

import pytest

from sales_report.aggregate import MonthlyTotal
from sales_report.etl import EtlResult, run_etl, to_json_payload

SAMPLE_CSV = """date,product,quantity,unit_price
2026-01-05,ノートPC,2,148000
2026-02-02,ノートPC,1,148000
"""


def test_to_json_payload_keeps_amounts_as_strings():
    totals = (MonthlyTotal(month="2026-01", total_amount=Decimal("296000"), record_count=2),)

    payload = to_json_payload(totals)

    assert payload == {
        "months": [{"month": "2026-01", "total_amount": "296000", "record_count": 2}]
    }


def test_run_etl_writes_the_aggregated_result_as_json(tmp_path: Path):
    input_path = tmp_path / "sales.csv"
    input_path.write_text(SAMPLE_CSV, encoding="utf-8")
    output_path = tmp_path / "out" / "report.json"

    result = run_etl(input_path, output_path)

    assert result == EtlResult(month_count=2, total_amount=Decimal("444000"))
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert [month["month"] for month in written["months"]] == ["2026-01", "2026-02"]


def test_run_etl_creates_the_output_directory(tmp_path: Path):
    input_path = tmp_path / "sales.csv"
    input_path.write_text(SAMPLE_CSV, encoding="utf-8")
    output_path = tmp_path / "deep" / "nested" / "report.json"

    run_etl(input_path, output_path)

    assert output_path.exists()


def test_run_etl_raises_with_the_line_number_for_a_broken_row(tmp_path: Path):
    input_path = tmp_path / "broken.csv"
    input_path.write_text(
        "date,product,quantity,unit_price\n2026-01-05,A,いち,100\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="2行目"):
        run_etl(input_path, tmp_path / "out.json")


def test_run_etl_writes_an_empty_month_list_for_a_header_only_file(tmp_path: Path):
    input_path = tmp_path / "empty.csv"
    input_path.write_text("date,product,quantity,unit_price\n", encoding="utf-8")
    output_path = tmp_path / "out.json"

    result = run_etl(input_path, output_path)

    assert result == EtlResult(month_count=0, total_amount=Decimal("0"))
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"months": []}
