"""The sector map on the Landscape page.

A stacked bar answers "how many companies per domain". It cannot answer the
question people actually arrive with — *how is this population arranged?* —
because a bar has no room for the 150-odd clusters the taxonomy found inside
those domains, and no way to show that one domain is a single dense subject
while another is a dozen loosely related ones.

So the page draws the population: one mark per company, grouped into its
cluster, clusters grouped into their domain.

There are two ways it can get the coordinates, and they differ in what the
picture is allowed to claim.

**Measured** — `scripts/landscape_atlas.py` has run and `company_atlas` holds
an (x, y) per company, derived from the description text itself. Then distance
means similarity: near things read alike, the shape of the cloud is the shape
of the industry, and the figure is a map in the ordinary sense.

**Arranged** — no coordinates stored, so `_arrange` lays domains out as discs
and seats clusters inside them. The grouping is still real (the clusters came
from embedding descriptions in `scripts/taxonomy_build.py`) but the geometry
is furniture: distance means nothing and the caption says so.

`source_of(points)` reports which one is on screen, and the page captions
itself accordingly. Everything downstream is identical.

Positions are deterministic: the same company lands in the same place on every
render, seeded from its cluster and id. A map that reshuffles on each page load
looks like it is showing motion it does not have.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Colour ───────────────────────────────────────────────────────────────
#
# The rest of the site carries identity in a single accent hue; this is the
# one figure that needs several at once, because the whole point is telling
# domains apart. Five, not the eleven of a typical embedding atlas: beyond
# that the legend stops being readable and the hues stop being distinguishable
# to a colourblind reader. Everything past the fifth domain is grey, which is
# also how the site draws "everything else" elsewhere.
#
# Validated with the dataviz palette checker against each mode's own surface:
#
#   light  #1a56c4 #c2410c #6d28d9 #0891b2 #9d174d  on #f7f7f4  → all six PASS
#   dark   #4a8ae0 #d2703f #8f77e8 #2f9fbb #cc5f92  on #0b0d0f  → CVD WARN 6.7
#
# The dark WARN sits in the 6–8 floor band, which is legal only with a second
# encoding carrying the same information: the cluster labels drawn directly on
# the figure, which name the domain's subject matter without reference to hue.
CATEGORICAL_LIGHT = ("#1a56c4", "#c2410c", "#6d28d9", "#0891b2", "#9d174d")
CATEGORICAL_DARK = ("#4a8ae0", "#d2703f", "#8f77e8", "#2f9fbb", "#cc5f92")

NAMED_DOMAINS = len(CATEGORICAL_LIGHT)
OTHER = "Other domains"

# Drawing every mapped company sends megabytes of coordinates to the browser
# for a picture whose shape is settled long before that. The sample is
# stratified by cluster, so every cluster that exists is visible.
MAX_POINTS = 42_000


def hues(is_dark: bool) -> tuple[str, ...]:
    return CATEGORICAL_DARK if is_dark else CATEGORICAL_LIGHT


# ── Layout ───────────────────────────────────────────────────────────────


def _lobe_radii(sizes: pd.Series) -> pd.Series:
    """How much of the canvas each domain gets: area with the count, not width.

    A domain holding four times as many companies should look four times as
    big, and area is what the eye actually compares — scaling the radius
    linearly would make it sixteen times as big and swamp everything else.
    """
    return 0.42 * np.sqrt(sizes / float(sizes.max()))


def _lobe_centres(sizes: pd.Series) -> dict[str, tuple[float, float]]:
    """Largest domain in the middle, the rest packed around it.

    Laying the domains out on a ring instead left the middle of the figure
    empty and pushed the tail into a thin arc at the rim; a packed arrangement
    reads as one population with parts, which is what it is.
    """
    radii = _lobe_radii(sizes)
    names = list(sizes.index)
    centres = {names[0]: (0.0, 0.0)}
    if len(names) == 1:
        return centres

    rest = names[1:]
    # Walk the satellites around the core, each one far enough out to sit
    # clear of it, and spaced by the angle its own width subtends.
    core = float(radii.iloc[0])
    angle = 0.0
    for name in rest:
        r = float(radii[name])
        distance = core + r * 0.97
        span = 2 * np.arcsin(min(r * 1.12 / distance, 0.999))
        angle += span / 2
        centres[name] = (distance * np.cos(angle), distance * np.sin(angle))
        angle += span / 2 + 0.04
    return centres


def _sunflower(n: int) -> tuple[np.ndarray, np.ndarray]:
    """n points spread evenly over a unit disc (phyllotaxis).

    Used to seat clusters inside their domain: it fills a disc without the
    gaps and seams a grid or a ring leaves behind.
    """
    i = np.arange(n, dtype=float) + 0.5
    r = np.sqrt(i / n)
    theta = i * np.pi * (3.0 - np.sqrt(5.0))      # golden angle
    return r * np.cos(theta), r * np.sin(theta)


# How far the feathered rim strays past the nominal blob radius, as a fraction
# of it. The disc is shrunk by the same amount first, so a feathered blob
# occupies the area an unfeathered one would have and the lobe packing above
# still holds.
_FEATHER = 0.055


def _scatter_within(n: int, radius: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """n points filling a disc evenly, deterministically, with a soft rim."""
    rng = np.random.default_rng(seed)
    # sqrt of a uniform gives uniform area density; without it every blob is a
    # dense pinprick with a halo, which reads as structure that is not there.
    core = radius * (1.0 - 2 * _FEATHER)
    r = core * np.sqrt(rng.random(n))
    # Uniform density is right, but stopping it dead at `core` draws every
    # cluster as a compass-perfect circle, and a field of a hundred identical
    # discs reads as a diagram of a population rather than the population.
    # Blurring the radius with a narrow gaussian is exactly an edge blur: it
    # leaves core density untouched (a uniform field convolved with a narrow
    # kernel is still uniform away from its boundary) and dissolves the rim,
    # letting a few marks sit just outside as stragglers. The softness is
    # decorative in the same way the coordinates already are — see the module
    # docstring's table; what is real is which blob a mark belongs to.
    r = np.abs(r + rng.normal(0.0, radius * _FEATHER, n))
    theta = rng.random(n) * 2 * np.pi
    return r * np.cos(theta), r * np.sin(theta)


def source_of(points: pd.DataFrame) -> str:
    """"measured" when the coordinates came from the descriptions."""
    return "measured" if points.attrs.get("measured") else "arranged"


def layout(companies: pd.DataFrame) -> pd.DataFrame:
    """Give every company an (x, y), measuring where possible.

    `companies` needs: company_id, domain, cluster, and whatever extra columns
    the hover card wants to carry through. If it also carries non-null x and
    y — `scripts/landscape_atlas.py` has run — those are used as they are and
    nothing is invented.
    """
    if companies.empty:
        return companies.assign(x=[], y=[])

    if {"x", "y"} <= set(companies.columns):
        placed = companies[companies["x"].notna() & companies["y"].notna()].copy()
        # A partial run would mix measured and arranged points in one picture,
        # where no reader could tell which half meant anything. All or none.
        if len(placed) >= 0.6 * len(companies):
            placed[["x", "y"]] = placed[["x", "y"]].astype(float)
            placed.attrs["measured"] = True
            return placed.reset_index(drop=True)
        companies = companies.drop(columns=["x", "y"])

    return _arrange(companies)


def _arrange(companies: pd.DataFrame) -> pd.DataFrame:
    """The fallback geometry, used until the coordinates are computed.

    Three nested discs: the figure holds domain lobes, a lobe holds its
    clusters, a cluster holds its companies. Every radius goes as the square
    root of a count, so area reads as quantity at all three levels.
    """

    sizes = companies.groupby("domain", sort=False).size().sort_values(ascending=False)
    radii = _lobe_radii(sizes)
    centres = _lobe_centres(sizes)

    out = []
    for domain, grp in companies.groupby("domain", sort=False):
        cx, cy = centres[domain]
        lobe = float(radii[domain])
        counts = grp.groupby("cluster", sort=False).size().sort_values(ascending=False)
        sx, sy = _sunflower(len(counts))
        # Biggest clusters first, so they take the seats nearest the middle of
        # the lobe and the long tail fills in around them.
        for i, (cluster, n) in enumerate(counts.items()):
            blob = lobe * np.sqrt(n / float(counts.sum())) * 0.62
            blob = min(max(blob, lobe * 0.014), lobe * 0.58)
            seat = 1.0 - blob / lobe          # keep the blob inside the lobe
            px = cx + sx[i] * lobe * seat
            py = cy + sy[i] * lobe * seat
            rows = grp[grp["cluster"] == cluster]
            seed = abs(hash((str(domain), str(cluster)))) % (2**31)
            dx, dy = _scatter_within(len(rows), blob, seed)
            out.append(rows.assign(x=px + dx, y=py + dy))

    return pd.concat(out, ignore_index=True) if out else companies.assign(x=[], y=[])


# A label is a horizontal object, so whether two of them collide depends on
# how long the words are, not on how far apart the blobs are. At the figure's
# usual width one character of the label font covers roughly this much of the
# coordinate space, which runs -1..1 on both axes.
_CHAR_WIDTH = 0.0125
_LINE_HEIGHT = 0.045
MAX_LABEL_CHARS = 30


def _clip_label(text: str) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= MAX_LABEL_CHARS else t[:MAX_LABEL_CHARS - 1].rstrip() + "…"


def label_anchors(points: pd.DataFrame, limit: int = 9) -> pd.DataFrame:
    """The clusters worth naming on the figure itself.

    Only the largest few, and only where the words will not land on top of
    words already placed. The first version compared centre points against a
    fixed radius, which is the wrong test for a label: "Data Analytics &
    Business Intelligence" is three times the width of "Robotics" and overlaps
    a neighbour the short one clears easily. So each candidate is treated as
    the box it actually occupies — width from its character count — and
    rejected when that box would overlap one already on the figure.

    Candidates are considered biggest-first, so what survives is what carries
    the most companies.
    """
    if points.empty:
        return points
    cand = (points.groupby(["domain", "cluster"], sort=False)
                  .agg(x=("x", "mean"), y=("y", "mean"), n=("x", "size"))
                  .reset_index().sort_values("n", ascending=False))

    kept: list[dict] = []
    for r in cand.itertuples():
        if len(kept) >= limit:
            break
        text = _clip_label(r.cluster)
        half = len(text) * _CHAR_WIDTH / 2
        if any(abs(r.x - k["x"]) < (half + k["half"])
               and abs(r.y - k["y"]) < _LINE_HEIGHT for k in kept):
            continue
        kept.append({"domain": r.domain, "cluster": text,
                     "x": r.x, "y": r.y, "n": r.n, "half": half})
    return pd.DataFrame(kept)


# ── Figure ───────────────────────────────────────────────────────────────


def _rgba(colour: str, alpha: float) -> str:
    """`#rrggbb` -> `rgba(r,g,b,alpha)`. Anything else is passed through.

    Plotly has no way to set an annotation's background alpha except through
    the colour itself — its `opacity` applies to the whole annotation, text
    and all.
    """
    c = (colour or "").strip()
    if not (c.startswith("#") and len(c) == 7):
        return c
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return c
    return f"rgba({r},{g},{b},{alpha})"


def figure(points: pd.DataFrame, *, hue: dict[str, str], ink: str, ink_soft: str,
           context: str, surface: str, height: int = 620):
    """The map itself. One trace per domain, so the legend is the domain list.

    Marks are small and semi-transparent on purpose: at eighteen thousand
    points the useful signal is density, and opaque dots stack into flat
    silhouettes that hide how concentrated a cluster really is.
    """
    import plotly.graph_objects as go

    fig = go.Figure()
    present = set(points["domain"])
    # OTHER first, so the grey tail is painted UNDER the five named domains
    # rather than over them. `hue` arrives with OTHER appended last, and a
    # later trace draws on top — which had the largest, least informative
    # population muting every domain the figure exists to tell apart.
    order = [d for d in hue if d in present and d == OTHER]
    order += [d for d in hue if d in present and d != OTHER]

    # The sample shrinks on a smaller book, and marks tuned for eighteen
    # thousand points read as a sparse dusting at four thousand. Size and
    # opacity follow the count actually drawn, so the figure carries the same
    # weight either way.
    drawn = len(points)
    if drawn >= 30_000:
        size, alpha = 2.3, 0.55
    elif drawn >= 14_000:
        size, alpha = 3.4, 0.50
    elif drawn >= 6_000:
        size, alpha = 4.2, 0.58
    else:
        size, alpha = 5.2, 0.66

    # Draw order and legend order are not the same question, and tying them
    # together is what the OTHER-first fix above would otherwise break: the
    # tail has to be painted first but still read last. `legendrank` keeps the
    # list in the order a reader expects — biggest named domain down to the
    # catch-all — whatever sequence the traces were added in.
    rank = {d: i for i, d in enumerate(hue) if d != OTHER}
    for domain in order:
        d = points[points["domain"] == domain]
        if d.empty:
            continue
        fig.add_trace(go.Scattergl(
            x=d["x"], y=d["y"], mode="markers", name=f"{domain}  ({len(d):,})",
            legendrank=rank.get(domain, 10_000),
            marker=dict(size=size, color=hue[domain], opacity=alpha,
                        line=dict(width=0)),
            customdata=np.stack([d["label"], d["cluster"], d["capability"],
                                 d["listing"]], axis=-1),
            hovertemplate=("<b>%{customdata[0]}</b><br>"
                           "%{customdata[1]}<br>"
                           "<span>%{customdata[2]}</span><br>"
                           "%{customdata[3]}"
                           "<extra></extra>"),
        ))

    # These labels are not decoration. The dark palette's worst adjacent pair
    # separates by ΔE 6.7 under deuteranopia, which sits in the 6–8 floor band
    # — legal only where a second encoding carries the same information. The
    # cluster names ARE that encoding: they say what a blob is about without
    # reference to its hue. So they have to stay readable.
    #
    # `opacity` on an annotation fades the whole thing, text included, which
    # is what dimmed them before. The plate gets the transparency instead and
    # the type stays at full ink.
    plate = _rgba(surface, 0.70)
    for r in label_anchors(points).itertuples():
        fig.add_annotation(
            x=r.x, y=r.y, text=str(r.cluster), showarrow=False,
            font=dict(size=10.5, color=ink), bgcolor=plate, borderpad=3,
        )

    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(orientation="v", x=1.0, xanchor="right", y=1.0,
                    bgcolor=surface, bordercolor=context, borderwidth=1,
                    font=dict(size=11, color=ink_soft),
                    itemsizing="constant"),
        hoverlabel=dict(bgcolor=surface, bordercolor=context,
                        font=dict(size=11.5, color=ink)),
        xaxis=dict(visible=False, fixedrange=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False, fixedrange=False),
        dragmode="pan",
    )
    return fig


def assign_hues(domains: list[str], is_dark: bool) -> dict[str, str]:
    """Fixed order, never cycled: the top domains take the named hues and the
    rest share the context grey — so adding a domain never repaints the others."""
    palette = hues(is_dark)
    out = {}
    for i, d in enumerate(domains):
        if i < NAMED_DOMAINS:
            out[d] = palette[i]
    return out
