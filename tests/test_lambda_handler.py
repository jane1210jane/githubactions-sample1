import json
from typing import Any

import boto3
import pytest
from moto import mock_aws

from sales_report.lambda_handler import handler

SAMPLE_CSV = """date,product,quantity,unit_price
2026-01-05,ノートPC,2,148000
2026-02-02,ノートPC,1,148000
"""
REGION = "ap-northeast-1"


def _event(bucket: str) -> dict[str, Any]:
    return {
        "input": {"bucket": bucket, "key": "in/sales.csv"},
        "output": {"bucket": bucket, "key": "out/report.json"},
    }


@pytest.fixture
def bucket() -> Any:
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(
            Bucket="sales-report-test",
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        client.put_object(
            Bucket="sales-report-test", Key="in/sales.csv", Body=SAMPLE_CSV.encode("utf-8")
        )
        yield client


def test_handler_writes_the_report_to_the_output_location(bucket: Any):
    result = handler(_event("sales-report-test"), object())

    assert result["month_count"] == 2
    assert result["total_amount"] == "444000"
    written = bucket.get_object(Bucket="sales-report-test", Key="out/report.json")
    payload = json.loads(written["Body"].read().decode("utf-8"))
    assert [month["month"] for month in payload["months"]] == ["2026-01", "2026-02"]


def test_handler_reports_the_output_location(bucket: Any):
    result = handler(_event("sales-report-test"), object())

    assert result["output"] == {"bucket": "sales-report-test", "key": "out/report.json"}


def test_handler_raises_a_readable_error_when_the_event_is_missing_input(bucket: Any):
    with pytest.raises(ValueError, match="input"):
        handler({"output": {"bucket": "sales-report-test", "key": "o.json"}}, object())


def test_handler_propagates_a_parse_error_with_the_line_number(bucket: Any):
    bucket.put_object(
        Bucket="sales-report-test",
        Key="in/broken.csv",
        Body="date,product,quantity,unit_price\n2026-01-05,A,いち,100\n".encode(),
    )
    event = _event("sales-report-test")
    event["input"]["key"] = "in/broken.csv"

    with pytest.raises(ValueError, match="2行目"):
        handler(event, object())
