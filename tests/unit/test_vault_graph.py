import pytest

from vault.graph import Graph, Node


def g() -> Graph:
    x = Graph()
    for n in ["src", "ev", "asm", "cand", "pf", "claim", "metric"]:
        x.add_node(Node(n, "t", n, "S", "ref", "v1"))
    x.add_edge("ev", "src", "DERIVED_FROM")
    x.add_edge("asm", "ev", "DERIVED_FROM")
    x.add_edge("cand", "asm", "ASSUMES")
    x.add_edge("pf", "cand", "USED_BY_OPTIMIZER")
    x.add_edge("claim", "asm", "CHALLENGES")
    x.add_edge("metric", "pf", "DISPLAYED_BY_METRIC")
    return x


def test_traversal_and_impact_classes():
    x = g()
    assert x.upstream("pf") == {"cand", "asm", "ev", "src"}
    imp = x.impact("ev")
    assert imp["direct"] == {"asm", "cand", "pf"}
    assert imp["possible"] == {"claim", "metric"}  # argument/display level only


def test_cycle_detection_and_dangling():
    x = g()
    assert x.derivation_cycles() == []
    x.add_edge("src", "pf", "DERIVED_FROM")
    assert x.derivation_cycles()
    x.add_edge("claim", "ghost", "SUPPORTS")
    assert ("claim", "ghost", "SUPPORTS") in x.dangling()


def test_invalid_edges_rejected():
    x = g()
    with pytest.raises(ValueError):
        x.add_edge("ev", "src", "CAUSES")
    with pytest.raises(ValueError):
        x.add_edge("ev", "ev", "DERIVED_FROM")


def test_resolver_and_public_scan():
    import pandas as pd

    from vault.extra import resolve, scan_public
    c = {"entities": {"machine": ["M-1158"], "zone": ["Z-B40"]},
         "synonyms": {"back forty": "Z-B40"}}
    assert resolve(c, "zone", "Back Forty") == "Z-B40"
    for bad in [("machine", "M-9999"), ("planet", "x")]:
        with pytest.raises(KeyError):
            resolve(c, *bad)
    assert scan_public(pd.DataFrame({"player_id": ["P1"]})) == ["player_id"]
    fake_token = "dapi" + "0123456789abcdef" + "0123"  # built at runtime: not a literal secret
    assert scan_public(pd.DataFrame({"x": [fake_token]}))
    assert scan_public(pd.DataFrame({"machine_id": ["M-1158"]})) == []
