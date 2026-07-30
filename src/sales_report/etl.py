"""CSV を読み、月次集計し、JSON として書き出す ETL。
# EXPERIMENT(stage-07 Q1): 演習1検証用の無害なコメント変更。検証後に削除する。

CLI が「人が読む表を標準出力に出す」のに対し、ETL は「入力を読み、変換し、
出力先に書く」。コンテナに載せて無人で動かすには後者の形が要る。
集計そのものは aggregate モジュールに委ね、ここは入出力だけを担当する。
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sales_report.aggregate import MonthlyTotal, aggregate_monthly, parse_records


@dataclass(frozen=True)
class EtlResult:
    """ETL 1回分の実行結果の要約。ログや戻り値に使う。"""

    month_count: int
    total_amount: Decimal


def to_json_payload(totals: Iterable[MonthlyTotal]) -> dict[str, object]:
    """集計結果を JSON にできる形へ変換する。

    金額は文字列にする。JSON の数値は倍精度浮動小数点なので、
    Decimal のまま数値として書くと精度が落ちる。
    """
    return {
        "months": [
            {
                "month": total.month,
                "total_amount": str(total.total_amount),
                "record_count": total.record_count,
            }
            for total in totals
        ]
    }


def run_etl(input_path: Path, output_path: Path) -> EtlResult:
    """input_path の CSV を集計し、output_path に JSON を書く。"""
    with input_path.open(newline="", encoding="utf-8") as stream:
        totals = aggregate_monthly(parse_records(csv.DictReader(stream)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(to_json_payload(totals), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return EtlResult(
        month_count=len(totals),
        total_amount=sum((total.total_amount for total in totals), Decimal("0")),
    )
