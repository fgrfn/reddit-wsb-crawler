"""
Discord Bot mit Slash-Commands.

Ermöglicht on-demand Abfragen direkt aus Discord:
  /top [days]         → Top-Ticker der letzten N Tage
  /chart <ticker> [days] → Mention-Verlauf als ASCII-Chart im Embed
  /status             → Crawler-Status

Läuft parallel zum Scheduler (eigener asyncio-Task).
Wird nur gestartet wenn DISCORD_BOT_TOKEN gesetzt ist.
"""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from loguru import logger

from wsb_crawler.alerts.discord import send_top_tickers
from wsb_crawler.analysis.trends import get_ticker_chart_data, get_top_tickers
from wsb_crawler.storage.database import Database

# Wird beim Start gesetzt (dependency injection statt global)
_db: Database | None = None


def set_database(db: Database) -> None:
    global _db
    _db = db


def _get_db() -> Database:
    if _db is None:
        raise RuntimeError("Bot-Datenbank nicht initialisiert")
    return _db


def _build_ascii_chart(
    values: list[int],
    labels: list[str],
    height: int = 8,
    width: int = 40,
) -> str:
    """Baut einen simplen ASCII-Balken-Chart für Discord-Codeblöcke."""
    if not values or max(values) == 0:
        return "Keine Daten"

    max_val = max(values)
    bars = []
    for i, (label, val) in enumerate(zip(labels, values)):
        bar_len = int(val / max_val * width)
        bar = "█" * bar_len
        bars.append(f"{label[:5]:>5} │{bar:<{width}} {val}")

    header = f"{'':>5} │{'Mentions':^{width}}"
    sep = f"{'─'*5}┼{'─'*width}─"
    return "\n".join([header, sep] + bars)


class WSBBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()
        logger.info("Discord Bot: Slash-Commands synchronisiert")

    async def on_ready(self) -> None:
        logger.info(f"Discord Bot eingeloggt als: {self.user}")


# Bot-Instanz (lazy init)
_bot: WSBBot | None = None


def get_bot() -> WSBBot:
    global _bot
    if _bot is None:
        _bot = WSBBot()
        _register_commands(_bot)
    return _bot


def _register_commands(bot: WSBBot) -> None:
    """Registriert alle Slash-Commands."""

    @bot.tree.command(name="top", description="Top-Ticker der letzten N Tage")
    @app_commands.describe(days="Zeitraum in Tagen (Standard: 7)")
    async def top_command(interaction: discord.Interaction, days: int = 7) -> None:
        await interaction.response.defer()
        try:
            db = _get_db()
            entries = await get_top_tickers(db, days=days, limit=10)
            await send_top_tickers(entries, days=days)
            await interaction.followup.send(
                f"✅ Top-Ticker der letzten {days} Tage in Discord gepostet."
            )
        except Exception as e:
            logger.error(f"/top Fehler: {e}")
            await interaction.followup.send(f"❌ Fehler: {e}")

    @bot.tree.command(name="chart", description="Mentions-Verlauf eines Tickers")
    @app_commands.describe(
        ticker="Ticker-Symbol (z.B. GME)",
        days="Zeitraum in Tagen (Standard: 30)",
    )
    async def chart_command(
        interaction: discord.Interaction, ticker: str, days: int = 30
    ) -> None:
        await interaction.response.defer()
        ticker = ticker.upper().replace("$", "")
        try:
            db = _get_db()
            history = await get_ticker_chart_data(db, ticker, days=days)

            if not history.mention_counts:
                await interaction.followup.send(
                    f"Keine Daten für **${ticker}** in den letzten {days} Tagen."
                )
                return

            # Max. 20 Datenpunkte für lesbaren Chart
            data = history.mention_counts[-20:]
            labels = [dt.strftime("%d.%m") for dt, _ in data]
            values = [count for _, count in data]

            chart = _build_ascii_chart(values, labels)
            total = sum(values)
            avg = total / len(values)

            embed = discord.Embed(
                title=f"📊 ${ticker} — Mentions letzte {days} Tage",
                description=f"```\n{chart}\n```",
                color=0xFF4500,
            )
            embed.add_field(name="Gesamt", value=str(total), inline=True)
            embed.add_field(name="∅ täglich", value=f"{avg:.1f}", inline=True)
            embed.add_field(name="Peak", value=str(max(values)), inline=True)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"/chart Fehler für {ticker}: {e}")
            await interaction.followup.send(f"❌ Fehler: {e}")

    @bot.tree.command(name="status", description="Aktueller Crawler-Status")
    async def status_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            db = _get_db()
            status = await db.get_run_status()

            last_run = (
                f"<t:{int(status.last_run_at.timestamp())}:R>"
                if status.last_run_at else "—"
            )
            duration = (
                f"{status.last_run_duration_seconds:.0f}s"
                if status.last_run_duration_seconds else "—"
            )

            embed = discord.Embed(title="💓 Crawler Status", color=0x2B2D31)
            embed.add_field(name="Letzter Lauf", value=last_run, inline=True)
            embed.add_field(name="Dauer", value=duration, inline=True)
            embed.add_field(name="Alerts gesamt", value=str(status.total_alerts_sent), inline=True)
            embed.add_field(name="Ticker getrackt", value=str(status.tracked_tickers), inline=True)
            embed.add_field(name="Läufe gesamt", value=str(status.total_runs), inline=True)
            embed.add_field(name="Status", value="🟢 Gesund" if status.is_healthy else "🔴 Fehler", inline=True)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"/status Fehler: {e}")
            await interaction.followup.send(f"❌ Fehler: {e}")


async def start_bot(token: str) -> None:
    """Startet den Discord-Bot (blockierend)."""
    bot = get_bot()
    try:
        await bot.start(token)
    except Exception as e:
        logger.error(f"Bot-Fehler: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()
