"""
Tests für den Discord-Webhook-Versand (alerts/discord.py).

Mockt httpx — testet Rate-Limit-, Retry- und Fehlerpfade ohne Netzwerk.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from wsb_crawler.alerts import discord as discord_mod


def _response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    if status_code >= 400 and status_code != 429:
        resp.raise_for_status.side_effect = RuntimeError(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _client_ctx(post_return=None, post_side_effect=None, patch_return=None):
    """Baut einen async-Context-Manager der einen gemockten httpx-Client liefert."""
    client = MagicMock()
    if post_side_effect is not None:
        client.post = AsyncMock(side_effect=post_side_effect)
    elif post_return is not None:
        client.post = AsyncMock(return_value=post_return)
    if patch_return is not None:
        client.patch = AsyncMock(return_value=patch_return)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSendWebhook:
    async def test_success(self):
        with patch(
            "wsb_crawler.alerts.discord.httpx.AsyncClient",
            return_value=_client_ctx(post_return=_response(204)),
        ):
            result = await discord_mod._send_webhook({"content": "hi"}, "https://wh")
        assert result is True

    async def test_success_with_wait_returns_id(self):
        resp = _response(200, {"id": "12345"})
        with patch(
            "wsb_crawler.alerts.discord.httpx.AsyncClient",
            return_value=_client_ctx(post_return=resp),
        ):
            result = await discord_mod._send_webhook({"content": "hi"}, "https://wh", wait=True)
        assert result == "12345"

    async def test_rate_limit_then_success(self):
        responses = iter([_response(429, {"retry_after": 0.01}), _response(204)])

        async def _post(*a, **k):
            return next(responses)

        with (
            patch(
                "wsb_crawler.alerts.discord.httpx.AsyncClient",
                return_value=_client_ctx(post_side_effect=_post),
            ),
            patch("wsb_crawler.alerts.discord.asyncio.sleep", new=AsyncMock()),
        ):
            result = await discord_mod._send_webhook({"content": "hi"}, "https://wh")
        assert result is True

    async def test_all_attempts_fail(self):
        async def _post(*a, **k):
            raise RuntimeError("network down")

        with (
            patch(
                "wsb_crawler.alerts.discord.httpx.AsyncClient",
                return_value=_client_ctx(post_side_effect=_post),
            ),
            patch("wsb_crawler.alerts.discord.asyncio.sleep", new=AsyncMock()),
        ):
            result = await discord_mod._send_webhook({"content": "hi"}, "https://wh", retries=2)
        assert result is False


class TestEditWebhookMessage:
    async def test_edit_success(self):
        with patch(
            "wsb_crawler.alerts.discord.httpx.AsyncClient",
            return_value=_client_ctx(patch_return=_response(200)),
        ):
            result = await discord_mod._edit_webhook_message({"content": "x"}, "https://wh", "1")
        assert result is True

    async def test_edit_missing_message_returns_false(self):
        with patch(
            "wsb_crawler.alerts.discord.httpx.AsyncClient",
            return_value=_client_ctx(patch_return=_response(404)),
        ):
            result = await discord_mod._edit_webhook_message({"content": "x"}, "https://wh", "1")
        assert result is False
