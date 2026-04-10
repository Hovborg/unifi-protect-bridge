import json

from typer.testing import CliRunner

from custom_components.unifi_protect_bridge.const import KNOWN_DETECTION_TYPES, SOURCE_LABELS
from unifi_protect_bridge.cli import app
from unifi_protect_bridge.detections import (
    KNOWN_DETECTION_TYPES as CLI_KNOWN_DETECTION_TYPES,
)
from unifi_protect_bridge.detections import (
    SOURCE_LABELS as CLI_SOURCE_LABELS,
)

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Support CLI for UniFi Protect Bridge" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "UniFi Protect Bridge 0.2.11" in result.stdout


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "UniFi Protect Bridge doctor" in result.stdout
    assert "integration: ok" in result.stdout
    assert "HA_TOKEN: missing" in result.stdout


def test_integration_check() -> None:
    result = runner.invoke(app, ["integration", "check"])
    assert result.exit_code == 0
    assert "manifest domain" in result.stdout
    assert "Status: ok" in result.stdout


def test_integration_manifest_json() -> None:
    result = runner.invoke(app, ["integration", "manifest", "--json"])
    assert result.exit_code == 0
    manifest = json.loads(result.stdout)
    assert manifest["domain"] == "unifi_protect_bridge"
    assert manifest["version"] == "0.2.11"


def test_webhook_normalize_redacts_device_ids_by_default(tmp_path) -> None:
    payload_file = tmp_path / "webhook.json"
    payload_file.write_text(
        json.dumps(
            {
                "timestamp": 1775860000000,
                "alarm": {
                    "name": "Driveway person",
                    "sources": [{"device": "84:78:48:28:72:5C"}],
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["webhook", "normalize", "--file", str(payload_file), "--query", "source=person"],
    )

    assert result.exit_code == 0
    assert "primary_detection_type: person" in result.stdout
    assert "device_count: 1" in result.stdout
    assert "84784828725C" not in result.stdout


def test_automation_render_redacts_webhook_url() -> None:
    result = runner.invoke(
        app,
        [
            "automation",
            "render",
            "person",
            "--device",
            "84:78:48:28:72:5C",
            "--webhook-url",
            "https://ha.example/api/webhook/secret?source=person&token=secret",
        ],
    )

    assert result.exit_code == 0
    assert "name: UniFi Protect Bridge: person" in result.stdout
    assert "/api/webhook/<webhook_id>" in result.stdout
    assert "token=%3Credacted%3E" in result.stdout
    assert "secret?source" not in result.stdout


def test_automation_inspect_groups_duplicates_without_claiming_user_webhooks(
    tmp_path,
) -> None:
    automations_file = tmp_path / "automations.json"
    automations_file.write_text(
        json.dumps(
            [
                {
                    "id": "current",
                    "name": "UniFi Protect Bridge: person",
                    "enable": True,
                },
                {
                    "id": "legacy",
                    "name": "HA Protect Bridge: person",
                    "enable": True,
                },
                {
                    "id": "user",
                    "name": "User managed person webhook",
                    "actions": [
                        {
                            "type": "HTTP_REQUEST",
                            "metadata": {"url": "https://ha/api/webhook/abc?source=person"},
                        }
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["automation", "inspect", "--file", str(automations_file)])

    assert result.exit_code == 0
    assert "total: 3" in result.stdout
    assert "managed: 2" in result.stdout
    assert "unmanaged: 1" in result.stdout
    assert "person: keep current (current), duplicates=1" in result.stdout


def test_protect_automations_alias_reports_duplicates(tmp_path) -> None:
    automations_file = tmp_path / "automations.json"
    automations_file.write_text(
        json.dumps(
            [
                {"id": "current", "name": "UniFi Protect Bridge: person"},
                {"id": "legacy", "name": "HA Protect Bridge: person"},
                {"id": "user", "name": "User managed person webhook"},
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["protect", "automations", "--file", str(automations_file)])

    assert result.exit_code == 0
    assert "Bridge-managed: 2" in result.stdout
    assert "User-owned/ignored: 1" in result.stdout
    assert "person: 1 duplicate" in result.stdout


def test_protect_cameras_from_bootstrap(tmp_path) -> None:
    bootstrap_file = tmp_path / "bootstrap.json"
    bootstrap_file.write_text(json.dumps(_bootstrap()), encoding="utf-8")

    result = runner.invoke(app, ["protect", "cameras", "--bootstrap", str(bootstrap_file)])

    assert result.exit_code == 0
    assert "NVR: Test NVR" in result.stdout
    assert "Cameras: 2" in result.stdout
    assert "Driveway" in result.stdout
    assert "person" in result.stdout
    assert "ring" in result.stdout


def test_bridge_sources() -> None:
    result = runner.invoke(app, ["bridge", "sources"])
    assert result.exit_code == 0
    assert "license_plate_of_interest: license plate of interest" in result.stdout
    assert "audio_alarm_smoke: smoke alarm" in result.stdout


def test_bridge_plan_from_bootstrap_does_not_print_webhook_url(tmp_path) -> None:
    bootstrap_file = tmp_path / "bootstrap.json"
    bootstrap_file.write_text(json.dumps(_bootstrap()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "bridge",
            "plan",
            "--bootstrap",
            str(bootstrap_file),
            "--webhook-url",
            "https://ha.example/api/webhook/secret",
        ],
    )

    assert result.exit_code == 0
    assert "Webhook URL: set" in result.stdout
    assert "https://ha.example" not in result.stdout
    assert "person: 1 camera" in result.stdout


def test_bridge_plan_is_dry_run_and_redacts_webhook_url() -> None:
    result = runner.invoke(
        app,
        [
            "bridge",
            "plan",
            "person",
            "--device",
            "84:78:48:28:72:5C",
            "--webhook-url",
            "https://ha.example/api/webhook/secret",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run only. No Protect changes were made." in result.stdout
    assert "device_count: 1" in result.stdout
    assert "https://ha.example" not in result.stdout


def test_bridge_plan_requires_device() -> None:
    result = runner.invoke(
        app,
        ["bridge", "plan", "person", "--webhook-url", "https://ha.example/api/webhook/secret"],
    )
    assert result.exit_code == 1
    assert "At least one --device value is required." in result.stderr


def test_cli_detection_metadata_matches_integration() -> None:
    assert CLI_KNOWN_DETECTION_TYPES == KNOWN_DETECTION_TYPES
    assert CLI_SOURCE_LABELS == SOURCE_LABELS


def _bootstrap() -> dict[str, object]:
    return {
        "nvr": {"name": "Test NVR"},
        "cameras": [
            {
                "id": "camera-1",
                "mac": "84:78:48:28:72:5C",
                "name": "Driveway",
                "marketName": "G5 Bullet",
                "featureFlags": {"isDoorbell": False},
                "smartDetectSettings": {
                    "objectTypes": ["person", "vehicle", "licensePlate"],
                    "audioTypes": ["alrmSmoke"],
                },
            },
            {
                "id": "camera-2",
                "mac": "84:78:48:28:72:5D",
                "name": "Doorbell",
                "featureFlags": {"isDoorbell": True},
                "smartDetectSettings": {"objectTypes": ["package"], "audioTypes": []},
            },
        ],
    }
