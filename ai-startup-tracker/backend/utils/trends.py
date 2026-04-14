"""
Trend velocity computation from GitHub repo snapshots.

Computes 7-day deltas and a composite trend_score for each repo
by comparing current metrics against the nearest prior snapshot.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("trends")


def _find_prior_snapshot(
    session: Session,
    repo_full_name: str,
    current_time: datetime,
    lookback_days: int = 7,
) -> Optional[Dict]:
    """
    Find the nearest snapshot for a repo that is at least `lookback_days`
    old relative to `current_time`. Returns a dict of metrics or None.
    """
    from backend.db.models import GithubRepoSnapshot

    # Make current_time UTC-aware for safe arithmetic
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    cutoff = current_time - timedelta(days=lookback_days)

    prior = (
        session.query(GithubRepoSnapshot)
        .filter(
            GithubRepoSnapshot.repo_full_name == repo_full_name,
            GithubRepoSnapshot.collected_at <= cutoff,
        )
        .order_by(GithubRepoSnapshot.collected_at.desc())
        .first()
    )
    if prior:
        return {
            "stars": prior.stars or 0,
            "forks": prior.forks or 0,
            "open_issues": prior.open_issues or 0,
            "collected_at": prior.collected_at,
        }
    return None


def compute_deltas(
    current_stars: int,
    current_forks: int,
    current_issues: int,
    prior: Optional[Dict],
) -> Tuple[int, int, int]:
    """
    Compute 7-day deltas. Returns (stars_delta, forks_delta, issues_delta).
    If no prior snapshot exists, deltas are 0.
    """
    if not prior:
        return (0, 0, 0)
    return (
        current_stars - (prior.get("stars") or 0),
        current_forks - (prior.get("forks") or 0),
        current_issues - (prior.get("open_issues") or 0),
    )


def _to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Return dt as timezone-aware UTC datetime (or None)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_trend_score(
    stars_delta: int,
    forks_delta: int,
    issues_delta: int,
    pushed_at: Optional[datetime],
    all_deltas: Optional[Dict[str, List[int]]] = None,
) -> float:
    """
    Compute a composite trend score (0..1).

    Formula:
      0.45 * normalized(stars_7d_delta) +
      0.20 * normalized(forks_7d_delta) +
      0.15 * normalized(issues_7d_delta) +
      0.20 * freshness_bonus

    Normalization: min-max within the current batch.
    If all_deltas is provided, uses those for normalization context.
    Otherwise returns a raw weighted sum (useful for single-repo scoring).
    """
    # Freshness bonus: 1.0 if pushed within last 7 days, decays linearly to 0 at 30 days
    freshness = 0.0
    pushed_at_utc = _to_utc_aware(pushed_at)

    if pushed_at_utc:
        now_utc = datetime.now(timezone.utc)
        days_since = (now_utc - pushed_at_utc).total_seconds() / 86400.0

        # Guard against weird future timestamps
        if days_since < 0:
            days_since = 0.0

        if days_since <= 7:
            freshness = 1.0
        elif days_since <= 30:
            freshness = max(0.0, 1.0 - (days_since - 7) / 23.0)

    if all_deltas:
        stars_norm = _min_max_normalize(stars_delta, all_deltas.get("stars", [0]))
        forks_norm = _min_max_normalize(forks_delta, all_deltas.get("forks", [0]))
        issues_norm = _min_max_normalize(issues_delta, all_deltas.get("issues", [0]))
    else:
        # Without batch context, use log-scaled approximation
        stars_norm = min(1.0, max(0.0, stars_delta / 100.0)) if stars_delta > 0 else 0.0
        forks_norm = min(1.0, max(0.0, forks_delta / 30.0)) if forks_delta > 0 else 0.0
        issues_norm = min(1.0, max(0.0, issues_delta / 20.0)) if issues_delta > 0 else 0.0

    score = (
        0.45 * stars_norm +
        0.20 * forks_norm +
        0.15 * issues_norm +
        0.20 * freshness
    )
    return round(min(1.0, max(0.0, score)), 4)


def _min_max_normalize(value: int, all_values: List[int]) -> float:
    """Min-max normalize a value within a list. Returns 0..1."""
    if not all_values:
        return 0.0
    lo = min(all_values)
    hi = max(all_values)
    if hi == lo:
        return 0.5 if value > 0 else 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def compute_batch_trends(
    session: Session,
    snapshots: List,
    lookback_days: int = 7,
) -> None:
    """
    Compute velocity deltas and trend scores for a batch of snapshots
    (already inserted in the current session but not yet committed).

    Mutates snapshot objects in-place with computed deltas and trend_score.
    """
    # First pass: compute deltas for each snapshot
    all_stars_deltas = []
    all_forks_deltas = []
    all_issues_deltas = []
    delta_map: Dict[int, Tuple[int, int, int]] = {}

    for snap in snapshots:
        prior = _find_prior_snapshot(
            session, snap.repo_full_name,
            snap.collected_at, lookback_days,
        )
        sd, fd, iss_d = compute_deltas(
            snap.stars or 0, snap.forks or 0, snap.open_issues or 0,
            prior,
        )
        snap.stars_7d_delta = sd
        snap.forks_7d_delta = fd
        snap.issues_7d_delta = iss_d

        all_stars_deltas.append(sd)
        all_forks_deltas.append(fd)
        all_issues_deltas.append(iss_d)
        delta_map[id(snap)] = (sd, fd, iss_d)

    # Second pass: compute normalized trend scores
    batch_deltas = {
        "stars": all_stars_deltas,
        "forks": all_forks_deltas,
        "issues": all_issues_deltas,
    }

    for snap in snapshots:
        sd, fd, iss_d = delta_map[id(snap)]
        snap.trend_score = compute_trend_score(
            sd, fd, iss_d,
            snap.pushed_at,
            all_deltas=batch_deltas,
        )

    logger.info(
        f"Computed trends for {len(snapshots)} snapshots "
        f"(max stars_delta={max(all_stars_deltas, default=0)}, "
        f"max trend_score={max((s.trend_score or 0) for s in snapshots) if snapshots else 0:.3f})"
    )
