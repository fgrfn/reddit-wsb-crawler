"""In-memory Fortschritt des aktuell laufenden Crawl-Laufs.

Der Fortschritt ist bewusst runtime-only: nach Container-Neustart ist er weg,
aber während eines langen Laufs kann /api/status dadurch Details liefern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_current_run: dict[str, Any] | None = None
_last_run: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def start_run(run_id: str, subreddits: list[str]) -> None:
    """Startet einen neuen Progress-Snapshot."""
    global _current_run
    now = _now_iso()
    _current_run = {
        "run_id": run_id,
        "short_id": run_id[:8],
        "active": True,
        "success": None,
        "phase": "starting",
        "phase_label": "Start",
        "message": "Crawl wird vorbereitet…",
        "progress": 2,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "duration_s": 0.0,
        "subreddits": subreddits,
        "subreddit_progress": {
            sub: {"posts": 0, "comments": 0, "done": False, "error": None} for sub in subreddits
        },
        "posts_scanned": 0,
        "comments_scanned": 0,
        "tickers_found": 0,
        "candidate_count": 0,
        "active_candidate_count": 0,
        "alerts_sent": 0,
        "top_tickers": [],
        "steps": [
            {"key": "starting", "label": "Start", "done": False},
            {"key": "reddit", "label": "Reddit lesen", "done": False},
            {"key": "extract", "label": "Ticker erkennen", "done": False},
            {"key": "save", "label": "Daten speichern", "done": False},
            {"key": "analysis", "label": "Spikes analysieren", "done": False},
            {"key": "enrich", "label": "Kurse & News", "done": False},
            {"key": "alerts", "label": "Alerts senden", "done": False},
            {"key": "cleanup", "label": "Aufräumen", "done": False},
        ],
    }


def _mark_done_until(phase: str) -> None:
    if _current_run is None:
        return
    seen = False
    for step in _current_run["steps"]:
        if step["key"] == phase:
            seen = True
            step["done"] = False
        elif not seen:
            step["done"] = True


def update_run(
    *,
    phase: str | None = None,
    phase_label: str | None = None,
    message: str | None = None,
    progress: int | None = None,
    **metrics: Any,
) -> None:
    """Aktualisiert den aktuellen Lauf."""
    if _current_run is None:
        return
    if phase is not None:
        _current_run["phase"] = phase
        _mark_done_until(phase)
    if phase_label is not None:
        _current_run["phase_label"] = phase_label
    if message is not None:
        _current_run["message"] = message
    if progress is not None:
        _current_run["progress"] = max(0, min(100, progress))
    for key, value in metrics.items():
        _current_run[key] = value
    _current_run["updated_at"] = _now_iso()
    _current_run["duration_s"] = _duration_seconds(_current_run.get("started_at"))


def update_subreddit(
    subreddit: str,
    *,
    posts: int,
    comments: int,
    done: bool = False,
    error: str | None = None,
) -> None:
    """Aktualisiert den Fortschritt eines einzelnen Subreddits."""
    if _current_run is None:
        return
    progress = _current_run.setdefault("subreddit_progress", {})
    progress[subreddit] = {"posts": posts, "comments": comments, "done": done, "error": error}
    _current_run["posts_scanned"] = sum(int(v.get("posts", 0)) for v in progress.values())
    _current_run["comments_scanned"] = sum(int(v.get("comments", 0)) for v in progress.values())
    done_count = sum(1 for v in progress.values() if v.get("done"))
    total = max(1, len(progress))
    update_run(
        phase="reddit",
        phase_label="Reddit lesen",
        message=f"r/{subreddit}: {posts} Posts, {comments} Kommentare gelesen",
        progress=10 + int((done_count / total) * 30),
    )


def finish_run(*, success: bool, message: str, alerts_sent: int | None = None) -> None:
    """Schließt den aktuellen Progress-Snapshot ab."""
    global _current_run, _last_run
    if _current_run is None:
        return
    if alerts_sent is not None:
        _current_run["alerts_sent"] = alerts_sent
    _current_run["active"] = False
    _current_run["success"] = success
    _current_run["finished_at"] = _now_iso()
    _current_run["updated_at"] = _current_run["finished_at"]
    _current_run["duration_s"] = _duration_seconds(_current_run.get("started_at"))
    _current_run["progress"] = 100 if success else _current_run.get("progress", 0)
    _current_run["phase"] = "done" if success else "failed"
    _current_run["phase_label"] = "Abgeschlossen" if success else "Fehler"
    _current_run["message"] = message
    for step in _current_run.get("steps", []):
        step["done"] = success
    _last_run = dict(_current_run)
    _current_run = None


def snapshot() -> dict[str, Any] | None:
    """Gibt den aktuellen oder zuletzt abgeschlossenen Lauf zurück."""
    if _current_run is not None:
        update_run()
        return dict(_current_run)
    return dict(_last_run) if _last_run is not None else None


def _duration_seconds(started_at: str | None) -> float:
    if not started_at:
        return 0.0
    started = datetime.fromisoformat(started_at)
    return (datetime.now(tz=UTC) - started).total_seconds()
