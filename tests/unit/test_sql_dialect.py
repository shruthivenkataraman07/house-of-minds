import duckdb

from analytics.sql_dialect import days_between, ident, local_hhmm, seconds_between, year_month


def test_duckdb_helpers_execute():
    con = duckdb.connect()
    a, b = "TIMESTAMP '2025-03-08 14:00:00'", "TIMESTAMP '2025-03-09 13:00:00'"
    assert con.execute(f"SELECT {seconds_between(a, b, 'duckdb')}").fetchone()[0] == 82800
    d0, d1 = "DATE '2025-01-01'", "DATE '2025-01-31'"
    assert con.execute(f"SELECT {days_between(d0, d1, 'duckdb')}").fetchone()[0] == 30
    assert con.execute(f"SELECT {local_hhmm(a, 'duckdb')}").fetchone()[0] == "06:00"
    assert con.execute(f"SELECT {year_month('DATE ' + chr(39) + '2025-03-08' + chr(39))}"
                       ).fetchone()[0] == "2025-03"


def test_databricks_spellings():
    assert seconds_between("a", "b", "databricks") == "timestampdiff(SECOND, a, b)"
    assert days_between("a", "b", "databricks") == "datediff(b, a)"
    assert "from_utc_timestamp" in local_hhmm("t", "databricks")
    assert ident("x", "databricks") == "`x`" and ident("x", "duckdb") == '"x"'
