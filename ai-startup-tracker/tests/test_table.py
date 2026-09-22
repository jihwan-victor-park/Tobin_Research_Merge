"""Tests for the shared public-table renderer.

Two things matter here beyond looks. The renderer puts database text into the
DOM, so it has to escape; and it caps how many rows it draws, so the caller
has to be able to tell when it capped.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pandas as pd

from frontend import table


def _render(df, **kw) -> tuple[str, int]:
    with patch("frontend.table.st.markdown") as md:
        n = table.render(df, **kw)
    return (md.call_args[0][0] if md.call_args else ""), n


class TestMarkup:
    def test_roles_become_classes(self):
        df = pd.DataFrame([{"Who": "Acme", "Where": "Berlin", "N": 1234}])
        html, _ = _render(df, roles={"Who": table.STRONG, "Where": table.MUTED,
                                     "N": table.NUMBER})
        assert '<td class="strong">Acme</td>' in html
        assert '<td class="mut">Berlin</td>' in html
        assert '<td class="num">1,234</td>' in html

    def test_number_headers_are_right_aligned_too(self):
        html, _ = _render(pd.DataFrame([{"N": 5}]), roles={"N": table.NUMBER})
        assert '<th class="num">N</th>' in html

    def test_decimals_keep_one_place(self):
        html, _ = _render(pd.DataFrame([{"N": 12.25}]), roles={"N": table.NUMBER})
        assert "12.2" in html or "12.3" in html

    def test_score_renders_as_a_rule_and_a_number(self):
        html, _ = _render(pd.DataFrame([{"S": 0.42}]), roles={"S": table.BAR})
        assert 'class="v2-bar"' in html and "42%" in html and "0.42" in html

    def test_missing_values_read_as_a_dash(self):
        html, _ = _render(pd.DataFrame([{"A": None, "B": float("nan")}]))
        assert html.count("—") == 2

    def test_widths_reach_the_colgroup(self):
        html, _ = _render(pd.DataFrame([{"A": 1, "B": 2}]), widths={"A": "70%"})
        assert '<col style="width:70%">' in html


class TestSafety:
    def test_database_text_is_escaped(self):
        df = pd.DataFrame([{"Description": "<script>alert(1)</script> & co"}])
        html, _ = _render(df)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html and "&amp;" in html

    def test_column_names_are_escaped(self):
        html, _ = _render(pd.DataFrame([{"<b>x</b>": 1}]))
        assert "<b>x</b>" not in html


class TestCaps:
    def test_caps_rows_and_reports_how_many_it_drew(self):
        df = pd.DataFrame({"A": range(50)})
        html, n = _render(df, max_rows=10)
        assert n == 10
        assert html.count("<tr>") == 11          # ten rows plus the header

    def test_reports_the_full_count_when_it_fits(self):
        _, n = _render(pd.DataFrame({"A": range(4)}), max_rows=10)
        assert n == 4

    def test_scroll_container_only_when_a_height_is_given(self):
        assert "scroll" in _render(pd.DataFrame({"A": [1]}), height=300)[0]
        assert "scroll" not in _render(pd.DataFrame({"A": [1]}))[0]


class TestEmpty:
    def test_empty_frame_says_so_and_draws_nothing(self):
        html, n = _render(pd.DataFrame(), empty="No rows yet.")
        assert n == 0
        assert "No rows yet." in html and "<table" not in html
