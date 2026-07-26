"""売上レコードの読み取りと月次集計。

このモジュールは副作用を持たない純粋関数だけで構成する。
CLI・API・GUI・Databricks は、すべてここを薄く包むだけにする。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

REQUIRED_COLUMNS = ("date", "product", "quantity", "unit_price")
HEADER_LINE_COUNT = 1
NO_DATA_MESSAGE = "(対象データなし)"


@dataclass(frozen=True)
class SalesRecord:
    """CSV の 1 行に対応する売上レコード。"""

    sold_on: date
    product: str
    quantity: int
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class MonthlyTotal:
    """ある月の集計結果。month は "2026-01" 形式。"""

    month: str
    total_amount: Decimal
    record_count: int


def parse_records(rows: Iterable[Mapping[str, str]]) -> tuple[SalesRecord, ...]:
    """文字列の辞書列を SalesRecord に変換する。不正な行があれば ValueError。"""
    return tuple(
        _parse_row(row, line_number)
        for line_number, row in enumerate(rows, start=HEADER_LINE_COUNT + 1)
    )


def _parse_row(row: Mapping[str, str], line_number: int) -> SalesRecord:
    missing = [column for column in REQUIRED_COLUMNS if column not in row]
    if missing:
        raise ValueError(f"{line_number}行目: 列が足りません: {', '.join(missing)}")

    try:
        return SalesRecord(
            sold_on=date.fromisoformat(row["date"]),
            product=row["product"],
            quantity=int(row["quantity"]),
            unit_price=Decimal(row["unit_price"]),
        )
    except (ValueError, InvalidOperation) as error:
        raise ValueError(f"{line_number}行目: 値を解釈できません: {error}") from error


def aggregate_monthly(records: Iterable[SalesRecord]) -> tuple[MonthlyTotal, ...]:
    """月ごとの売上金額と件数を集計する。結果は月の昇順。"""
    amounts: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)

    for record in records:
        month = f"{record.sold_on:%Y-%m}"
        amounts[month] += record.amount
        counts[month] += 1

    return tuple(
        MonthlyTotal(month=month, total_amount=amounts[month], record_count=counts[month])
        for month in sorted(amounts)
    )


def format_table(totals: Iterable[MonthlyTotal]) -> str:
    """集計結果を人間が読める表に整形する。"""
    header = ["月       件数         売上金額", "-------- ---- ----------------"]
    body = [f"{total.month} {total.record_count:>4} {total.total_amount:>16,}" for total in totals]
    return "\n".join(header + (body or [NO_DATA_MESSAGE]))
