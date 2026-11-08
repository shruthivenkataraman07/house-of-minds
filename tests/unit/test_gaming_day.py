"""Gaming-day mapping across the 2025-03-09 DST change (23-hour gaming date 2025-03-08)."""

import duckdb
import pytest

from analytics.metrics import gaming_day_join


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("""CREATE TABLE calendar_day AS SELECT * FROM (VALUES
        (DATE '2025-03-07', TIMESTAMP '2025-03-07 14:00', TIMESTAMP '2025-03-08 14:00', 86400),
        (DATE '2025-03-08', TIMESTAMP '2025-03-08 14:00', TIMESTAMP '2025-03-09 13:00', 82800),
        (DATE '2025-03-09', TIMESTAMP '2025-03-09 13:00', TIMESTAMP '2025-03-10 13:00', 86400))
        t(gaming_date, gaming_day_start_utc, gaming_day_end_utc, scheduled_seconds)""")
    return c


@pytest.mark.parametrize("utc,expected", [
    ("2025-03-08 13:59:59", "2025-03-07"),  # 05:59 PST Saturday -> Friday's gaming day
    ("2025-03-08 14:00:00", "2025-03-08"),  # 06:00 PST
    ("2025-03-09 12:59:59", "2025-03-08"),  # 05:59 PDT Sunday, after the clock change
    ("2025-03-09 13:00:00", "2025-03-09"),  # 06:00 PDT
])
def test_gaming_date_boundaries(con, utc, expected):
    got = con.execute(f"SELECT cal.gaming_date FROM (SELECT TIMESTAMP '{utc}' ts) e "
                      f"{gaming_day_join('e.ts')}").fetchone()[0]
    assert str(got) == expected


def test_dst_day_is_23_hours(con):
    assert con.execute("SELECT scheduled_seconds FROM calendar_day "
                       "WHERE gaming_date = DATE '2025-03-08'").fetchone()[0] == 82800
