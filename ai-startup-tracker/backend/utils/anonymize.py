"""Withholding company identities on the public pages.

The tracker's distinguishing coverage is companies that no commercial database
lists, and many of them are young, unannounced, or working from a grant award
that names their principal investigator. Publishing a name and a website turns
an aggregate research finding into a directory of specific small firms, which
is not what the dataset is for. The public pages therefore show what a company
does and roughly where it is, and withhold who it is.

A label has to be *stable* to be useful: a reader comparing two rows, or coming
back to the page, must see the same entry under the same name. It is derived
from the company's surrogate key by hash, so it does not move between renders,
does not depend on sort order, and does not expose the key itself.

There is deliberately no "anonymise this frame" helper here. Each public table
selects the columns it renders by name, which is a shorter and safer contract
than a denylist of columns to strip: a new identifying column added to a query
has to be named to appear, rather than having to be remembered here.

This is presentation only. Nothing here changes what is stored, and the
internal pages still show real names -- see `frontend/v2/shell.py` for which
routes count as public.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

LABEL_PREFIX = "Stealth company"


def stealth_label(key) -> str:
    """A stable, non-reversible label for one company.

    Six hex characters is enough to keep collisions out of a page of a few
    thousand rows while staying short enough to read and quote aloud.
    """
    if key is None or (isinstance(key, float) and pd.isna(key)):
        return f"{LABEL_PREFIX} —"
    digest = hashlib.blake2s(str(key).encode("utf-8"), digest_size=3).hexdigest()
    return f"{LABEL_PREFIX} {digest.upper()}"


# Grant-sourced rows carry a generated preamble naming the award programme and
# the awarding agency -- "SBIR/STTR awardee, Department of Defense (first award
# 2019). Project: ..." -- which names a collection channel in every row. The
# project text after it is the part that says what the company does.
_PROVENANCE_PREAMBLE = re.compile(
    r"^\s*(SBIR/STTR|SBIR|STTR|NIH|NSF|CORDIS|EU)\b[^.]*?"
    r"(awardee|grantee|recipient)\b[^.]*\.\s*(Project:\s*)?",
    re.IGNORECASE,
)


def strip_provenance(text) -> str:
    """Drop a description's leading "how we found this" preamble.

    Returns the remainder, or the original text when the preamble is the whole
    description -- an empty cell says less than a slightly revealing one, and
    the caller can still choose to drop the row.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    body = _PROVENANCE_PREAMBLE.sub("", str(text)).strip()
    return body or str(text).strip()

