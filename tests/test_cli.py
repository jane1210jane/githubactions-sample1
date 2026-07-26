from pathlib import Path

from sales_report.cli import EXIT_INVALID_INPUT, EXIT_OK, main

SAMPLE_CSV = """date,product,quantity,unit_price
2026-01-05,ノートPC,2,148000
2026-02-02,ノートPC,1,148000
"""


def test_main_prints_monthly_totals_and_returns_zero(tmp_path: Path, capsys):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

    exit_code = main([str(csv_path)])

    output = capsys.readouterr().out
    assert exit_code == EXIT_OK
    assert "2026-01" in output
    assert "296,000" in output


def test_main_reports_a_readable_error_when_the_file_is_missing(tmp_path: Path, capsys):
    exit_code = main([str(tmp_path / "notfound.csv")])

    assert exit_code == EXIT_INVALID_INPUT
    assert "エラー" in capsys.readouterr().err


def test_main_reports_a_readable_error_when_a_value_is_invalid(tmp_path: Path, capsys):
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text(
        "date,product,quantity,unit_price\n2026-01-05,A,いち,100\n", encoding="utf-8"
    )

    exit_code = main([str(csv_path)])

    assert exit_code == EXIT_INVALID_INPUT
    assert "2行目" in capsys.readouterr().err
