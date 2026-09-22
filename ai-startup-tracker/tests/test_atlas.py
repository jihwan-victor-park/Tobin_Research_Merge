"""Tests for the Landscape sector map.

The map's honesty rests on two properties: a company always lands in its own
cluster's blob, and it lands in the same place every time. The first is what
makes the grouping readable; the second is what stops the figure implying
motion between page loads that the data does not have.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from frontend import atlas


def _frame(n_domains=4, clusters=5, per=40):
    rows = []
    for d in range(n_domains):
        for c in range(clusters):
            for i in range(per * (d + 1)):      # domains of different sizes
                rows.append({"company_id": len(rows), "domain": f"D{d}",
                             "cluster": f"D{d} c{c}", "capability": "cap",
                             "label": f"Company {len(rows)}", "listing": "Hidden"})
    return pd.DataFrame(rows)


class TestLayout:
    def test_every_company_is_placed(self):
        df = _frame()
        out = atlas.layout(df)
        assert len(out) == len(df)
        assert out[["x", "y"]].notna().all().all()

    def test_deterministic(self):
        df = _frame()
        a = atlas.layout(df).sort_values("company_id")[["x", "y"]].to_numpy()
        b = atlas.layout(df).sort_values("company_id")[["x", "y"]].to_numpy()
        assert np.array_equal(a, b)

    def test_a_cluster_stays_together(self):
        """Each cluster is a compact blob, not smeared across its domain."""
        out = atlas.layout(_frame())
        for _, grp in out.groupby("cluster"):
            spread = np.hypot(grp["x"] - grp["x"].mean(), grp["y"] - grp["y"].mean())
            assert spread.max() < 0.25, "cluster is not compact"

    def test_bigger_domains_take_more_room(self):
        out = atlas.layout(_frame())
        extent = out.groupby("domain")[["x", "y"]].apply(
            lambda g: np.hypot(g["x"] - g["x"].mean(), g["y"] - g["y"].mean()).max())
        sizes = out.groupby("domain").size()
        assert extent.idxmax() == sizes.idxmax()

    def test_empty_frame(self):
        out = atlas.layout(pd.DataFrame(columns=["company_id", "domain", "cluster"]))
        assert out.empty


class TestLabels:
    def test_labels_do_not_collide(self):
        anchors = atlas.label_anchors(atlas.layout(_frame()))
        pts = anchors[["x", "y"]].to_numpy()
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                assert not (abs(pts[i][0] - pts[j][0]) < 0.17
                            and abs(pts[i][1] - pts[j][1]) < 0.17 * 0.42)

    def test_labels_are_the_biggest_clusters(self):
        out = atlas.layout(_frame())
        anchors = atlas.label_anchors(out)
        assert len(anchors) <= 9
        assert anchors["n"].is_monotonic_decreasing


class TestHues:
    def test_fixed_order_never_cycled(self):
        """A domain dropping out must not repaint the ones that remain."""
        full = atlas.assign_hues(["a", "b", "c", "d", "e", "f", "g"], is_dark=False)
        assert len(full) == atlas.NAMED_DOMAINS, "the tail must fall through to grey"
        fewer = atlas.assign_hues(["a", "b", "c"], is_dark=False)
        for d in fewer:
            assert fewer[d] == full[d]

    def test_each_mode_has_its_own_steps(self):
        assert set(atlas.hues(True)).isdisjoint(atlas.hues(False))
