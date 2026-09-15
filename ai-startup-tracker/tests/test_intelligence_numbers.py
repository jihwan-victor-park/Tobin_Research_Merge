"""Tests for the figure guard on the answer box's narrative.

The product claim is that no number in an answer was written by a model, so
this check is load-bearing in both directions: a fabricated figure must be
caught, and a correctly quoted one must not be, because a false rejection
silently throws away a paid-for narrative and falls back to the template.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend.v2.intelligence import _numbers_check_out

FACTS = {
    "total": 15143,
    "growth": -42.9,
    "recent_range": (2022, 2024),
    "formation_by_founding_year": [{"year": 2012, "companies": 551},
                                   {"year": 2024, "companies": 1804}],
}


class TestAcceptsQuotedFigures:
    def test_exact(self):
        assert _numbers_check_out("The tracker holds 15,143 companies.", FACTS)

    def test_from_the_retrieved_context(self):
        assert _numbers_check_out("1,804 were founded in 2024.", FACTS)

    def test_signed_share_move(self):
        assert _numbers_check_out("The cohort lost 42.9% of its share.", FACTS)

    def test_hyphenated_year_range(self):
        # "2012-2024" is a range, not a negative number.
        assert _numbers_check_out("Formation ran from 2012-2024.", FACTS)

    def test_en_dash_year_range(self):
        assert _numbers_check_out("Across 2022–2024, formation held.", FACTS)


class TestRejectsInvention:
    def test_a_figure_that_is_not_there(self):
        assert not _numbers_check_out("The tracker holds 15,900 companies.", FACTS)

    def test_a_computed_figure(self):
        # 15,143 / 2 is arithmetic the model was told not to do.
        assert not _numbers_check_out("Roughly 7,571 of them are unlisted.", FACTS)
