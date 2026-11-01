"""OFFLINE SYNTHETIC tests for vintage-calibrated, independently checked factors."""

import pytest

from src.india_adjustments import audit_conversion, parse_action
from src.india_reconciliation import SESSION_DATES


def arguments(session):
    # Synthetic nominal 100 at both anchors, later 1:1 bonus, and Rs 10 cash
    # dividend on a verified Rs 100 previous close: S=.5, D=.8*.9=.72.
    return dict(
        session=session, nominal_close=120., terminal_date="2024-12-31",
        terminal_close=100., terminal_adjusted_close=80.,
        events=[{"date": "2024-08-01", "subject": "Dividend - Rs 10 Per Share"},
                {"date": "2025-08-01", "subject": "Bonus 1:1"}],
        previous_nominal_closes={"2024-08-01": 100.},
        anchors=[{"date": "2023-11-10", "nominal_close": 100.,
                  "yahoo_close": 50., "yahoo_adjusted_close": 36.},
                 {"date": "2024-05-21", "nominal_close": 100.,
                  "yahoo_close": 50., "yahoo_adjusted_close": 36.}],
    )


@pytest.mark.parametrize("session", SESSION_DATES)
def test_recovered_session_independent_chain_and_two_anchors(session):
    row = audit_conversion(**arguments(session))
    assert row["verified"]
    assert row["split_share_multiplier"] == 2
    assert row["reconstructed_dividend_factor"] == pytest.approx(.72)
    assert row["total_conversion_factor"] == pytest.approx(.36)
    assert row["adjusted_close"] == pytest.approx(43.2)


def test_split_only_is_not_accepted_as_total_factor():
    args = arguments(SESSION_DATES[0])
    args["anchors"][1]["yahoo_adjusted_close"] = 50.
    row = audit_conversion(**args)
    assert not row["verified"] and row["adjusted_close"] is None


def test_missing_independent_dividend_evidence_leaves_observation_unresolved():
    args = arguments(SESSION_DATES[0])
    args["previous_nominal_closes"] = {}
    row = audit_conversion(**args)
    assert not row["verified"] and row["adjusted_close"] is None
    assert "pre-dividend" in row["unresolved_reason"]


def test_action_in_bracket_disallows_carried_anchor_factor():
    args = arguments(SESSION_DATES[0])
    args["events"].append({"date": SESSION_DATES[0], "subject": "Dividend - Rs 1 Per Share"})
    row = audit_conversion(**args)
    assert not row["verified"]
    assert "inside anchor" in row["unresolved_reason"]


def test_no_holdout_price_inputs_for_calibration_or_anchors():
    args = arguments(SESSION_DATES[0])
    args["terminal_date"] = "2025-10-01"
    assert not audit_conversion(**args)["verified"]
    args = arguments(SESSION_DATES[0])
    args["anchors"][1]["date"] = "2025-10-01"
    assert not audit_conversion(**args)["verified"]


@pytest.mark.parametrize("description,kind,value", [
    ("Bonus 1:1", "shares", 2),
    ("Face Value Split (Sub-Division) - From Rs 5/- Per Share To Re 1/- Per Share", "shares", 5),
    ("Interim Dividend - Rs 9 Per Share Special Dividend - Rs 18 Per Share", "dividend", 27),
    ("Dividend - Re 1 Per Sh", "dividend", 1),
    ("Buy Back", "nonadjusting_buyback", 1),
])
def test_official_action_parsing(description, kind, value):
    assert parse_action(description) == (kind, value)


def test_unknown_action_and_duplicate_action_do_not_pass():
    args = arguments(SESSION_DATES[0])
    args["events"].append({"date": "2024-06-01", "subject": "Rights distribution"})
    assert not audit_conversion(**args)["verified"]
    args = arguments(SESSION_DATES[0])
    args["events"].append(args["events"][0])
    assert not audit_conversion(**args)["verified"]
