#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/status.html - what fetched when, and what did not.

Built entirely from state/manifest.json, so a source that quietly stopped updating
shows up on a page rather than only in a log nobody opens. This is the first page
to open when the board looks wrong.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

SRC_BI = {"nws_cwf": ("NWS Coastal Waters Forecast", "Pronóstico de Aguas Costeras del NWS"),
          "nws_alerts": ("NWS active marine products", "Productos marinos vigentes del NWS"),
          "nws_zones": ("NWS marine zone lookup", "Consulta de zonas marinas del NWS")}

CSS = r"""
table.st{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:1.2rem}
table.st th{background:var(--controls);font:600 .76rem "Archivo",sans-serif;
  letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);padding:.5rem .6rem;
  text-align:left;border-bottom:1px solid var(--line)}
table.st td{padding:.5rem .6rem;border-bottom:1px solid var(--grid);font-size:.92rem;
  vertical-align:top}
.ok{color:var(--ok);font-weight:600}
.bad{color:var(--flag);font-weight:600}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.err{font:400 .82rem "JetBrains Mono",monospace;color:var(--flag);word-break:break-word}
.lead{max-width:62ch}
"""


def fmt_age(mins):
    if mins is None:
        return "–"
    if mins < 90:
        return f"{mins:.0f} min"
    if mins < 48 * 60:
        return f"{mins / 60:.1f} h"
    return f"{mins / 1440:.1f} d"


def main():
    man = M.read_manifest()
    srcs = M.load_sources(active_only=False)
    problems = M.validate()

    rows = []
    for key in sorted(man):
        e = man[key]
        age = M.age_minutes(e.get("fetched_utc"))
        en, es = SRC_BI.get(key, (key, key))
        ok = e.get("ok")
        # Age matters more than the last outcome: a fetch that failed an hour ago
        # but has a fresh cache behind it is a different problem from one that has
        # not succeeded in a day.
        stale = age is not None and age > 180
        cov = e.get("coverage") or {}
        covtxt = (f"{cov['zones']} zones, {cov['periods']} periods, "
                  f"wind {cov['wind_rate']:.0%}, wave detail {cov['wave_rate']:.0%}"
                  if cov else "")
        rows.append(
            "<tr>"
            f"<td><b>{M.bi(en, es)}</b><br><span class='err' style='color:var(--ink2)'>"
            f"{html.escape(str(e.get('url', ''))[:90])}</span></td>"
            f"<td class='{'ok' if ok else 'bad'}'>"
            f"{M.bi('OK', 'OK') if ok else M.bi('FAILED', 'FALLÓ')}</td>"
            f"<td class='num {'bad' if stale else ''}'>{fmt_age(age)}</td>"
            f"<td class='num'>{e.get('bytes', 0):,}</td>"
            f"<td>{covtxt}{('<div class=err>' + html.escape(str(e['error'])[:200]) + '</div>') if e.get('error') else ''}</td>"
            "</tr>")

    down = [s for s in srcs.values() if s["down"]]
    downrows = "".join(
        f"<tr><td><b>{s['src_id']}</b></td><td>{M.bi(s['name_en'], s['name_es'])}</td>"
        f"<td>{M.bi(s['notes'], M.es_note(s['notes']))}</td></tr>" for s in down)

    cfg = (f"<p class='ok'>{M.bi('Configuration is consistent.', 'La configuración es consistente.')}</p>"
           if not problems else
           "<ul class='bad'>" + "".join(f"<li>{html.escape(p)}</li>" for p in problems) + "</ul>")

    body = f"""
<p class="lead">{M.bi(
    "Every number on this dashboard is written to disk by a fetcher and read back by a page "
    "generator, which never touches the network. If a fetch fails, the previous payload stays "
    "in place and the board keeps working &mdash; this page is how you see that it happened.",
    "Cada número de este tablero lo escribe en disco un recolector y lo lee un generador de "
    "páginas, que nunca accede a la red. Si una descarga falla, la carga anterior permanece y "
    "el tablero sigue funcionando; esta página es la forma de ver que ocurrió.")}</p>

<h2>{M.bi("Data sources", "Fuentes de datos")}</h2>
<table class="st"><thead><tr>
<th>{M.bi("Source", "Fuente")}</th><th>{M.bi("Last result", "Último resultado")}</th>
<th>{M.bi("Age", "Antigüedad")}</th><th>{M.bi("Bytes", "Bytes")}</th>
<th>{M.bi("Detail", "Detalle")}</th>
</tr></thead><tbody>{"".join(rows) or "<tr><td colspan=5>no fetches recorded</td></tr>"}</tbody></table>

<h2>{M.bi("Stations marked down", "Estaciones fuera de servicio")}</h2>
{("<table class='st'><thead><tr><th>ID</th><th>" + M.bi("Station", "Estación") +
  "</th><th>" + M.bi("Note", "Nota") + "</th></tr></thead><tbody>" + downrows + "</tbody></table>")
 if down else "<p>" + M.bi("None.", "Ninguna.") + "</p>"}

<h2>{M.bi("Configuration", "Configuración")}</h2>
{cfg}
"""
    gen = M.bi(f"Generated {M.utcnow().isoformat()[:16]}Z. Refreshes every 10 minutes.",
               f"Generado {M.utcnow().isoformat()[:16]}Z. Se actualiza cada 10 minutos.")
    out_html = M.page_shell("status.html", "Data status", "Estado de datos",
                            "What fetched when", "Qué se descargó y cuándo",
                            body, extra_css=CSS, scripts="function onLang(){}", generated=gen)
    out = os.path.join(M.WEBOUT, "status.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_status] wrote {out} ({len(out_html):,} bytes, {len(rows)} sources, "
          f"{len(down)} down, {len(problems)} config problems)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
