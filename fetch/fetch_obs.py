#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fetch real observations from the CARICOOS instruments (DM1 THREDDS/OPeNDAP).

This is what turns "Conditions now" from a forecast board into an observation
board. The NWS forecast describes a whole marine zone for a 12-hour period;
these are instruments in the water reporting minutes ago.

Sources, in order of what they provide:
  UMaine buoys   PR1/PR2/PR3/VI1 - waves + QARTOD flags, hourly
  CDIP waveriders 181/249         - waves, half-hourly
  Mesonet         X*** stations   - wind, gust, direction, ~5-minutely
  NDBC latest_obs                 - one HTTP GET, fallback + upstream sentinels

Why NOT the www.caricoos.org JSON API, which would have been far simpler:
it publishes no usable observation time. Its `actual_time` field comes back as
`2026` - the epoch rounded to four significant figures by the site's display
formatter - so there is no way to tell a five-minute-old reading from a
five-hour-old one. Values without a trustworthy time are worse than no values
on a board a mariner uses to decide whether to leave the dock. (Its `/us/`
variant also labels imperial numbers with metric units.) OPeNDAP costs a second
per station and gives a real timestamp and a QC flag, so that is what runs here.

QARTOD aggregate flags are honoured: 1 = pass, 2 = not evaluated, 3 = suspect,
4 = fail. Anything flagged 4 is dropped; 3 is kept but marked, because a suspect
reading a mariner can see and judge beats a blank cell.
"""
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                      # noqa: E402
import marlib as M                      # noqa: E402

MPS_TO_KT = 1.9438444924406046
QC_FAIL = 4


def log(msg):
    print(f"[fetch_obs] {msg}", flush=True)


# Never assume a unit. The mesonet publishes AvrgWS in KNOTS while the buoys
# publish wind in m/s, and assuming m/s everywhere inflated every mesonet reading
# by 94% - a 15 kt breeze was being reported as 30 kt, which is the difference
# between a pleasant afternoon and a small-craft warning. Read the file's own
# `units` attribute and convert from that.
_KT = {"knots": 1.0, "knot": 1.0, "kt": 1.0, "kts": 1.0,
       "m/s": 1.9438444924406046, "m s-1": 1.9438444924406046,
       "meters/second": 1.9438444924406046, "m s^-1": 1.9438444924406046,
       "mph": 0.868976, "miles per hour": 0.868976, "miles/hour": 0.868976,
       "km/h": 0.539957, "kph": 0.539957, "kilometers/hour": 0.539957,
       # El ADCP de las boyas publica en cm/s. Sin esta fila _conv lo SALTA en
       # vez de adivinar, que es lo correcto - pero entonces no hay corriente.
       "cm/s": 0.019438444924406046, "cm s-1": 0.019438444924406046}
_M = {"m": 1.0, "meters": 1.0, "metres": 1.0, "meter": 1.0,
      "ft": 0.3048, "feet": 0.3048, "cm": 0.01}


def _to_c(value, units, src, what):
    """Temperature to Celsius from the file's declared unit.

    The mesonet publishes AirTemp in degree_Fahrenheit while the buoys publish
    water temperature in Celsius. Reading both as Celsius put 96 F on a page as
    "96 C" - the same class of mistake as reading knots as m/s, and just as
    invisible until someone looks at a number and knows it is wrong."""
    if value is None:
        return None
    u = (units or "").strip().lower()
    if u in ("degc", "c", "celsius", "degree_celsius", "degrees_celsius", "deg_c"):
        return value
    if u in ("degf", "f", "fahrenheit", "degree_fahrenheit", "degrees_fahrenheit", "deg_f"):
        return (value - 32.0) * 5.0 / 9.0
    if u in ("k", "kelvin"):
        return value - 273.15
    log(f"  {src}: unknown {what} unit {u!r} - reading skipped rather than guessed")
    return None


def _units(ds, name):
    v = ds.variables.get(name)
    return (getattr(v, "units", "") or "").strip().lower() if v is not None else ""


def _conv(value, units, table, what, src):
    if value is None:
        return None
    f = table.get(units)
    if f is None:
        log(f"  {src}: unknown {what} unit {units!r} - reading skipped rather than guessed")
        return None
    return value * f


def _stats24(ds, tname, fields, src):
    """Min / max / median over the last 24 hours, from the file already open.

    The board only ever needed the latest reading, so that is all this fetcher
    kept - which meant nothing could answer "how windy has it been today?" or
    "what was the peak gust?". Reading the tail of the same dataset costs about a
    tenth of a second per station, so the history comes from the instrument
    record itself rather than from a rolling cache we would have to maintain and
    could silently lose.

    `fields` maps output name -> (variable, unit-conversion table or None).
    """
    import datetime as _dt
    import netCDF4
    tv = ds.variables.get(tname)
    if tv is None or not len(tv):
        return None
    n = len(tv)
    probe = min(n, 600)
    try:
        tt = netCDF4.num2date(tv[n - probe:], tv.units, only_use_cftime_datetimes=False)
    except Exception:
        return None
    cut = tt[-1] - _dt.timedelta(hours=24)
    keep = [i for i, x in enumerate(tt) if x >= cut]
    if len(keep) < 3:
        return None
    start = n - probe + keep[0]

    out = {"n": len(keep), "hours": 24}
    for name, (var, table) in fields.items():
        v = ds.variables.get(var)
        if v is None:
            continue
        try:
            arr = np.ma.masked_invalid(np.ma.masked_array(v[start:])).compressed()
        except Exception:
            continue
        if not arr.size:
            continue
        f = 1.0
        if table is not None:
            f = table.get(_units(ds, var))
            if f is None:          # unknown unit - skip rather than guess
                continue
        out[name] = {"min": round(float(arr.min()) * f, 2),
                     "max": round(float(arr.max()) * f, 2),
                     "median": round(float(np.median(arr)) * f, 2)}
    return out if len(out) > 2 else None


def _num(ds, name, idx=-1):
    v = ds.variables.get(name)
    if v is None:
        return None
    try:
        x = v[idx]
    except Exception:
        return None
    if np.ma.is_masked(x):
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def _last_time(ds, tname="time"):
    import netCDF4
    tv = ds.variables.get(tname)
    if tv is None or not len(tv):
        return None
    try:
        d = netCDF4.num2date(tv[-1], tv.units, only_use_cftime_datetimes=False)
        return d.replace(tzinfo=__import__("datetime").timezone.utc).isoformat()
    except Exception:
        return None


def _catalog(env, cat):
    url = f"{env['THREDDS_BASE']}/catalog/{cat}/catalog.xml"
    return re.findall(r'urlPath="([^"]+)"', M.http_text(url, env["NWS_USER_AGENT"]))


def buoy_waves(env, src):
    """Newest merged waves file for one UMaine buoy.

    The per-station folder also holds other stations' files (PR2/Waves contains
    VI1 files), so the pattern is anchored to this station's id - sorting the
    folder blind picks up a different buoy's data.
    """
    import netCDF4
    stid = src["src_id"]
    try:
        ents = _catalog(env, f"{src['endpoint']}/Waves")
    except Exception as e:
        log(f"  {stid}: catalog failed ({type(e).__name__})")
        return None
    pat = re.compile(rf"/{re.escape(stid)}\d*\.waves\.merged\.nc$", re.I)
    files = sorted(x for x in ents if pat.search("/" + x))
    if not files:
        log(f"  {stid}: no merged waves file in catalog")
        return None
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{files[-1]}")
    except Exception as e:
        log(f"  {stid}: open failed ({type(e).__name__})")
        return None
    try:
        qc = _num(ds, "significant_wave_height_qc_agg")
        if qc is not None and qc >= QC_FAIL:
            log(f"  {stid}: waves flagged QARTOD {int(qc)} (fail), dropped")
            return None
        hu = _units(ds, "significant_wave_height")
        return {"obs_utc": _last_time(ds),
                "hs_m": _conv(_num(ds, "significant_wave_height"), hu, _M, "wave height", stid),
                "tp_s": _num(ds, "dominant_wave_period"),
                # La ola MAXIMA, no solo la significativa. Hs es el promedio del
                # tercio mayor; hmax es la que de verdad golpea, y es la que
                # guardan los records historicos (8.16 m en PR1 con Maria).
                "hmax_m": _conv(_num(ds, "max_wave_height"), hu, _M, "max wave", stid),
                "dp_deg": _num(ds, "mean_wave_direction"), "wave_units": hu,
                "qc": None if qc is None else int(qc), "file": files[-1].split("/")[-1],
                "last24h": _stats24(ds, "time",
                                    {"hs_m": ("significant_wave_height", _M),
                                     "hmax_m": ("max_wave_height", _M),
                                     "tp_s": ("dominant_wave_period", None)}, stid)}
    finally:
        ds.close()


def buoy_ocean(env, src):
    """Water temperature and salinity from one UMaine buoy's CTD.

    A third stream beside Waves and Meteorology, and it was missing until
    2026-10-06. The gap was invisible from the pipeline's own side - every page
    rendered, nothing warned - and only surfaced when the chatbot was asked
    whether the water was normal for the date. It HAD the 17-year climatology
    band for exactly that question and no reading to compare against it, so it
    correctly answered that it could not say.

    Same folder convention as the other streams, so the same anchoring caveat
    applies: a station's folder holds other stations' files.
    """
    import netCDF4
    stid = src["src_id"]
    try:
        ents = _catalog(env, f"{src['endpoint']}/Physical_Properties")
    except Exception as e:
        log(f"  {stid}: ocean catalog failed ({type(e).__name__})")
        return None
    pat = re.compile(rf"/{re.escape(stid)}\d*\.ocean\.[0-9.]+m\.merged\.nc$", re.I)
    files = sorted(x for x in ents if pat.search("/" + x))
    if not files:
        log(f"  {stid}: no merged ocean file in catalog")
        return None
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{files[-1]}")
    except Exception as e:
        log(f"  {stid}: ocean open failed ({type(e).__name__})")
        return None
    try:
        qc = _num(ds, "temperature_qc_agg")
        if qc is not None and qc >= QC_FAIL:
            log(f"  {stid}: water temp flagged QARTOD {int(qc)} (fail), dropped")
            return None
        # Read the file's own unit rather than assuming Celsius - the same rule
        # that caught the mesonet publishing air temperature in Fahrenheit.
        tu = _units(ds, "temperature")
        return {"obs_utc": _last_time(ds),
                # wtemp_c, not water_temp_c: the NDBC reader already established
                # that internal name, and make_chat_context maps it. Inventing a
                # second spelling for the same quantity silently dropped it.
                "wtemp_c": _to_c(_num(ds, "temperature"), tu, stid, "water temp"),
                "salinity_psu": _num(ds, "salinity"),
                "water_temp_units": tu,
                "ocean_qc": None if qc is None else int(qc),
                "ocean_file": files[-1].split("/")[-1],
                "ocean24h": _stats24(ds, "time",
                                     {"water_temp_c": ("temperature", None)}, stid)}
    finally:
        ds.close()


def buoy_currents(env, src):
    """Surface current from the buoy's ADCP.

    The last stream to be wired up, and the one with the most behind it:
    `engine/derive.py` has carried `wind_vs_current()` from the start, and
    `config/thresholds.tsv` has a `wind_vs_curr` limit for passages and inlets -
    the physics and the policy were written and tested, and had no current data
    to run on until 2026-10-06.

    Two details that would be wrong if assumed instead of read:

    * The file reports a PROFILE - speed is (time, depth) over ~36 bins. The
      shallowest bin is what a hull feels, so that is the one taken; a blind
      index would silently report the current 38 m down.
    * `current_direction` is `sea_water_velocity_to_direction` - degrees TOWARD
      which the water flows, true north. That is exactly what wind_vs_current()
      wants for `curr_to_deg`. Waves and wind in this project are FROM. Mixing
      the two conventions reverses the opposing component, turning the calmest
      case into the roughest.
    """
    import netCDF4
    import numpy as np
    stid = src["src_id"]
    try:
        ents = _catalog(env, f"{src['endpoint']}/Currents")
    except Exception as e:
        log(f"  {stid}: currents catalog failed ({type(e).__name__})")
        return None
    pat = re.compile(rf"/{re.escape(stid)}\d*\.currents\.adcp\.merged\.nc$", re.I)
    files = sorted(x for x in ents if pat.search("/" + x))
    if not files:
        log(f"  {stid}: no merged currents file in catalog")
        return None
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{files[-1]}")
    except Exception as e:
        log(f"  {stid}: currents open failed ({type(e).__name__})")
        return None
    try:
        depth = np.atleast_1d(np.ma.filled(ds.variables["depth"][:], np.nan))
        ok = np.where(np.isfinite(depth))[0]
        if not len(ok):
            log(f"  {stid}: currents file has no usable depth axis")
            return None
        k = int(ok[np.argmin(depth[ok])])          # el bin mas somero
        su = _units(ds, "current_speed")

        def _bin(name):
            v = ds.variables.get(name)
            if v is None:
                return None
            a = np.ma.masked_invalid(v[-1, k] if v.ndim == 2 else v[-1])
            return None if a is np.ma.masked or a.mask else round(float(a), 2)

        # La bandera QARTOD tambien es un perfil, una por bin - leerla como
        # escalar reventaba con "only length-1 arrays can be converted".
        qc = _bin("current_speed_qc_agg")
        if qc is not None and qc >= QC_FAIL:
            log(f"  {stid}: current flagged QARTOD {int(qc)} (fail), dropped")
            return None
        spd = _conv(_bin("current_speed"), su, _KT, "current", stid)
        return {"obs_utc": _last_time(ds),
                "curr_kt": spd,
                "curr_to_deg": _bin("current_direction"),
                "curr_depth_m": round(float(depth[k]), 1),
                "current_units": su,
                "curr_qc": None if qc is None else int(qc),
                "currents_file": files[-1].split("/")[-1]}
    finally:
        ds.close()


def cdip_waves(env, src):
    import netCDF4
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{src['endpoint']}")
    except Exception as e:
        log(f"  {src['src_id']}: open failed ({type(e).__name__})")
        return None
    try:
        hu = _units(ds, "waveHs")
        return {"obs_utc": _last_time(ds, "waveTime"),
                "hs_m": _conv(_num(ds, "waveHs"), hu, _M, "wave height", src["src_id"]),
                "tp_s": _num(ds, "waveTp"), "dp_deg": _num(ds, "waveDp"),
                "wave_units": hu, "qc": None,
                "last24h": _stats24(ds, "waveTime",
                                    {"hs_m": ("waveHs", _M), "tp_s": ("waveTp", None)},
                                    src["src_id"])}
    finally:
        ds.close()


def buoy_wind(env, src):
    """The buoy's own anemometer, from its Meteorology stream.

    These folders were there from the start and went unused, so a site sitting
    beside its own buoy was reading wind off a mesonet station tens of kilometres
    away - Ponce was 45 km from XIMG, Vieques 29 km from XCUL.
    """
    import netCDF4
    stid = src["src_id"]
    try:
        ents = _catalog(env, f"{src['endpoint']}/Meteorology")
    except Exception as e:
        log(f"  {stid}: met catalog failed ({type(e).__name__})")
        return None
    pat = re.compile(rf"/{re.escape(stid)}\d*\.met\.merged\.nc$", re.I)
    files = sorted(x for x in ents if pat.search("/" + x))
    if not files:
        return None
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{files[-1]}")
    except Exception as e:
        log(f"  {stid}: met open failed ({type(e).__name__})")
        return None
    try:
        wu, gu = _units(ds, "wind_speed"), _units(ds, "wind_gust")
        au = _units(ds, "air_temperature")
        return {"obs_utc": _last_time(ds),
                "wind_kt": _conv(_num(ds, "wind_speed"), wu, _KT, "wind", stid),
                "gust_kt": _conv(_num(ds, "wind_gust"), gu, _KT, "gust", stid),
                "wdir_deg": _num(ds, "wind_direction"),
                # Mar adentro no hay estaciones de tierra, asi que la boya es la
                # unica fuente de aire y presion en su zona.
                "atemp_c": _to_c(_num(ds, "air_temperature"), au, stid, "air temp"),
                "pres_mb": _num(ds, "barometric_pressure"),
                "wind24h": _stats24(ds, "time",
                                    {"wind_kt": ("wind_speed", _KT),
                                     "gust_kt": ("wind_gust", _KT)}, stid)}
    finally:
        ds.close()


def windnet_nc(env, src):
    """A WindNet station that opens normally. Units come from the file - Tres
    Palmas reports in miles per hour, not m/s."""
    import netCDF4
    sid = src["src_id"]
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{src['endpoint']}")
    except Exception as e:
        log(f"  {sid}: open failed ({type(e).__name__})")
        return None
    try:
        return {"obs_utc": _last_time(ds),
                "wind_kt": _conv(_num(ds, "AvrgWS"), _units(ds, "AvrgWS"), _KT, "wind", sid),
                "gust_kt": None,
                "wdir_deg": _num(ds, "DirWS")}
    finally:
        ds.close()


def windnet_dap(env, src):
    """A WindNet station netCDF4 refuses to open.

    The Arecibo file trips "NC_UNLIMITED in the wrong index" in the DAP client -
    the Model Viewer ETL hit the same wall and reached for the pydap engine. That
    would mean a new dependency in a virtualenv another project owns, so this
    talks to the DAP server directly instead: .dds for the time length, then
    .ascii for the last row. Plain HTTP and text parsing, nothing installed.

    QARTOD flags are honoured: 4 (fail) is dropped, 3 (suspect) and 2 (not
    evaluated) are kept, since a reading the mariner can see and weigh beats a
    blank cell.
    """
    base = f"{env['THREDDS_BASE']}/dodsC/{src['endpoint']}"
    ua = env["NWS_USER_AGENT"]
    sid = src["src_id"]
    try:
        dds = M.http_text(f"{base}.dds", ua)
        m = re.search(r"time = (\d+)", dds)
        if not m:
            log(f"  {sid}: no time dimension in .dds")
            return None
        i = int(m.group(1)) - 1
        q = (f"time[{i}:{i}],wind_speed[0:0][{i}:{i}],wind_speed_qc[0:0][{i}:{i}],"
             f"wind_gust[0:0][{i}:{i}],wind_direction[0:0][{i}:{i}],"
             f"wind_direction_qc[0:0][{i}:{i}]")
        txt = M.http_text(f"{base}.ascii?{q}", ua)
    except Exception as e:
        log(f"  {sid}: DAP read failed ({type(e).__name__})")
        return None

    def grab(name):
        m = re.search(rf"^{re.escape(name)}\[.*?\]\s*\n(?:\[0\],\s*)?(-?[\d.eE+-]+)",
                      txt, re.M)
        if not m:
            return None
        try:
            v = float(m.group(1))
        except ValueError:
            return None
        return None if v <= -9e29 else v

    t = grab("time")
    if t is None:
        return None
    # this file's time is DAYS since 1970-01-01, not seconds
    obs = M.epoch_to_iso(t * 86400.0)
    ws, wd = grab("wind_speed"), grab("wind_direction")
    qs, qd = grab("wind_speed_qc"), grab("wind_direction_qc")
    if qs is not None and qs >= QC_FAIL:
        ws = None
    if qd is not None and qd >= QC_FAIL:
        wd = None
    # .das declares m/s for this station
    return {"obs_utc": obs,
            "wind_kt": None if ws is None else ws * MPS_TO_KT,
            "gust_kt": (lambda g: None if g is None else g * MPS_TO_KT)(grab("wind_gust")),
            "wdir_deg": wd, "qc": None if qs is None else int(qs)}


def mesonet_wind(env, src):
    import netCDF4
    try:
        ds = netCDF4.Dataset(f"{env['THREDDS_BASE']}/dodsC/{src['endpoint']}")
    except Exception as e:
        log(f"  {src['src_id']}: open failed ({type(e).__name__})")
        return None
    try:
        sid = src["src_id"]
        wu, gu = _units(ds, "AvrgWS"), _units(ds, "GustWS")
        return {"obs_utc": _last_time(ds),
                "wind_kt": _conv(_num(ds, "AvrgWS"), wu, _KT, "wind", sid),
                "gust_kt": _conv(_num(ds, "GustWS"), gu, _KT, "gust", sid),
                "wind_units": wu,
                "wdir_deg": _num(ds, "DirWS"),
                "atemp_c": _to_c(_num(ds, "AirTemp"), _units(ds, "AirTemp"), sid, "air temp"),
                "last24h": _stats24(ds, "time",
                                    {"wind_kt": ("AvrgWS", _KT), "gust_kt": ("GustWS", _KT)},
                                    sid)}
    finally:
        ds.close()


def ndbc(env, want):
    try:
        txt = M.http_text(env["NDBC_LATEST"], env["NWS_USER_AGENT"])
    except Exception as e:
        log(f"  NDBC latest_obs failed ({type(e).__name__})")
        return {}
    out = {}
    for line in txt.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        if len(f) < 19 or f[0] not in want:
            continue

        def n(i):
            try:
                return None if f[i] == "MM" else float(f[i])
            except (ValueError, IndexError):
                return None
        try:
            obs = M.parts_to_iso(f[3], f[4], f[5], f[6], f[7])
        except Exception:
            continue
        w, g = n(9), n(10)
        out[want[f[0]]] = {"obs_utc": obs, "hs_m": n(11), "tp_s": n(12), "dp_deg": n(14),
                           "wind_kt": None if w is None else w * MPS_TO_KT,
                           "gust_kt": None if g is None else g * MPS_TO_KT,
                           "wdir_deg": n(8), "wtemp_c": n(17), "qc": None}
    return out


def _fetch_one(env, s):
    """Todos los streams de una fuente, combinados en un solo registro.

    Separada de main() para que una estacion que revienta se pueda aislar sin
    envolver el bucle entero en un try - y para que se lea de un vistazo que
    una boya son CUATRO lecturas distintas, no una.
    """
    prov = s["provider"]
    if prov != "caricoos_buoy":
        # .get, no [] : ndbc y coops se recogen en otro bucle, asi que aqui
        # devuelven None como hacia el if/elif original. Con corchetes lanzaban
        # KeyError y, antes de aislar los fallos, eso tumbaba el run entero.
        fn = {"cdip": cdip_waves, "caricoos_mesonet": mesonet_wind,
              "windnet_nc": windnet_nc, "windnet_dap": windnet_dap}.get(prov)
        return fn(env, s) if fn else None

    r = buoy_waves(env, s)
    # Oleaje, viento, CTD y ADCP son cuatro archivos con sus propios tiempos. El
    # del oleaje manda como tiempo del registro; los demas viajan con el suyo
    # propio, porque una corriente de hace tres horas junto a un oleaje de hace
    # diez minutos no es una lectura, son dos.
    for fn, marca in ((buoy_wind, "wind_obs_utc"), (buoy_ocean, "ocean_obs_utc"),
                      (buoy_currents, "curr_obs_utc")):
        x = fn(env, s)
        if not x:
            continue
        if r is None:
            r = x
        else:
            r.update({k: v for k, v in x.items() if k != "obs_utc"})
            r[marca] = x["obs_utc"]
    return r


def main(argv):
    problems = M.validate()
    if problems:
        for p in problems:
            log(f"CONFIG ERROR: {p}")
        return 2
    env = M.load_env()
    srcs = M.load_sources()
    only = None
    for a in argv:
        if a.startswith("--station="):
            only = a.split("=", 1)[1].split(",")

    obs = {}
    for sid, s in srcs.items():
        if only and sid not in only:
            continue
        r = None
        try:
            r = _fetch_one(env, s)
        except Exception as e:                                   # noqa: BLE001
            # Una estacion que revienta NO puede llevarse las otras 24 por
            # delante. Paso el 2026-10-06: una variable QARTOD con forma
            # inesperada en una boya aborto el run completo y dejo el tablero
            # entero con los datos de la hora anterior, sin ningun aviso.
            log(f"  {sid}: FALLO ({type(e).__name__}: {e}); se omite esta estacion")
            continue
        if not r or not r.get("obs_utc"):
            continue
        r["src_id"] = sid
        r["provider"] = s["provider"]
        obs[sid] = r
        continue
    for sid, r in ndbc(env, {s["endpoint"]: i for i, s in srcs.items()
                             if s["provider"] == "ndbc"}).items():
        r["src_id"] = sid
        r["provider"] = "ndbc"
        obs.setdefault(sid, r)

    # Age, and the staleness verdict, computed once here so every page agrees.
    for sid, r in obs.items():
        a = M.age_minutes(r["obs_utc"])
        r["age_min"] = None if a is None else round(a, 1)
        mx = srcs[sid]["max_age_h"] * 60 if sid in srcs else 360
        r["stale"] = bool(a is not None and a > mx)

    payload = {"fetched_utc": M.utcnow().isoformat(), "count": len(obs), "stations": obs}
    if "--dry-run" not in argv:
        M.write_json(payload, "obs", "obs.json")
        M.record("caricoos_obs", env["THREDDS_BASE"], bool(obs), len(str(payload)),
                 extra={"stations": len(obs),
                        "stale": sum(1 for r in obs.values() if r["stale"])})

    fresh = [r for r in obs.values() if not r["stale"]]
    log(f"{len(obs)} stations read, {len(fresh)} fresh "
        f"({sum(1 for r in fresh if r.get('hs_m') is not None)} with waves, "
        f"{sum(1 for r in fresh if r.get('wind_kt') is not None)} with wind)")
    for sid, r in sorted(obs.items()):
        flag = " STALE" if r["stale"] else ""
        log(f"  {sid:12s} {str(r['age_min']):>8s} min  Hs={r.get('hs_m')} "
            f"Tp={r.get('tp_s')} wind={None if r.get('wind_kt') is None else round(r['wind_kt'],1)}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
