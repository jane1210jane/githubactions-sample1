"""sales-report コマンドの入口。

CSV の読み込みと標準出力への書き出しという副作用だけを担当し、
集計ロジックは aggregate モジュールに委ねる。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path

from sales_report.aggregate import aggregate_monthly, format_table, parse_records

EXIT_OK = 0
EXIT_INVALID_INPUT = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sales-report", description="売上CSVを月次集計して表示する"
    )
    parser.add_argument("csv_path", type=Path, help="売上CSVのパス")
    args = parser.parse_args(argv)

    try:
        totals = aggregate_monthly(parse_records(_read_rows(args.csv_path)))
    except (OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    print(format_table(totals))
    return 1


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


if __name__ == "__main__":
    raise SystemExit(main())
