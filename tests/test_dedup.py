"""
tests/test_dedup.py — Unit tests for the deduplication logic.
"""
import math
import pytest
import pandas as pd
from pipeline.clean.dedup_chargers import (
    cluster_by_distance,
    merge_cluster,
    compute_confidence,
    attribute_completeness,
    operator_similar,
)


def make_df(records):
    return pd.DataFrame(records)


class TestHaversine:
    def test_same_point(self):
        from pipeline.clean.dedup_chargers import haversine_m
        assert haversine_m(19.0, 72.8, 19.0, 72.8) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance(self):
        from pipeline.clean.dedup_chargers import haversine_m
        # Mumbai to Pune ≈ 120 km
        d = haversine_m(19.076, 72.877, 18.520, 73.856)
        assert 115_000 < d < 135_000


class TestCluster:
    def test_two_nearby_points_same_cluster(self):
        df = make_df([
            {"lat": 19.0760, "lon": 72.8777, "id": 1, "source": "osm",
             "name": "A", "operator": "Tata", "power_kw": 7.4,
             "current_type": "AC", "connector_types": ["Type2"], "fetched_at": None},
            {"lat": 19.0761, "lon": 72.8778, "id": 2, "source": "ocm",
             "name": "A", "operator": "Tata", "power_kw": 7.4,
             "current_type": "AC", "connector_types": ["Type2"], "fetched_at": None},
        ])
        labels = cluster_by_distance(df, 75)
        assert labels[0] == labels[1]  # same cluster

    def test_distant_points_different_clusters(self):
        df = make_df([
            {"lat": 19.076, "lon": 72.877, "id": 1, "source": "osm",
             "name": "A", "operator": None, "power_kw": None,
             "current_type": None, "connector_types": [], "fetched_at": None},
            {"lat": 18.520, "lon": 73.856, "id": 2, "source": "ocm",
             "name": "B", "operator": None, "power_kw": None,
             "current_type": None, "connector_types": [], "fetched_at": None},
        ])
        labels = cluster_by_distance(df, 75)
        assert labels[0] != labels[1]


class TestMerge:
    def make_cluster(self):
        return make_df([
            {"id": 1, "source": "osm", "name": "Tata EV Charger", "operator": "Tata Power EV",
             "lat": 19.076, "lon": 72.877, "power_kw": 7.4, "current_type": "AC",
             "connector_types": ["Type2"], "fetched_at": "2024-01-01"},
            {"id": 2, "source": "ocm", "name": "Tata Power", "operator": "Tata Power EV",
             "lat": 19.0761, "lon": 72.8771, "power_kw": 7.4, "current_type": "AC",
             "connector_types": ["Type2"], "fetched_at": "2024-01-15"},
        ])

    def test_merge_picks_best(self):
        group = self.make_cluster()
        result = merge_cluster(group)
        assert result["n_sources"] == 2
        assert "Type2" in result["connector_types"]
        assert result["confidence"] > 0.5

    def test_confidence_range(self):
        for n in range(1, 5):
            c = compute_confidence(n, 1.0, 0)
            assert 0 <= c <= 1


class TestOperatorSimilarity:
    def test_same(self):
        assert operator_similar("Tata Power EV", "Tata Power EV")

    def test_similar(self):
        assert operator_similar("tata power", "Tata Power EV")

    def test_different(self):
        assert not operator_similar("ChargeZone", "BPCL")
