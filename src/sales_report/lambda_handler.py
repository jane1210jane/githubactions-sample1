"""AWS Lambda の入口。

S3 から CSV を取り、ETL にかけ、結果の JSON を S3 に戻す。
このモジュールは「S3 と Lambda の作法」だけを担当し、
集計も変換も etl モジュールに委ねる。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import boto3

from sales_report.etl import run_etl

REQUIRED_SECTIONS = ("input", "output")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """S3 のオブジェクトを ETL にかけ、結果を S3 に書き戻す。"""
    source, destination = _read_locations(event)
    client = boto3.client("s3")

    with tempfile.TemporaryDirectory() as workspace:
        input_path = Path(workspace) / "input.csv"
        output_path = Path(workspace) / "output.json"

        client.download_file(source["bucket"], source["key"], str(input_path))
        result = run_etl(input_path, output_path)
        client.upload_file(str(output_path), destination["bucket"], destination["key"])

    return {
        "month_count": result.month_count,
        "total_amount": str(result.total_amount),
        "output": destination,
    }


def _read_locations(event: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    missing = [section for section in REQUIRED_SECTIONS if section not in event]
    if missing:
        raise ValueError(f"イベントに必要な項目がありません: {', '.join(missing)}")
    return event["input"], event["output"]
