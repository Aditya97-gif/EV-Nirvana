"""
tests/test_requirement.py — Tests for charger requirement formula.
"""
import math
import pytest
from pipeline.analytics.requirement import required_chargers


class TestRequiredChargers:
    def test_basic(self):
        # 1000 EVs, 30% public, 8 kWh/day, 30 kW DC, 15% util, 20h, 90% eff
        req = required_chargers(1000, 0.30, 8.0, 30, 0.15, 20, 0.90)
        # daily_energy = 1000 * 0.30 * 8 = 2400 kWh
        # per charger = 30 * 0.15 * 20 * 0.90 = 81 kWh
        # required = ceil(2400 / 81) = ceil(29.6) = 30
        assert req == 30

    def test_zero_evs(self):
        assert required_chargers(0, 0.30, 8.0, 30, 0.15, 20, 0.90) == 0

    def test_ceiling(self):
        # Ensure we always round up
        req = required_chargers(100, 1.0, 1.0, 10, 1.0, 1.0, 1.0)
        energy = 100 * 1.0 * 1.0  # 100
        per_charger = 10 * 1.0 * 1.0 * 1.0  # 10
        expected = math.ceil(energy / per_charger)  # 10
        assert req == expected

    def test_zero_charger_kw(self):
        assert required_chargers(1000, 0.30, 8.0, 0, 0.15, 20, 0.90) == 0
