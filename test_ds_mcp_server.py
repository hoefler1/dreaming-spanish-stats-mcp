from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

from parameterized import parameterized

import ds_mcp_server


def _make_cache(seconds_per_day, goal_s=1800, external_s=0):
    """Baut ein _load()-kompatibles Cache-Dict aus einer Liste Sekunden/Tag."""
    series = []
    cum = external_s
    start = date(2026, 1, 1)
    for i, sec in enumerate(seconds_per_day):
        cum += sec
        series.append({
            "date": start + timedelta(days=i),
            "seconds": float(sec),
            "goalReached": sec >= goal_s,
            "cumulative_seconds": cum,
            "cumulative_hours": cum / 3600.0,
            "avg7_min": 0.0,
            "avg30_min": 0.0,
        })
    return {"ts": 0.0, "series": series, "external_s": external_s, "goal_s": goal_s}


class Test(TestCase):
    @parameterized.expand([
        ("case_1", [{"seconds": 20}, {"seconds": 0}], 30, True, 20),
        ("case_2", [{"seconds": 20}, {"seconds": 0}, {"seconds": 0}, {"seconds": 0}], 30, True, 20),
        ("case_3", [{"seconds": 20}, {"seconds": 0}], 30, False, 10),
        ("case_4", [{"seconds": 20}, {"seconds": 30}, {"seconds": 10}], 30, False, 20),
        ("case_5", [{"seconds": 20}, {"seconds": 30}, {"seconds": 10}], 2, False, 20),
        ("case_6", [{"seconds": 20}, {"seconds": 30}, {"seconds": 10}], 1, False, 10),
        ("leer", [], 30, False, 0.0),
    ])
    def test__trailing_avg_seconds(self, _name, series, days, only_active, expected):
        self.assertEqual(ds_mcp_server._trailing_avg_seconds(series, days, only_active), expected)


class TestOnlyActiveDaysThreading(TestCase):
    # 4 Tage: aktiv / 0 / aktiv / 0 -> Aktiv-Schnitt (60 min) doppelt so hoch
    # wie Kalender-Schnitt (30 min). So lässt sich das Durchschleifen des Flags
    # eindeutig nachweisen.
    CACHE = _make_cache([3600, 0, 3600, 0])

    def test_progress_stats_threads_flag(self):
        with patch.object(ds_mcp_server, "_load", return_value=self.CACHE):
            full = ds_mcp_server.progress_stats(only_active_days=False)
            active = ds_mcp_server.progress_stats(only_active_days=True)
        self.assertEqual(full["pace_min_per_day"]["all"], 30.0)
        self.assertEqual(active["pace_min_per_day"]["all"], 60.0)

    def test_progress_summary_threads_flag(self):
        with patch.object(ds_mcp_server, "_load", return_value=self.CACHE):
            full = ds_mcp_server.progress_summary(only_active_days=False)
            active = ds_mcp_server.progress_summary(only_active_days=True)
        self.assertIn("gesamt: 0h 30min", full)
        self.assertIn("gesamt: 1h 0min", active)

    def test_milestone_table_threads_flag(self):
        with patch.object(ds_mcp_server, "_load", return_value=self.CACHE):
            full = ds_mcp_server.milestone_table(only_active_days=False)
            active = ds_mcp_server.milestone_table(only_active_days=True)
        # Höheres Tempo -> frühere ETA fürs (noch nicht erreichte) 50h-Ziel.
        self.assertLess(active["eta_by_pace"]["50"]["60d"],
                        full["eta_by_pace"]["50"]["60d"])
