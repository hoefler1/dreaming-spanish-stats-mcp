#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

# --- Konfiguration ---------------------------------------------------------

BASE = "https://app.dreaming.com/.netlify/functions"
EP_DAYS = f"{BASE}/dayWatchedTime"
EP_EXTERNAL = f"{BASE}/externalTime"
EP_USER = f"{BASE}/user"

MILESTONES_H = [50, 150, 300, 600, 1000, 1500]
PACE_WINDOWS = {"7d": 7, "30d": 30, "60d": 60, "all": None}
CACHE_TTL_SECONDS = 300  # Daten max. 5 Minuten zwischenspeichern

mcp = FastMCP("dreaming-spanish")

# --- API + Cache -----------------------------------------------------------

_cache: dict = {"ts": 0.0, "series": None, "external_s": 0, "goal_s": 0}


def _token() -> str:
    tok = os.environ.get("DS_TOKEN", "").strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    if not tok:
        raise RuntimeError(
            "Kein DS_TOKEN gesetzt. Bitte Umgebungsvariable DS_TOKEN mit dem "
            "Bearer-Token aus app.dreaming.com setzen.")
    return tok


def _fetch_json(url: str, token: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"HTTP {e.code} bei {url}. Token gültig/abgelaufen?") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Netzwerkfehler bei {url}: {e.reason}") from e


def _parse_day(raw: str) -> date:
    return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()


def _build_series(day_data: list[dict]) -> list[dict]:
    secs: dict[date, float] = {}
    goal: dict[date, bool] = {}
    for row in day_data:
        d = _parse_day(row["date"])
        secs[d] = secs.get(d, 0.0) + float(row.get("timeSeconds", 0) or 0)
        goal[d] = goal.get(d, False) or bool(row.get("goalReached", False))
    start, end = min(secs), max(secs)
    series, cur = [], start
    while cur <= end:
        series.append({"date": cur, "seconds": secs.get(cur, 0.0),
                       "goalReached": goal.get(cur, False)})
        cur += timedelta(days=1)
    return series


def _moving_avg(values: list[float], window: int) -> list[float]:
    out = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        chunk = values[lo:i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def _enrich(series: list[dict], external_seconds: int) -> list[dict]:
    secs = [r["seconds"] for r in series]
    avg7, avg30 = _moving_avg(secs, 7), _moving_avg(secs, 30)
    cum = external_seconds
    for i, r in enumerate(series):
        cum += r["seconds"]
        r["cumulative_seconds"] = cum
        r["cumulative_hours"] = cum / 3600.0
        r["avg7_min"] = avg7[i] / 60.0
        r["avg30_min"] = avg30[i] / 60.0
    return series


def _load(force: bool = False) -> dict:
    """Holt Daten (mit TTL-Cache) und liefert {series, external_s, goal_s}."""
    now = time.time()
    if (not force and _cache["series"] is not None
            and now - _cache["ts"] < CACHE_TTL_SECONDS):
        return _cache
    token = _token()
    day_data = _fetch_json(EP_DAYS, token)
    if not isinstance(day_data, list) or not day_data:
        raise RuntimeError("Keine Tagesdaten erhalten. Token korrekt?")
    try:
        external_s = int(_fetch_json(EP_EXTERNAL, token)["externalTimes"][0]["timeSeconds"])
    except (KeyError, IndexError, TypeError, ValueError):
        external_s = 0
    try:
        goal_s = int(_fetch_json(EP_USER, token)["user"]["dailyGoalSeconds"])
    except (KeyError, TypeError, ValueError):
        goal_s = 0
    series = _enrich(_build_series(day_data), external_s)
    _cache.update(ts=now, series=series, external_s=external_s, goal_s=goal_s)
    return _cache


# --- Analyse-Helfer --------------------------------------------------------

def _trailing_avg_seconds(series: list[dict], days: int | None) -> float:
    rows = series if days is None else series[-days:]
    return sum(r["seconds"] for r in rows) / len(rows) if rows else 0.0


def _streaks(series: list[dict]) -> tuple[int, int]:
    longest = run = 0
    for r in series:
        run = run + 1 if r["seconds"] > 0 else 0
        longest = max(longest, run)
    current = 0
    for r in reversed(series):
        if r["seconds"] > 0:
            current += 1
        else:
            break
    return current, longest


def _predict(series: list[dict], target_h: float, pace_s: float) -> dict:
    current_h = series[-1]["cumulative_hours"]
    last_date = series[-1]["date"]
    if current_h >= target_h:
        return {"milestone_hours": target_h, "already_reached": True,
                "current_hours": round(current_h, 1)}
    if pace_s <= 0:
        return {"milestone_hours": target_h, "already_reached": False,
                "current_hours": round(current_h, 1), "eta": None,
                "note": "Tempo ist 0 — kein Datum berechenbar."}
    remaining_h = target_h - current_h
    days = int(remaining_h * 3600 / pace_s) + 1
    return {
        "milestone_hours": target_h,
        "already_reached": False,
        "current_hours": round(current_h, 1),
        "remaining_hours": round(remaining_h, 1),
        "pace_min_per_day": round(pace_s / 60, 1),
        "days_needed": days,
        "weeks_needed": round(days / 7, 1),
        "eta": (last_date + timedelta(days=days)).isoformat(),
    }


def _fmt_hm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60}min"


# --- MCP-Tools -------------------------------------------------------------

@mcp.tool()
def progress_summary() -> str:
    """Liefert eine lesbare Zusammenfassung des Dreaming-Spanish-Fortschritts:
    Gesamtstunden, Streaks, Tempo (7/30/60 Tage, gesamt) und Meilenstein-ETAs
    unter dem 60-Tage-Tempo."""
    c = _load()
    s, ext, goal = c["series"], c["external_s"], c["goal_s"]
    total_h = s[-1]["cumulative_hours"]
    cur_streak, long_streak = _streaks(s)
    active = sum(1 for r in s if r["seconds"] > 0)
    paces = {k: _trailing_avg_seconds(s, w) for k, w in PACE_WINDOWS.items()}

    lines = [
        f"Zeitraum: {s[0]['date']} bis {s[-1]['date']} ({len(s)} Tage, {active} aktiv)",
        f"Gesamt (inkl. {_fmt_hm(ext)} extern): {total_h:.1f} Stunden",
        f"Aktuelle Serie: {cur_streak} Tage | Längste: {long_streak} Tage",
        "Tempo pro Tag — "
        f"7T: {_fmt_hm(paces['7d'])} | 30T: {_fmt_hm(paces['30d'])} | "
        f"60T: {_fmt_hm(paces['60d'])} | gesamt: {_fmt_hm(paces['all'])}",
        "Meilenstein-ETA (60-Tage-Tempo, lineare Hochrechnung):",
    ]
    for m in MILESTONES_H:
        p = _predict(s, m, paces["60d"])
        if p.get("already_reached"):
            lines.append(f"  {m} h: erreicht")
        elif p.get("eta"):
            lines.append(f"  {m} h: ~{p['eta']} (in {p['days_needed']} Tagen)")
    return "\n".join(lines)


@mcp.tool()
def progress_stats() -> dict:
    """Strukturierte Kennzahlen: aktuelle Gesamtstunden, Tempo über mehrere
    Fenster (7/30/60 Tage, gesamt) in Minuten/Tag, Streaks, aktive Tage,
    Ziel-Erreichungsquote und Datumsspanne."""
    c = _load()
    s, goal_s = c["series"], c["goal_s"]
    cur_streak, long_streak = _streaks(s)
    paces_min = {k: round(_trailing_avg_seconds(s, w) / 60, 1)
                 for k, w in PACE_WINDOWS.items()}
    goal_days = sum(1 for r in s if r["goalReached"])
    return {
        "current_hours": round(s[-1]["cumulative_hours"], 1),
        "external_hours": round(c["external_s"] / 3600, 1),
        "date_range": {"start": s[0]["date"].isoformat(),
                       "end": s[-1]["date"].isoformat(), "days": len(s)},
        "active_days": sum(1 for r in s if r["seconds"] > 0),
        "pace_min_per_day": paces_min,
        "current_streak_days": cur_streak,
        "longest_streak_days": long_streak,
        "daily_goal_min": round(goal_s / 60, 1) if goal_s else None,
        "goal_reached_days": goal_days,
        "goal_reached_rate": round(goal_days / len(s), 3),
    }


@mcp.tool()
def predict_milestone(target_hours: float, pace_window: str = "60d") -> dict:
    """Prognostiziert das Datum für einen Stunden-Meilenstein.

    target_hours: Zielwert in Stunden (z. B. 150, 300, oder beliebig).
    pace_window: Tempo-Fenster — eines von "7d", "30d", "60d", "all"
                 (Standard "60d"). Bestimmt, über wie viele letzte Tage der
                 Tagesdurchschnitt gemittelt wird.

    Hinweis: lineare Hochrechnung; reale Daten schwanken, je weiter in der
    Zukunft, desto unsicherer.
    """
    if pace_window not in PACE_WINDOWS:
        return {"error": f"pace_window muss eines sein von {list(PACE_WINDOWS)}."}
    c = _load()
    s = c["series"]
    pace_s = _trailing_avg_seconds(s, PACE_WINDOWS[pace_window])
    result = _predict(s, float(target_hours), pace_s)
    result["pace_window"] = pace_window
    return result


@mcp.tool()
def milestone_table() -> dict:
    """Alle Standard-Meilensteine (50/150/300/600/1000/1500 h) mit ETA unter
    drei Tempo-Szenarien (7, 30, 60 Tage) — gibt die Spannweite der Prognose."""
    c = _load()
    s = c["series"]
    windows = {"7d": 7, "30d": 30, "60d": 60}
    paces = {k: _trailing_avg_seconds(s, w) for k, w in windows.items()}
    table = {}
    for m in MILESTONES_H:
        table[str(m)] = {k: _predict(s, m, paces[k]).get("eta")
                         if s[-1]["cumulative_hours"] < m else "erreicht"
                         for k in windows}
    return {"current_hours": round(s[-1]["cumulative_hours"], 1),
            "eta_by_pace": table}


@mcp.tool()
def daily_data(last_n_days: int = 30) -> list[dict]:
    """Rohdaten der letzten N Tage (Standard 30): Datum, Minuten, Ziel erreicht,
    kumulierte Stunden. Für eigene Detailauswertungen."""
    c = _load()
    rows = c["series"][-max(1, last_n_days):]
    return [{
        "date": r["date"].isoformat(),
        "minutes": round(r["seconds"] / 60, 1),
        "goal_reached": r["goalReached"],
        "cumulative_hours": round(r["cumulative_hours"], 2),
    } for r in rows]


if __name__ == "__main__":
    mcp.run()  # stdio-Transport (für Claude Desktop)
