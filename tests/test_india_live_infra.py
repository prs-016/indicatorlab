"""Offline YAML contract and session watchdog checks; no AWS or market access."""

import hashlib
import json
import logging
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from src.live.india import TABLE, SessionCalendar
from src.live.india_watchdog import check_once, evaluate_health

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra/india_live"
NOW = datetime(2024, 1, 2, 4, tzinfo=UTC)
CALENDAR = SessionCalendar(
    {
        "2024-01-02": [["09:15", "15:30"]],
        "2024-01-03": [],
        "2024-01-06": [["18:00", "19:00"]],
    },
    source="SYNTHETIC TEST ONLY",
)
SYMBOLS = ("SYN0.NS", "SYN1.NS")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


class CfnLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    name = suffix if suffix == "Ref" else "Fn::" + suffix
    if suffix == "GetAtt" and isinstance(value, str):
        value = value.split(".", 1)
    return {name: value}


CfnLoader.add_multi_constructor("!", intrinsic)


@pytest.fixture
def template():
    return yaml.load((INFRA / "template.yaml").read_text(), Loader=CfnLoader)


def test_template_has_no_shared_resources_or_secrets(template):
    resources = template["Resources"]
    forbidden = {
        "AWS::S3::Bucket",
        "AWS::DynamoDB::Table",
        "AWS::SSM::Parameter",
        "AWS::EC2::NatGateway",
    }
    assert not any(r["Type"] in forbidden for r in resources.values())
    assert "ClusterName" not in template["Parameters"]
    assert resources["Cluster"] == {"Type": "AWS::ECS::Cluster"}
    assert template["Parameters"]["QuoteProvider"]["Default"] == "yahoo"
    assert [
        rule["Assert"]["Fn::Equals"]
        for rule in template["Rules"]["RequiredRegion"]["Assertions"]
    ] == [
        [{"Ref": "AWS::Region"}, "us-east-2"],
        [{"Ref": "AWS::StackName"}, "indicatorlab-india-live"],
    ]
    for action in ("Start", "Stop"):
        target = resources[action]["Properties"]["Target"]["Input"]["Fn::Sub"]
        assert '"Cluster":"${Cluster}"' in target

    assert template["Parameters"]["SchedulesState"]["Default"] == "DISABLED"
    assert resources["Service"]["Properties"]["DesiredCount"] == 0
    assert resources["Service"]["Properties"]["Cluster"] == {"Ref": "Cluster"}


def test_collector_configuration_and_secret_injection(template):
    r = template["Resources"]
    task = r["Task"]["Properties"]
    assert task["RequiresCompatibilities"] == ["FARGATE"]
    assert task["RuntimePlatform"]["CpuArchitecture"] == "ARM64"
    container = task["ContainerDefinitions"][0]
    assert container["EntryPoint"] == ["python", "-B", "-m", "src.live.india_app"]
    assert container["Command"] == ["--run"] and container["StopTimeout"] == 120
    condition, secrets, omitted = container["Secrets"]["Fn::If"]
    assert condition == "UseDhan" and omitted == {"Ref": "AWS::NoValue"}
    assert {v["Name"] for v in secrets} == {
        "DHAN_CLIENT_ID",
        "DHAN_ACCESS_TOKEN",
    }
    assert all(set(v["ValueFrom"]) == {"Ref"} for v in secrets)
    assert not any(v["Name"].startswith("DHAN_") for v in container["Environment"])
    assert r["Service"]["Properties"]["DeploymentConfiguration"] == {
        "MinimumHealthyPercent": 0,
        "MaximumPercent": 100,
    }
    statements = r["TaskRole"]["Properties"]["Policies"][0]["PolicyDocument"][
        "Statement"
    ]
    assert {s["Action"] for s in statements} == {
        "dynamodb:BatchWriteItem",
        "s3:PutObject",
    }
    assert all(s["Resource"] != "*" for s in statements)
    assert "raw/live/india/*" in statements[1]["Resource"]["Fn::Sub"]
    assert "indicatorlab-live-india" in statements[0]["Resource"]["Fn::Sub"]


def test_schedules_monitoring_and_alarm_contract(template):
    r = template["Resources"]
    assert template["Parameters"]["StartExpression"]["Default"] == "cron(5 9 * * ? *)"
    assert template["Parameters"]["StopExpression"]["Default"] == "cron(40 15 * * ? *)"
    for name in ["Start", "Stop"]:
        p = r[name]["Properties"]
        assert p["ScheduleExpressionTimezone"] == "Asia/Kolkata"
        assert p["State"] == {"Ref": "SchedulesState"}
    assert r["WatchdogTimer"]["Properties"]["State"] == {"Ref": "SchedulesState"}
    alarm = r["StaleIngestionAlarm"]["Properties"]
    assert alarm["Period"] == 60 and alarm["TreatMissingData"] == "breaching"
    assert (
        alarm["Namespace"] == "IndicatorLab/India"
        and alarm["MetricName"] == "IngestionHealthy"
    )
    assert alarm["Dimensions"] == [{"Name": "Service", "Value": TABLE}]
    assert (
        r["Watchdog"]["Properties"]["Code"]["ImageUri"]
        == r["Task"]["Properties"]["ContainerDefinitions"][0]["Image"]
    )
    assert "Secrets" not in r["Watchdog"]["Properties"]
    assert r["Watchdog"]["Properties"]["Role"] != r["Task"]["Properties"]["TaskRoleArn"]
    assert r["SecurityGroup"]["Properties"].get("SecurityGroupIngress", []) == []


def test_all_template_references_resolve_locally(template):
    known = (
        set(template["Parameters"])
        | set(template["Resources"])
        | {
            "AWS::Region",
            "AWS::AccountId",
            "AWS::Partition",
            "AWS::StackName",
            "AWS::NoValue",
            "AWS::URLSuffix",
        }
    )

    def walk(value):
        if isinstance(value, dict):
            if "Ref" in value:
                assert value["Ref"] in known
            if "Fn::GetAtt" in value:
                assert value["Fn::GetAtt"][0] in template["Resources"]
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(template)


def test_image_build_context_and_dependencies():
    docker = (INFRA / "Dockerfile").read_text()
    assert "COPY . " not in docker and "COPY src/ " not in docker
    assert "india_app.py" in docker and "india_watchdog.py" in docker
    assert "mock" not in docker.lower()
    assert "COPY runtime/" in docker
    ignore = (INFRA / "Dockerfile.dockerignore").read_text()
    assert ignore.startswith("**\n") and "**/.env*" in ignore
    deps = (INFRA / "requirements.txt").read_text()
    assert all(dep in deps for dep in ["requests", "pandas", "pyarrow", "boto3"])
    assert all(dep not in deps for dep in ["torch", "transformers", "dhanhq"])


@pytest.mark.parametrize(
    "seconds,healthy",
    [(0, True), (60, True), (60.01, False), (120, False), (-1, False)],
)
def test_age_threshold(seconds, healthy):
    receipts = {s: (NOW - timedelta(seconds=seconds)).isoformat() for s in SYMBOLS}
    assert evaluate_health(NOW, CALENDAR, SYMBOLS, receipts) is healthy


@pytest.mark.parametrize(
    "receipts",
    [
        {},
        {"SYN0.NS": NOW.isoformat()},
        {"SYN0.NS": "bad", "SYN1.NS": NOW.isoformat()},
        {"SYN0.NS": "2024-01-02T04:00:00", "SYN1.NS": NOW.isoformat()},
    ],
)
def test_all_symbols_required(receipts):
    assert not evaluate_health(NOW, CALENDAR, SYMBOLS, receipts)


@pytest.mark.parametrize(
    "stamp",
    [
        "2024-01-02T03:45:30+00:00",
        "2024-01-02T03:44:00+00:00",
        "2024-01-03T04:00:00+00:00",
        "2024-01-06T12:30:30+00:00",
    ],
)
def test_closure_and_opening_grace(stamp):
    assert evaluate_health(datetime.fromisoformat(stamp), CALENDAR, SYMBOLS, {})


def test_unknown_calendar_fails():
    with pytest.raises(ValueError):
        evaluate_health(datetime(2024, 1, 4, 4, tzinfo=UTC), CALENDAR, SYMBOLS, {})


@pytest.fixture
def config(tmp_path):
    roster = tmp_path / "roster.csv"
    roster.write_text("Symbol,Series\n" + "".join(f"SYN{i},EQ\n" for i in range(100)))
    calendar = tmp_path / "calendar.json"
    calendar.write_text(
        json.dumps(
            {
                "timezone": "Asia/Kolkata",
                "source": "SYNTHETIC TEST ONLY",
                "sessions": {"2024-01-02": [["09:15", "15:30"]], "2024-01-03": []},
            }
        )
    )
    doc = {
        "review": {
            "approved": True,
            "reviewed_by": "synthetic reviewer",
            "source": "synthetic evidence only",
            "reviewed_at": "2024-01-01T00:00:00+00:00",
            "valid_from": "2024-01-02",
            "valid_until": "2024-01-03",
        }
    }
    for key, path in [("roster", roster), ("calendar", calendar)]:
        doc[key] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(doc))
    return path


class Ddb:
    def __init__(self):
        self.calls = []
        self.response = {
            "Responses": {
                TABLE: [
                    {
                        "symbol": {"S": f"SYN{i}.NS"},
                        "ts_received": {"S": NOW.isoformat()},
                    }
                    for i in range(100)
                ]
            }
        }

    def batch_get_item(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class Metrics:
    def __init__(self):
        self.calls = []

    def put_metric_data(self, **kwargs):
        self.calls.append(kwargs)


def test_check_once_hundred_readonly_receipts(config):
    ddb, metrics = Ddb(), Metrics()
    assert check_once(config, ddb, metrics, now=NOW) == {"healthy": True}
    request = ddb.calls[0]["RequestItems"][TABLE]
    assert len(request["Keys"]) == 100 and request["ConsistentRead"]
    assert metrics.calls[0]["Namespace"] == "IndicatorLab/India"
    assert metrics.calls[0]["MetricData"][0]["Value"] == 1


@pytest.mark.parametrize(
    "cause", ["stale", "missing", "unprocessed", "unknown", "duplicate"]
)
def test_failures_publish_unhealthy(config, cause):
    ddb, metrics = Ddb(), Metrics()
    rows = ddb.response["Responses"][TABLE]
    if cause == "stale":
        rows[0]["ts_received"]["S"] = "2024-01-01T04:00:00+00:00"
    if cause == "missing":
        rows.pop()
    if cause == "unprocessed":
        ddb.response["UnprocessedKeys"] = {TABLE: {"Keys": []}}
    if cause == "unknown":
        rows[0]["symbol"]["S"] = "UNKNOWN.NS"
    if cause == "duplicate":
        rows.append(rows[0])
    assert check_once(config, ddb, metrics, now=NOW) == {"healthy": False}
    assert metrics.calls[0]["MetricData"][0]["Value"] == 0


@pytest.mark.parametrize("change", ["hash", "expired", "unapproved"])
def test_bad_review_is_unhealthy_without_table_read(config, change):
    doc = json.loads(config.read_text())
    if change == "hash":
        doc["calendar"]["sha256"] = "bad"
    if change == "expired":
        doc["review"]["valid_until"] = "2024-01-01"
    if change == "unapproved":
        doc["review"]["approved"] = False
    config.write_text(json.dumps(doc))
    ddb, metrics = Ddb(), Metrics()
    assert check_once(config, ddb, metrics, now=NOW) == {"healthy": False}
    assert ddb.calls == []


def test_closed_day_skips_table(config):
    ddb, metrics = Ddb(), Metrics()
    assert check_once(
        config, ddb, metrics, now=datetime(2024, 1, 3, 4, tzinfo=UTC)
    ) == {"healthy": True}
    assert not ddb.calls


def test_errors_sanitized_and_metric_failure_propagates(config, caplog):
    def denied(**kwargs):
        raise RuntimeError("PRIVATE_TOKEN_AND_PATH")

    ddb, metrics = Ddb(), Metrics()
    ddb.batch_get_item = denied
    with caplog.at_level(logging.ERROR):
        assert check_once(config, ddb, metrics, now=NOW) == {"healthy": False}
    assert "PRIVATE_TOKEN_AND_PATH" not in caplog.text
    metrics.put_metric_data = denied
    with pytest.raises(RuntimeError):
        check_once(config, Ddb(), metrics, now=NOW)
