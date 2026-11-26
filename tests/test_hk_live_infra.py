"""Offline deployment guard checks; never invoke AWS or start a collector."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class TemplateLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag: value}


TemplateLoader.add_multi_constructor("!", intrinsic)


def test_existing_table_region_and_cost_guards():
    path = ROOT / "infra/hk_live/template.yaml"
    text = path.read_text()
    document = yaml.load(text, Loader=TemplateLoader)
    resources = document["Resources"]
    assert not any(row["Type"] == "AWS::DynamoDB::Table" for row in resources.values())
    assert document["Parameters"]["QuoteTableName"]["Default"] == "indicatorlab-live-hk"
    assert document["Parameters"]["SchedulesState"]["Default"] == "DISABLED"
    assert "us-west-2" not in text
    assert "us-east-2" in str(document["Rules"]["RequiredRegion"])
    assert resources["Service"]["Properties"]["DesiredCount"] == 0
    for key in ["Start", "Stop", "WatchdogTimer"]:
        assert resources[key]["Properties"]["State"] == {"Ref": "SchedulesState"}
    assert "CreateTable" not in text and "DeleteTable" not in text
    assert "${QuoteTableName}" in str(resources["CollectorRole"])
    assert "${QuoteTableName}" in str(resources["WatchdogRole"])
    assert resources["Watchdog"]["Properties"]["Environment"]["Variables"][
        "HK_QUOTE_TABLE"
    ] == {"Ref": "QuoteTableName"}


def test_hk_config_does_not_replace_other_markets():
    data = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert data["live"]["region"] == "us-east-2"
    assert data["live"]["hk"]["table"] == "indicatorlab-live-hk"
    assert len(data["markets"]["US"]["stocks"]) == 10
    assert data["markets"]["IN"]["stocks"] == {}


def test_wrong_runtime_region_fails_before_any_aws_call(monkeypatch):
    import boto3

    from src.hk.cloud.watchdog import handler
    from src.hk.live import AwsSink

    monkeypatch.setattr(
        boto3,
        "resource",
        lambda *a, **kw: pytest.fail("Wrong region must not invoke AWS"),
    )
    with pytest.raises(ValueError, match="us-east-2"):
        AwsSink(region="us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    with pytest.raises(ValueError, match="us-east-2"):
        handler({}, None)


def test_watchdog_does_not_hide_an_old_receipt_behind_a_new_one():
    from datetime import datetime

    from src.hk.cloud.watchdog import health

    now = datetime.fromisoformat("2026-11-12T02:00:00+00:00")
    assert not health(
        now, "open", ["2026-11-12T01:59:59+00:00", "2026-11-12T01:58:00+00:00"]
    )["healthy"]
