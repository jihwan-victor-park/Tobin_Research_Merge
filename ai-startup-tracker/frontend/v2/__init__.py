"""V2 homepage — an editorial, terminal-inflected redesign of the public landing page.

Self-contained: everything here reads through the same engine and the same
canonical AI predicate the rest of the dashboard uses (``backend.db.connection``,
``backend.utils.ai_filter``). Nothing in this package writes to the database or
touches the scraper.

This package is the site. ``shell.is_active()`` returns True unless ``?v=1`` is
set, so the V1 shell (``pipeline_dashboard.page_home`` and its nav) is reachable
only at that legacy address. The other public pages still live in
``pipeline_dashboard`` and are called from ``shell._render_v1_page``.
"""

from . import (theme, stylesheet, data, guard, intelligence, briefing,  # noqa: F401
               components, home, shell)

__all__ = ["theme", "data", "guard", "intelligence", "components", "home", "shell"]
