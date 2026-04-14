"""
Main entry point for the scraping agent.

Two modes:
  scout   — investigate a URL, produce a draft instruction (read-only, max 4 tool calls)
  execute — run an approved instruction for a known site (max 3 tool calls)

Usage:
  python agent/agent.py <url> [mode] [source_name]

Examples:
  python agent/agent.py https://www.seedcamp.com/companies/ scout
  python agent/agent.py https://www.ycombinator.com/companies execute yc
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(url: str, mode: str = "scout", source_name: str | None = None) -> dict:
    """
    Route to scout or execute mode based on the mode parameter.

    Args:
        url:         The URL to scrape or investigate.
        mode:        'scout' (default) or 'execute'.
        source_name: Required for execute mode — used as the 'source' field in the DB.

    Returns:
        Structured result dict.
    """
    # Input validation
    if not url or not url.startswith("http"):
        return {"success": False, "error": f"Invalid URL: '{url}'. Must start with http/https."}

    if mode not in ("scout", "execute"):
        return {"success": False, "error": f"Invalid mode: '{mode}'. Must be 'scout' or 'execute'."}

    if mode == "execute" and not source_name:
        return {"success": False, "error": "source_name is required for execute mode."}

    # Route to the appropriate mode
    if mode == "scout":
        from agent.scout import run_scout
        return run_scout(url)
    else:
        from agent.execute import run_execute
        return run_execute(url, source_name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent/agent.py <url> [mode] [source_name]")
        print("  mode: scout (default) or execute")
        print("  source_name: required for execute mode")
        sys.exit(1)

    url = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "scout"
    source_name = sys.argv[3] if len(sys.argv) > 3 else None

    result = run(url=url, mode=mode, source_name=source_name)
    print(json.dumps(result, indent=2, default=str))
