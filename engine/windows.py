# -*- coding: utf-8 -*-
"""Find the best departure windows in a rated forecast series.

A "window" is a run of consecutive forecast periods that never drops below a
given suitability. The CWF publishes 12-hour periods, so that is the granularity
here - deliberately, rather than interpolating to 3-hourly and implying a
precision the source does not have.
"""
import datetime as dt

from .ratings import FAVORABLE, MARGINAL, SEVERITY


def _t(iso):
    return dt.datetime.fromisoformat(iso)


def windows(series, allow=FAVORABLE, min_hours=6.0):
    """Runs of periods no worse than `allow`.

    `series` is a list of {'start_utc','end_utc','status',...} in time order.
    Returns [{'start_utc','end_utc','hours','worst','periods'}], longest first.
    """
    cap = SEVERITY[allow]
    out, run = [], []

    def flush():
        if not run:
            return
        hours = (_t(run[-1]["end_utc"]) - _t(run[0]["start_utc"])).total_seconds() / 3600.0
        if hours >= min_hours:
            worst = max(run, key=lambda p: SEVERITY[p["status"]])["status"]
            out.append({"start_utc": run[0]["start_utc"], "end_utc": run[-1]["end_utc"],
                        "hours": hours, "worst": worst, "periods": len(run)})

    for p in series:
        st = p.get("status")
        if st in SEVERITY and SEVERITY[st] <= cap and SEVERITY[st] >= 0:
            run.append(p)
        else:
            flush()
            run = []
    flush()
    out.sort(key=lambda w: (-w["hours"], w["start_utc"]))
    return out


def best_windows(series, min_hours=6.0, limit=3):
    """The windows worth telling a mariner about.

    Prefers fully Favorable runs. Falls back to runs that include Marginal only
    when there is no clean window at all - and says so via 'worst', so the page
    can label it honestly rather than presenting a marginal window as a good one.
    """
    clean = windows(series, FAVORABLE, min_hours)
    if clean:
        return clean[:limit], False
    relaxed = windows(series, MARGINAL, min_hours)
    return relaxed[:limit], True
