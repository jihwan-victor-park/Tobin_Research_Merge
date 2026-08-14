"""V2 homepage — an editorial, terminal-inflected redesign of the public landing page.

Self-contained: everything here reads through the same engine and the same
canonical AI predicate the rest of the dashboard uses (``backend.db.connection``,
``backend.utils.ai_filter``). Nothing in this package writes to the database or
touches the scraper.

The V1 homepage (``pipeline_dashboard.page_home``) is untouched and still serves
the default route; this package renders only when the "Home V2" nav entry or the
``?v=2`` query parameter selects it.
"""

from . import theme, data, intelligence, components, home, shell  # noqa: F401

__all__ = ["theme", "data", "intelligence", "components", "home", "shell"]
