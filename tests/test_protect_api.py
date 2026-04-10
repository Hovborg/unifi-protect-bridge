from custom_components.unifi_protect_bridge.protect_api import ProtectApiClient


def test_protect_api_client_accepts_custom_timeout() -> None:
    client = ProtectApiClient(
        "https://protect.example",
        "user",
        "secret",
        True,
        timeout_seconds=7.5,
    )

    assert client._timeout_seconds == 7.5
