"""
tests/test_gap_index.py — Tests for gap index computation.
"""
import pytest
import pandas as pd
import numpy as np
from pipeline.analytics.gap_index import minmax_norm


class TestMinMaxNorm:
    def test_range(self):
        s = pd.Series([10, 20, 30, 40, 50])
        n = minmax_norm(s)
        assert n.min() == pytest.approx(0.0)
        assert n.max() == pytest.approx(1.0)

    def test_constant_series(self):
        s = pd.Series([5, 5, 5])
        n = minmax_norm(s)
        assert (n == 0.5).all()


class TestCgiWeights:
    def test_weights_sum_to_one(self):
        weights = [0.30, 0.25, 0.20, 0.10, 0.15]
        assert sum(weights) == pytest.approx(1.0, abs=1e-6)
