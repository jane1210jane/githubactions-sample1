from datetime import date
from decimal import Decimal

import pytest

from sales_report.aggregate import (
    MonthlyTotal,
    SalesRecord,
    aggregate_monthly,
    format_table,
    parse_records,
)


def test_parse_records_converts_each_column_to_its_type():
    rows = [{"date": "2026-01-05", "product": "ノートPC", "quantity": "2", "unit_price": "148000"}]

    records = parse_records(rows)

    assert records == (
        SalesRecord(
            sold_on=date(2026, 1, 5),
            product="ノートPC",
            quantity=2,
            unit_price=Decimal("148000"),
        ),
    )


def test_parse_records_raises_when_a_required_column_is_missing():
    rows = [{"date": "2026-01-05", "product": "ノートPC", "quantity": "2"}]

    with pytest.raises(ValueError, match="unit_price"):
        parse_records(rows)


def test_parse_records_reports_the_line_number_of_an_invalid_value():
    rows = [
        {"date": "2026-01-05", "product": "A", "quantity": "1", "unit_price": "100"},
        {"date": "2026-01-06", "product": "B", "quantity": "いち", "unit_price": "100"},
    ]

    with pytest.raises(ValueError, match="3行目"):
        parse_records(rows)


def test_sales_record_amount_is_quantity_times_unit_price():
    record = SalesRecord(
        sold_on=date(2026, 1, 5), product="A", quantity=3, unit_price=Decimal("1200")
    )

    assert record.amount == Decimal("3600")


def test_aggregate_monthly_sums_amount_and_counts_per_month():
    records = (
        SalesRecord(sold_on=date(2026, 1, 5), product="A", quantity=2, unit_price=Decimal("100")),
        SalesRecord(sold_on=date(2026, 1, 20), product="B", quantity=1, unit_price=Decimal("50")),
        SalesRecord(sold_on=date(2026, 2, 3), product="A", quantity=1, unit_price=Decimal("100")),
    )

    totals = aggregate_monthly(records)

    assert totals == (
        MonthlyTotal(month="2026-01", total_amount=Decimal("250"), record_count=2),
        MonthlyTotal(month="2026-02", total_amount=Decimal("100"), record_count=1),
    )


def test_aggregate_monthly_returns_months_in_ascending_order():
    records = (
        SalesRecord(sold_on=date(2026, 3, 1), product="A", quantity=1, unit_price=Decimal("1")),
        SalesRecord(sold_on=date(2026, 1, 1), product="A", quantity=1, unit_price=Decimal("1")),
    )

    months = [total.month for total in aggregate_monthly(records)]

    assert months == ["2026-01", "2026-03"]


def test_aggregate_monthly_returns_empty_tuple_for_no_records():
    assert aggregate_monthly(()) == ()


def test_format_table_shows_a_row_per_month():
    totals = (MonthlyTotal(month="2026-01", total_amount=Decimal("250"), record_count=2),)

    table = format_table(totals)

    assert "2026-01" in table
    assert "250" in table


def test_format_table_states_explicitly_when_there_is_no_data():
    assert "(対象データなし)" in format_table(())
