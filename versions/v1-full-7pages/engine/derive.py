# -*- coding: utf-8 -*-
"""Derived maritime quantities. Pure functions, no I/O, no pandas - so the whole
rating core can be proven correct by tools/check_ratings.py before a byte is fetched.

DIRECTION CONVENTIONS, because mixing these up is the classic way to ship a
confidently wrong beam-sea number:

  wave_from_deg  direction the waves come FROM   (meteorological, matches buoy `dp`)
  wdir_from_deg  direction the wind comes FROM   (meteorological, matches mesonet)
  curr_to_deg    direction the current flows TOWARD (oceanographic, matches buoy `cd`)
  track_deg      the vessel's true course over ground

  rel_angle()    returns the ENCOUNTER ANGLE: the angle between the vessel's track
                 and the direction the waves are TRAVELLING TOWARD.
                   0 deg  = following sea   (waves overtaking from astern)
                  90 deg  = beam sea        (the ferry-roll case)
                 180 deg  = head sea
"""
import math

G = 9.80665          # m/s^2
KT_PER_MPS = 1.9438444924406046
M_PER_FT = 0.3048


# --------------------------------------------------------------------------
# units
# --------------------------------------------------------------------------
def mps_to_kt(v):
    return None if v is None else v * KT_PER_MPS


def kt_to_mps(v):
    return None if v is None else v / KT_PER_MPS


def m_to_ft(v):
    return None if v is None else v / M_PER_FT


def ft_to_m(v):
    return None if v is None else v * M_PER_FT


def uv_to_spd_dir(u, v):
    """(u, v) components -> (speed, direction the flow comes FROM, degrees).

    Meteorological convention, so a wind blowing toward the north (u=0, v=+1)
    is reported as coming from 180.
    """
    if u is None or v is None:
        return (None, None)
    spd = math.hypot(u, v)
    if spd == 0:
        return (0.0, 0.0)
    d = (math.degrees(math.atan2(-u, -v))) % 360.0
    return (spd, d)


# --------------------------------------------------------------------------
# angles
# --------------------------------------------------------------------------
def ang_diff(a, b):
    """smallest absolute difference between two bearings, 0..180."""
    if a is None or b is None:
        return None
    return abs((a - b + 180.0) % 360.0 - 180.0)


def rel_angle(track_deg, wave_from_deg):
    """Encounter angle: 0 = following sea, 90 = beam sea, 180 = head sea."""
    if track_deg is None or wave_from_deg is None:
        return None
    wave_toward = (wave_from_deg + 180.0) % 360.0
    return ang_diff(track_deg, wave_toward)


def exposed(wave_from_deg, arc):
    """Is wave_from_deg inside an open bearing arc like '290-070' (wraps past 360)?"""
    if wave_from_deg is None or not arc or arc == "-":
        return False
    try:
        a, b = (float(x) for x in arc.split("-"))
    except ValueError:
        return False
    d = wave_from_deg % 360.0
    a %= 360.0
    b %= 360.0
    return (a <= d <= b) if a <= b else (d >= a or d <= b)


# --------------------------------------------------------------------------
# waves
# --------------------------------------------------------------------------
def steepness(hs_m, tp_s):
    """Deep-water significant steepness  S = Hs / (1.56 * Tp^2).

    This, not Hs alone, is what makes a sea dangerous for small craft: 1.5 m at
    12 s is a comfortable swell (S=0.007); 1.5 m at 5 s is a wall of breaking
    chop (S=0.038). WMO-No. 702, Guide to Wave Analysis and Forecasting.
    """
    if hs_m is None or tp_s is None or tp_s <= 0:
        return None
    return hs_m / (1.56 * tp_s * tp_s)


def wave_celerity(t_s, depth_m=None):
    """Phase speed (m/s). Deep water C = gT/2pi; shallower than L/2 uses the
    dispersion relation, solved by fixed-point iteration."""
    if t_s is None or t_s <= 0:
        return None
    c0 = G * t_s / (2.0 * math.pi)
    if depth_m is None or depth_m <= 0:
        return c0
    l0 = c0 * t_s
    if depth_m >= 0.5 * l0:
        return c0
    l = l0
    for _ in range(64):
        nl = l0 * math.tanh(2.0 * math.pi * depth_m / l)
        if abs(nl - l) < 1e-9:
            l = nl
            break
        l = nl
    return l / t_s


def beam_component(hs_m, track_deg, wave_from_deg):
    """The part of the sea that arrives on the beam: Hs * |sin(encounter angle)|.

    Maximal at 90 deg (pure beam), zero in a pure following or head sea. This is
    the number that decides whether a ferry crossing is comfortable.
    """
    a = rel_angle(track_deg, wave_from_deg)
    if hs_m is None or a is None:
        return None
    return abs(hs_m * math.sin(math.radians(a)))


def head_component(hs_m, track_deg, wave_from_deg):
    """The along-track part of the sea: Hs * |cos(encounter angle)|. Drives
    slamming and speed loss rather than roll."""
    a = rel_angle(track_deg, wave_from_deg)
    if hs_m is None or a is None:
        return None
    return abs(hs_m * math.cos(math.radians(a)))


def encounter_period(t_s, speed_kt, track_deg, wave_from_deg, depth_m=None):
    """Wave period as the moving vessel feels it (s).

        Te = T / |1 - (V/C) * cos(mu)|

    with mu the encounter angle (0 = following). Running with the sea stretches
    the encounter period; punching into it shortens it. Returns None where the
    vessel matches the wave celerity exactly (Te -> infinity, surf-riding).
    """
    if t_s is None or speed_kt is None:
        return None
    a = rel_angle(track_deg, wave_from_deg)
    if a is None:
        return None
    c = wave_celerity(t_s, depth_m)
    if not c:
        return None
    v = kt_to_mps(speed_kt)
    denom = 1.0 - (v / c) * math.cos(math.radians(a))
    if abs(denom) < 1e-6:
        return None
    return t_s / abs(denom)


def roll_ratio(te_s, roll_period_s):
    """|Te/Tr - 1|. ZERO IS THE DANGEROUS END: the encounter period matching the
    vessel's natural roll period is synchronous rolling, the resonance case IMO
    MSC.1/Circ.1228 warns about. Rated with dir=low in thresholds.tsv.
    """
    if te_s is None or not roll_period_s or roll_period_s <= 0:
        return None
    return abs(te_s / roll_period_s - 1.0)


# --------------------------------------------------------------------------
# wind against current
# --------------------------------------------------------------------------
def wind_vs_current(wspd_kt, wdir_from_deg, curr_kt, curr_to_deg, curr_ref_kt=2.0):
    """Wind-against-current severity index, in knots of wind.

        index = wspd_kt * opposing_fraction * min(1, curr_kt / curr_ref_kt)

    where opposing_fraction = max(0, -cos(angle between where the wind is BLOWING
    TOWARD and where the current is FLOWING TOWARD)). It is 1 when they are
    exactly opposed and 0 once they align.

    This is a CARICOOS-defined transparent index, NOT a standard quantity - it
    exists so 'wind against tide' can be rated on the same knots scale as wind
    itself. 20 kt of wind against 2 kt of fully opposing current scores 20;
    the same wind with 1 kt scores 10. The hazard is real (steeper, shorter,
    breaking seas in the Mona Passage, Vieques Sound and the USVI cuts) even
    though the index is a convention.
    """
    if None in (wspd_kt, wdir_from_deg, curr_kt, curr_to_deg) or curr_kt <= 0:
        return 0.0
    wind_toward = (wdir_from_deg + 180.0) % 360.0
    theta = ang_diff(wind_toward, curr_to_deg)
    opposing = max(0.0, -math.cos(math.radians(theta)))
    return wspd_kt * opposing * min(1.0, curr_kt / curr_ref_kt)


# --------------------------------------------------------------------------
# descriptive scales (labels only; never used to rate)
# --------------------------------------------------------------------------
_BEAUFORT = [1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64]


def beaufort(wspd_kt):
    if wspd_kt is None:
        return None
    for i, lo in enumerate(_BEAUFORT):
        if wspd_kt < lo:
            return i
    return 12


_DOUGLAS = [0.0, 0.1, 0.5, 1.25, 2.5, 4.0, 6.0, 9.0, 14.0]


def douglas_sea_state(hs_m):
    if hs_m is None:
        return None
    for i, hi in enumerate(_DOUGLAS):
        if hs_m <= hi:
            return i
    return 9
