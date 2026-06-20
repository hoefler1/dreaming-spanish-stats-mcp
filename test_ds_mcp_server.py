from unittest import TestCase
from parameterized import parameterized

import ds_mcp_server


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
