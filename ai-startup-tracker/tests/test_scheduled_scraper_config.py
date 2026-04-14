"""Config shape for run_scheduled_scraper (no network)."""
from pathlib import Path

import yaml


def test_registered_sites_yaml_schema():
    path = Path(__file__).resolve().parents[1] / "data" / "scrape_schedule" / "registered_sites.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert "schedule" in cfg
    assert cfg["schedule"].get("mode") in ("daily", "interval", None)
    assert "sites" in cfg
    assert isinstance(cfg["sites"], list)
