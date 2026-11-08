import pytest

from optimization.action_catalog import (
    BUDGET_CENTS,
    ActionCatalog,
    CatalogAction,
    SelectedAction,
    price_selection,
)

ROWS = [  # mirrors the official catalog structure
    ("A-MOVE-MACHINE", "machine", 180000, 0, 2, 180, 24, "same_machine"),
    ("A-MOVE-BANK", "bank", 950000, 0, 5, 480, 3, "same_machine"),
    ("A-REPLACE-LEASE", "machine", 250000, 5500, 14, 360, 20, "same_machine"),
    ("A-REPLACE-BUY", "machine", 2200000, 0, 21, 360, 10, "same_machine"),
    ("A-TECH-SHIFT", "technician_shift", 1152000, 0, 7, 0, 3, None),
    ("A-PREVENTIVE", "manufacturer", 900000, 0, 7, 90, 3, None),
    ("A-INSPECT", "machine", 120000, 0, 1, 120, 15, None),
    ("A-WAYFINDING", "zone", 750000, 0, 10, 0, 2, None),
    ("A-COMP-PILOT", "pilot", 400000, 0, 5, 0, 1, "comp_policy"),
    ("A-COMP-CHANGE", "policy", 150000, 0, 3, 0, 1, "comp_policy"),
    ("A-PROMO", "event", 1500000, 0, 14, 0, 2, None),
    ("A-SURVEY", "month", 350000, 0, 7, 0, 1, None),
    ("A-HOLD", "none", 0, 0, 0, 0, 1, None),
]


@pytest.fixture
def cat():
    acts = {r[0]: CatalogAction(action_type_id=r[0], name=r[0], unit=r[1], unit_cost_cents=r[2],
                                recurring_cost_cents_per_day=r[3], lead_days=r[4],
                                downtime_minutes=r[5], quantity_limit=r[6],
                                incompatibility_group=r[7]) for r in ROWS}
    return ActionCatalog(actions=acts)


def sel(aid, q=1, targets=None):
    return SelectedAction(action_type_id=aid, quantity=q, targets=targets or [])


def test_guide_lease_example(cat):
    r = price_selection(cat, [sel("A-REPLACE-LEASE")])
    assert r.total_cents == 338000 and r.valid  # $2,500 + 16 x $55


def test_units_are_cents(cat):
    r = price_selection(cat, [sel("A-INSPECT", 3)])
    assert r.total_usd == 3600.0 and r.unspent_cents == BUDGET_CENTS - 360000


def test_budget_boundary(cat):
    ok = price_selection(cat, [sel("A-REPLACE-BUY", 4), sel("A-INSPECT", 10)])
    assert ok.total_cents == 8800000 + 1200000 == BUDGET_CENTS and ok.valid
    over = price_selection(cat, [sel("A-REPLACE-BUY", 5)])
    assert not over.valid and any("exceeds budget" in v for v in over.violations)


def test_quantity_limit(cat):
    r = price_selection(cat, [sel("A-INSPECT", 16)])
    assert any("exceeds limit" in v for v in r.violations)


def test_max_three_types_hold_not_counted(cat):
    three = price_selection(cat, [sel("A-INSPECT"), sel("A-SURVEY"), sel("A-COMP-PILOT"),
                                  sel("A-HOLD")])
    assert three.valid and three.action_types_used == 3
    four = price_selection(cat, [sel("A-INSPECT"), sel("A-SURVEY"), sel("A-COMP-PILOT"),
                                 sel("A-WAYFINDING")])
    assert not four.valid


def test_comp_policy_incompatible(cat):
    r = price_selection(cat, [sel("A-COMP-PILOT"), sel("A-COMP-CHANGE")])
    assert any("comp_policy" in v for v in r.violations)


def test_same_machine_conflict(cat):
    r = price_selection(cat, [sel("A-MOVE-MACHINE", 1, ["M-1"]),
                              sel("A-REPLACE-LEASE", 1, ["M-1"])])
    assert any("same_machine" in v for v in r.violations)
    ok = price_selection(cat, [sel("A-MOVE-MACHINE", 1, ["M-1"]),
                               sel("A-INSPECT", 1, ["M-1"])])
    assert ok.valid


def test_lead_time_operating_days(cat):
    assert cat.actions["A-REPLACE-LEASE"].operating_days == 16
    assert cat.actions["A-REPLACE-BUY"].operating_days == 9
    assert str(cat.actions["A-PROMO"].effective_from) == "2025-07-15"


def test_unknown_action_rejected(cat):
    assert not price_selection(cat, [sel("A-INVENTED")]).valid


def test_catalog_requires_13_actions(cat):
    with pytest.raises(ValueError):
        ActionCatalog(actions=dict(list(cat.actions.items())[:12]))
