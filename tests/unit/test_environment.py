"""Environment verification tests. These check the toolchain, not business logic."""

import importlib
from typing import TypedDict

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

ESSENTIAL_PACKAGES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "dotenv",
    "httpx",
    "requests",
    "orjson",
    "pandas",
    "polars",
    "numpy",
    "scipy",
    "duckdb",
    "pyarrow",
    "statsmodels",
    "sklearn",
    "lightgbm",
    "mlflow",
    "joblib",
    "ortools",
    "networkx",
    "langgraph",
    "langchain_core",
    "langchain_openai",
    "openai",
    "tenacity",
    "sqlalchemy",
    "aiosqlite",
    "databricks.sdk",
    "databricks.sql",
]


@pytest.mark.parametrize("name", ESSENTIAL_PACKAGES)
def test_import(name: str) -> None:
    importlib.import_module(name)


def test_fastapi_health() -> None:
    from backend.main import app

    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_duckdb_repository_roundtrip() -> None:
    from backend.repositories.duckdb_repo import DuckDBRepository

    repo = DuckDBRepository(":memory:")
    repo.write_table("t", pa.table({"x": [1, 2, 3]}))
    assert repo.query("SELECT sum(x) AS s FROM t").column("s")[0].as_py() == 6
    assert "t" in repo.list_tables()


def test_parquet_roundtrip(tmp_path) -> None:
    path = tmp_path / "t.parquet"
    pq.write_table(pa.table({"a": [1.5, 2.5]}), path)
    assert pq.read_table(path).column("a").to_pylist() == [1.5, 2.5]


def test_sklearn_fit_predict() -> None:
    import numpy as np
    from sklearn.linear_model import LinearRegression

    x = np.arange(10).reshape(-1, 1)
    model = LinearRegression().fit(x, 2 * x.ravel() + 1)
    assert model.predict([[20]])[0] == pytest.approx(41)


def test_lightgbm_fit() -> None:
    import lightgbm as lgb
    import numpy as np

    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    y = (x[:, 0] > 0).astype(int)
    clf = lgb.LGBMClassifier(n_estimators=10, verbose=-1).fit(x, y)
    assert clf.score(x, y) > 0.9


def test_mlflow_local_experiment(tmp_path) -> None:
    import mlflow

    mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'mlflow.db'}")
    exp_id = mlflow.create_experiment("env-check")
    with mlflow.start_run(experiment_id=exp_id) as run:
        mlflow.log_metric("m", 1.0)
    assert mlflow.get_run(run.info.run_id).data.metrics["m"] == 1.0


def test_ortools_solves_lp() -> None:
    from ortools.linear_solver import pywraplp

    s = pywraplp.Solver.CreateSolver("GLOP")
    x, y = s.NumVar(0, 10, "x"), s.NumVar(0, 10, "y")
    s.Add(x + y <= 12)
    s.Maximize(3 * x + 2 * y)
    assert s.Solve() == pywraplp.Solver.OPTIMAL
    assert s.Objective().Value() == pytest.approx(34)


def test_langgraph_deterministic_graph() -> None:
    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        n: int

    g = StateGraph(State)
    g.add_node("double", lambda s: {"n": s["n"] * 2})
    g.add_node("inc", lambda s: {"n": s["n"] + 1})
    g.add_edge(START, "double")
    g.add_edge("double", "inc")
    g.add_edge("inc", END)
    assert g.compile().invoke({"n": 5}) == {"n": 11}


def test_pydantic_structured_output() -> None:
    class Verdict(BaseModel):
        agent: str
        confidence: float
        evidence_ids: list[str]

    v = Verdict.model_validate_json('{"agent":"a","confidence":0.7,"evidence_ids":["e1"]}')
    assert v.confidence == 0.7
    with pytest.raises(ValueError):
        Verdict.model_validate({"agent": "a", "confidence": "high", "evidence_ids": []})


def test_repository_factory_defaults_to_duckdb() -> None:
    from backend.repositories.duckdb_repo import DuckDBRepository
    from backend.repositories.factory import get_repository
    from config.settings import Settings

    assert isinstance(get_repository(Settings(local_db_path=":memory:")), DuckDBRepository)
