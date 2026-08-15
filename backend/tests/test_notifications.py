import asyncio
import json
import logging
import time

import httpx
import pytest
from core.notifications import (
    NotificationConfigStore,
    NotificationEvent,
    NotificationHub,
    NotificationSettings,
)


async def public_resolver(host: str):
    return ["93.184.216.34"]


@pytest.mark.asyncio
async def test_publish_formats_and_sends_to_every_enabled_adapter():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "status": "ok"})

    config = NotificationSettings(
        app_name="TG Archive Test",
        telegram_enabled=True,
        telegram_bot_token="telegram-token",
        telegram_chat_id="-10001",
        discord_enabled=True,
        discord_webhook_url="https://discord.com/api/webhooks/1/token",
        qq_enabled=True,
        qq_api_url="http://onebot:3000",
        qq_access_token="qq-token",
        qq_target_type="group",
        qq_target_id="12345",
        webhook_enabled=True,
        webhook_url="https://hooks.example.test/archive",
        webhook_secret="hook-secret",
        events={NotificationEvent.ARCHIVE_SUCCESS},
    )
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        report = await NotificationHub(config, client=client, resolver=public_resolver).publish(
            NotificationEvent.ARCHIVE_SUCCESS,
            {
                "channel": "@demo",
                "message_id": 42,
                "file_name": "demo.mp4",
                "file_size": 1024,
                "remote_path": "/demo/2026-08/demo.mp4",
            },
        )

    assert report.delivered == 4
    assert report.failed == 0
    assert {item.channel for item in report.results} == {"telegram", "discord", "qq", "webhook"}

    telegram = next(r for r in requests if "api.telegram.org" in str(r.url))
    assert telegram.url.path.endswith("/bottelegram-token/sendMessage")
    assert json.loads(telegram.content)["chat_id"] == "-10001"

    discord = next(r for r in requests if r.headers.get("Host") == "discord.com")
    assert "demo.mp4" in json.loads(discord.content)["content"]

    qq = next(r for r in requests if "onebot" in str(r.url))
    assert qq.url.path == "/send_group_msg"
    assert json.loads(qq.content)["group_id"] == 12345
    assert qq.headers["Authorization"] == "Bearer qq-token"

    webhook = next(r for r in requests if r.headers.get("Host") == "hooks.example.test")
    webhook_payload = json.loads(webhook.content)
    assert webhook_payload["event"] == "archive.success"
    assert webhook.headers["X-TG-Archive-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_publish_skips_events_not_selected():
    config = NotificationSettings(
        telegram_enabled=True,
        telegram_bot_token="token",
        telegram_chat_id="1",
        events={NotificationEvent.ARCHIVE_FAILURE},
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        report = await NotificationHub(config, client=client, resolver=public_resolver).publish(
            NotificationEvent.ARCHIVE_SUCCESS, {"file_name": "ignored.bin"}
        )

    assert report.skipped is True
    assert report.delivered == 0


@pytest.mark.asyncio
async def test_one_failed_channel_does_not_block_other_channels():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Host") == "discord.com":
            return httpx.Response(500, text="broken")
        return httpx.Response(200, json={"ok": True})

    config = NotificationSettings(
        telegram_enabled=True,
        telegram_bot_token="token",
        telegram_chat_id="1",
        discord_enabled=True,
        discord_webhook_url="https://discord.com/api/webhooks/1/token",
        events={NotificationEvent.TEST},
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await NotificationHub(config, client=client, resolver=public_resolver).publish(NotificationEvent.TEST, {})

    assert report.delivered == 1
    assert report.failed == 1
    assert next(result for result in report.results if result.channel == "discord").error


def test_invalid_notification_urls_are_rejected():
    with pytest.raises(ValueError):
        NotificationSettings(discord_enabled=True, discord_webhook_url="file:///etc/passwd")

    with pytest.raises(ValueError):
        NotificationSettings(qq_enabled=True, qq_api_url="javascript:alert(1)")

    with pytest.raises(ValueError):
        NotificationSettings(discord_enabled=True, discord_webhook_url="https://example.com/hook")

    with pytest.raises(ValueError):
        NotificationSettings(webhook_enabled=True, webhook_url="https://user:pass@example.com/hook")

    with pytest.raises(ValueError):
        NotificationSettings(qq_enabled=True, qq_api_url="http://onebot:3000/?token=secret")

    with pytest.raises(ValueError):
        NotificationSettings(
            discord_enabled=True,
            discord_webhook_url="http://discord.com/api/webhooks/1/secret",
        )

    with pytest.raises(ValueError):
        NotificationSettings(
            webhook_enabled=True,
            webhook_url="http://hooks.example.test/archive",
        )

    with pytest.raises(ValueError):
        NotificationSettings(
            webhook_enabled=True,
            webhook_url="https://hooks.example.test:99999/archive",
        )

    with pytest.raises(ValueError):
        NotificationSettings(
            webhook_enabled=True,
            webhook_url="https://hooks.example.test/archive\r\nX-Test: injected",
        )


@pytest.mark.asyncio
async def test_generic_webhook_blocks_private_destinations_by_default():
    config = NotificationSettings(
        webhook_enabled=True,
        webhook_url="https://127.0.0.1:8080/hook",
        events={NotificationEvent.TEST},
    )

    async def private_resolver(host: str):
        return ["127.0.0.1"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        report = await NotificationHub(config, client=client, resolver=private_resolver).publish(NotificationEvent.TEST, {})

    assert report.failed == 1
    assert report.results[0].error == "destination_not_allowed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    [
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "64:ff9b:1::7f00:1",
        "2002:7f00:1::",
        "2001:0000:4136:e378:8000:63bf:3fff:fdd2",
    ],
)
async def test_generic_webhook_blocks_ipv6_addresses_that_embed_ipv4(address):
    config = NotificationSettings(
        webhook_enabled=True,
        webhook_url="https://hooks.example.test/archive",
        events={NotificationEvent.TEST},
    )

    async def embedded_resolver(host: str):
        return [address]

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as client:
        report = await NotificationHub(
            config,
            client=client,
            resolver=embedded_resolver,
        ).publish(NotificationEvent.TEST, {})

    assert report.failed == 1
    assert report.results[0].error == "destination_not_allowed"


@pytest.mark.asyncio
async def test_dns_resolution_is_bounded_by_notification_timeout():
    config = NotificationSettings(
        webhook_enabled=True,
        webhook_url="https://hooks.example.test/archive",
        events={NotificationEvent.TEST},
        timeout_seconds=0.05,
    )

    async def stalled_resolver(host: str):
        await asyncio.sleep(1)
        return ["93.184.216.34"]

    started = time.monotonic()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as client:
        report = await NotificationHub(
            config,
            client=client,
            resolver=stalled_resolver,
        ).publish(NotificationEvent.TEST, {})

    assert time.monotonic() - started < 0.5
    assert report.failed == 1
    assert report.results[0].error == "delivery_failed"


@pytest.mark.asyncio
async def test_delivery_errors_never_include_credential_urls():
    config = NotificationSettings(
        telegram_enabled=True,
        telegram_bot_token="super-secret-token",
        telegram_chat_id="1",
        events={NotificationEvent.TEST},
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        report = await NotificationHub(config, client=client, resolver=public_resolver).publish(NotificationEvent.TEST, {})

    assert report.results[0].error == "delivery_failed"
    assert "super-secret-token" not in repr(report)


@pytest.mark.asyncio
async def test_delivery_logs_never_include_secret_urls(caplog):
    config = NotificationSettings(
        telegram_enabled=True,
        telegram_bot_token="log-secret-token",
        telegram_chat_id="1",
        events={NotificationEvent.TEST},
    )
    caplog.set_level(logging.INFO)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))) as client:
        await NotificationHub(config, client=client, resolver=public_resolver).publish(NotificationEvent.TEST, {})

    assert "log-secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_generic_webhook_connects_to_validated_ip_without_second_dns_lookup():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200)

    config = NotificationSettings(
        webhook_enabled=True,
        webhook_url="https://hooks.example.test/archive",
        events={NotificationEvent.TEST},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await NotificationHub(config, client=client, resolver=public_resolver).publish(NotificationEvent.TEST, {})

    assert report.delivered == 1
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["Host"] == "hooks.example.test"
    assert requests[0].extensions["sni_hostname"] == "hooks.example.test"


@pytest.mark.asyncio
async def test_ipv6_literal_uses_bracketed_host_header():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200)

    async def global_ipv6_resolver(host: str):
        return ["2606:4700:4700::1111"]

    config = NotificationSettings(
        webhook_enabled=True,
        webhook_url="https://[2606:4700:4700::1111]/archive",
        events={NotificationEvent.TEST},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await NotificationHub(
            config,
            client=client,
            resolver=global_ipv6_resolver,
        ).publish(NotificationEvent.TEST, {})

    assert report.delivered == 1
    assert requests[0].headers["Host"] == "[2606:4700:4700::1111]"


def test_notification_config_store_round_trips_secrets_with_private_permissions(tmp_path):
    path = tmp_path / "notifications.json"
    store = NotificationConfigStore(path)
    config = NotificationSettings(
        telegram_enabled=True,
        telegram_bot_token="secret-token",
        telegram_chat_id="123",
        events={NotificationEvent.ARCHIVE_FAILURE},
    )

    store.save(config)
    restored = store.load(NotificationSettings())

    assert restored.telegram_bot_token == "secret-token"
    assert restored.events == {NotificationEvent.ARCHIVE_FAILURE}
    assert path.stat().st_mode & 0o777 == 0o600
