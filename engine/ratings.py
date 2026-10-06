# -*- coding: utf-8 -*-
"""Operational Suitability: thresholds + a sample of conditions -> a rating.

TERMINOLOGY - this is load-bearing, not cosmetic. What this module produces is
CariCOOS "Operational Suitability", with the levels Favorable / Marginal /
Unfavorable / No data. It is NOT an advisory, a warning or a watch. Those are
official National Weather Service product names; on these pages they appear only
inside verbatim NWS quotes, in their own panel, attributed to NWS. Active NWS
products are DELIBERATELY not fed into the scoring here - suitability is computed
from observations and forecast numbers alone, and the NWS panel stands beside it
rather than silently moving it.

No threshold is hardcoded. Every number comes from config/thresholds.tsv, which
methods.html renders verbatim (including its `source` column), so the published
methodology cannot drift away from what this file actually does.
"""
import os
from dataclasses import dataclass

from . import derive as D

FAVORABLE = "favorable"
MARGINAL = "marginal"
UNFAVORABLE = "unfavorable"
NODATA = "nodata"
#: no threshold in the policy covers this vessel class at this kind of place.
#: Distinct from NODATA on purpose - "we hold no numbers" and "we hold numbers but
#: publish no limits for this combination" are different statements, and blurring
#: them would let a policy gap masquerade as a data outage.
NOTRATED = "notrated"

#: worst-first ordering used to combine per-variable ratings
SEVERITY = {NOTRATED: -2, NODATA: -1, FAVORABLE: 0, MARGINAL: 1, UNFAVORABLE: 2}

FIELDS = ["cls", "var", "dir", "marginal", "unfavorable", "unit", "applies_to",
          "source", "notes"]


@dataclass(frozen=True)
class Threshold:
    cls: str
    var: str
    dir: str          # 'high' = larger is worse; 'low' = smaller is worse
    marginal: float
    unfavorable: float
    unit: str
    applies_to: tuple  # ('*',) or ('port', 'inlet', ...) or ('route',)
    source: str
    notes: str

    @property
    def specific(self):
        """True when this row names actual site kinds rather than '*'. A kind-specific
        row wins over the catch-all for the same (class, var) - so an inlet uses the
        inlet wave limit, not the general one."""
        return "*" not in self.applies_to


@dataclass(frozen=True)
class Rating:
    status: str
    driver: str        # the variable that decided it, e.g. 'gust_kt'
    value: float       # that variable's value, in the threshold's canonical unit
    limit: float       # the limit it crossed (None when Favorable)
    unit: str
    source: str        # citation for the limit, shown on methods.html
    reasons: tuple     # every (var, status, value, limit, unit) evaluated


def load_thresholds(base=None):
    """config/thresholds.tsv -> list[Threshold]."""
    base = base or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config", "thresholds.tsv")
    out = []
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        if f[0] == "class":          # header row
            continue
        if len(f) != len(FIELDS):
            raise SystemExit(
                f"thresholds.tsv:{lineno}: expected {len(FIELDS)} fields, got {len(f)}")
        try:
            marg, unfav = float(f[3]), float(f[4])
        except ValueError:
            raise SystemExit(f"thresholds.tsv:{lineno}: non-numeric limits: {f[3]!r} {f[4]!r}")
        if f[2] not in ("high", "low"):
            raise SystemExit(f"thresholds.tsv:{lineno}: dir must be high|low, got {f[2]!r}")
        if f[2] == "high" and not marg <= unfav:
            raise SystemExit(f"thresholds.tsv:{lineno}: dir=high needs marginal <= unfavorable")
        if f[2] == "low" and not marg >= unfav:
            raise SystemExit(f"thresholds.tsv:{lineno}: dir=low needs marginal >= unfavorable")
        out.append(Threshold(
            cls=f[0], var=f[1], dir=f[2], marginal=marg, unfavorable=unfav, unit=f[5],
            applies_to=tuple(x.strip() for x in f[6].split(",") if x.strip()),
            source=f[7], notes=f[8]))
    if not out:
        raise SystemExit("thresholds.tsv: no rows")
    return out


def applicable(thresholds, cls, kind):
    """Thresholds for one vessel class at one site kind, most specific per variable.

    A row naming the kind ('inlet') beats the catch-all ('*') for the same variable,
    so a site only ever gets one limit per variable.
    """
    hits = {}
    for th in thresholds:
        if th.cls != cls:
            continue
        if "*" not in th.applies_to and kind not in th.applies_to:
            continue
        cur = hits.get(th.var)
        if cur is None or (th.specific and not cur.specific):
            hits[th.var] = th
    return hits


def prepare_sample(raw, kind=None, track_deg=None, roll_period_s=None, speed_kt=None,
                   depth_m=None):
    """Raw observed/forecast numbers -> the canonical variables thresholds.tsv names.

    `raw` may contain: hs_m, tp_s, dp_deg (waves from), wind_kt, gust_kt, wdir_deg
    (wind from), curr_kt, curr_to_deg. Anything absent stays absent - a missing
    input must never silently become a passing value.
    """
    s = {k: v for k, v in raw.items() if v is not None}
    hs, tp = s.get("hs_m"), s.get("tp_s")

    if "steepness" not in s:
        v = D.steepness(hs, tp)
        if v is not None:
            s["steepness"] = v

    # Long-period swell is only a berth-ranging signal at long periods. Below the
    # cutoff the variable is NOT EVALUATED (absent), which is different from - and
    # must not be confused with - a passing value.
    if hs is not None and tp is not None and tp >= 14.0:
        s["lp_swell_m"] = hs

    if track_deg is not None and hs is not None and s.get("dp_deg") is not None:
        s["hs_beam_m"] = D.beam_component(hs, track_deg, s["dp_deg"])
        # speed_kt == 0 is a VALID speed (hove-to, at anchor, drifting) and a vessel
        # can roll in resonance at zero speed, so this must test for None rather
        # than truthiness.
        if roll_period_s and speed_kt is not None and tp:
            te = D.encounter_period(tp, speed_kt, track_deg, s["dp_deg"], depth_m)
            rr = D.roll_ratio(te, roll_period_s)
            if rr is not None:
                s["roll_ratio"] = rr
                s["te_s"] = te

    if "wind_vs_curr" not in s and {"wind_kt", "wdir_deg", "curr_kt", "curr_to_deg"} <= s.keys():
        s["wind_vs_curr"] = D.wind_vs_current(
            s["wind_kt"], s["wdir_deg"], s["curr_kt"], s["curr_to_deg"])

    return s


def rate_one(value, th):
    """One variable against one threshold."""
    if value is None:
        return NODATA
    if th.dir == "high":
        if value >= th.unfavorable:
            return UNFAVORABLE
        if value >= th.marginal:
            return MARGINAL
        return FAVORABLE
    # dir == 'low': smaller is worse (roll resonance)
    if value <= th.unfavorable:
        return UNFAVORABLE
    if value <= th.marginal:
        return MARGINAL
    return FAVORABLE


def exceedance(value, limit, dir_):
    """How far past its limit a variable is, as a ratio, for driver tie-breaking.
    0 when the limit was not crossed. Direction-aware, so roll_ratio (dir=low)
    compares the right way round."""
    if value is None or limit is None:
        return 0.0
    if dir_ == "high":
        return (value / limit) if limit else 0.0
    return (limit / value) if value else float("inf")


def rate(sample, cls, kind, thresholds):
    """Worst-case rating across every applicable variable present in `sample`.

    Returns Rating(status=NODATA) when nothing could be evaluated - never a
    default Favorable, because 'we have no data' and 'conditions are fine' are
    opposite messages to a mariner.
    """
    ths = applicable(thresholds, cls, kind)
    if not ths:
        return Rating(NOTRATED, None, None, None, None, "", ())
    reasons, worst, chosen, chosen_ex = [], NODATA, None, -1.0
    for var, th in sorted(ths.items()):
        v = sample.get(var)
        if v is None:
            continue
        st = rate_one(v, th)
        lim = th.unfavorable if st == UNFAVORABLE else (th.marginal if st == MARGINAL else None)
        reasons.append((var, st, v, lim, th.unit))
        # Ties are broken by how far past the limit the variable actually is, not by
        # variable name: when 1.4 m of sea at 5 s trips both the height and the
        # steepness limits, the mariner needs to be told it is the steepness.
        ex = exceedance(v, lim, th.dir)
        if SEVERITY[st] > SEVERITY[worst] or (SEVERITY[st] == SEVERITY[worst] and ex > chosen_ex):
            worst, chosen, chosen_ex = st, (var, v, lim, th.unit, th.source), ex

    if chosen is None:
        return Rating(NODATA, None, None, None, None, "", tuple(reasons))
    var, v, lim, unit, src = chosen
    return Rating(worst, var, v, lim, unit, src, tuple(reasons))


def worst_of(ratings):
    """Combine several ratings (e.g. every class at a site) into one headline."""
    best = NODATA
    for r in ratings:
        st = r.status if isinstance(r, Rating) else r
        if SEVERITY[st] > SEVERITY[best]:
            best = st
    return best
