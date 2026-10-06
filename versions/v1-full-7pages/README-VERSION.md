# v1-full — the complete seven-page dashboard (snapshot 2026-09-22)

Kept deliberately. The live site was reduced to three pages (Conditions now,
NWS forecast, Tools) for faster reading; everything here still works and is the
place to take pages back from.

Pages in this version: index (overview), conditions_now, planner,
marine_zones, tools, methods, status.

Worth knowing what is only in here:
  planner.html   five-day departure-window grid + best-window digest
                 (engine/windows.py drives it)
  methods.html   renders config/thresholds.tsv live, including the 7 limits
                 still tagged VERIFY. If the live site drops this page, that
                 published-methodology guarantee goes with it.
  status.html    per-source fetch ages, stations down, config validation
  index.html     the overview/landing page with the per-class tally

To restore a page: copy its pages/make_<name>.py back, re-add it to marlib.NAV,
and add it to the matching run_*.sh wrapper.

Snapshot excludes config/machine.env (local paths), data/, state/, logs/.
