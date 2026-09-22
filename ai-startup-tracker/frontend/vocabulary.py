"""How the site names the databases it measures itself against.

The tracker's headline finding is a comparison: it holds companies that the
established private-market databases do not. Naming those databases states who
we buy from as much as what we found, so the site makes the claim without the
brand names — the finding is about a category of source, not about two
companies.

Every user-visible string that refers to them is composed from the constants
here, and nothing else on the site spells them out. The vendor names remain
where they are a fact about the data rather than a claim to a reader: the
`source_domain` values that drive classification, the importer scripts named
after the files they read, and the code comments explaining lineage to whoever
maintains this.

The `SOURCE_A` / `SOURCE_B` labels exist because the internal coverage views
compare the two sources against each other and need them told apart. The
mapping is deliberately not written down here.
"""
from __future__ import annotations

# ── Public prose ─────────────────────────────────────────────────────────

DATASETS = "private market datasets"
THE_DATASETS = "the private market datasets"
A_DATASET = "a private market dataset"
NO_DATASET = "no private market dataset"

# The claim itself, in the two grammars the pages need.
ABSENT = "appear in no private market dataset"        # "5,161 companies {ABSENT}"
ABSENT_SHORT = "not in any private market dataset"    # captions and subtitles

# Section kickers are set in caps by the stylesheet, so they are written in caps.
KICKER = "NOT IN ANY PRIVATE MARKET DATASET"


# Chart legends and table headers, where the full phrase does not fit.
IN_SHORT = "in a private dataset"
NOT_IN_SHORT = "not in a private dataset"


# ── Internal coverage views ──────────────────────────────────────────────

SOURCE_A = "Private dataset A"
SOURCE_B = "Private dataset B"
