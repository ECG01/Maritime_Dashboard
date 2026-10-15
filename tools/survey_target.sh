#!/usr/bin/env bash
# Survey a candidate host for the Maritime Dashboard.
#
# Copy this file to the target server and run it there:
#     bash survey_target.sh
#
# It only READS. It installs nothing, writes nothing outside /tmp, changes no
# config, and needs no root for most of it. Paste the output back to whoever is
# doing the migration.
#
# It deliberately does NOT print the contents of any .env, credential or key
# file. It reports that such files exist and nothing more.
echo "=================================================================="
echo " Maritime Dashboard - target host survey"
echo " $(date -u '+%Y-%m-%dT%H:%M:%SZ')  (UTC)"
echo "=================================================================="

sec(){ echo; echo "--- $1"; }

sec "1. Host and OS"
echo "hostname     : $(hostname -f 2>/dev/null || hostname)"
echo "whoami       : $(whoami)"
echo "kernel       : $(uname -srm)"
if [ -r /etc/os-release ]; then . /etc/os-release; echo "distro       : ${PRETTY_NAME:-unknown}"; fi
echo "timezone     : $(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || date +%Z)"
echo "local time   : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "container?   : $( [ -f /.dockerenv ] && echo 'yes - docker' || (grep -qa 'docker\|lxc\|kubepods' /proc/1/cgroup 2>/dev/null && echo 'probably' || echo 'no, looks like a real host/VM') )"

sec "2. Python"
for p in python3 python3.12 python3.11 python3.10 python; do
  command -v "$p" >/dev/null 2>&1 && echo "$p -> $("$p" -V 2>&1) at $(command -v "$p")"
done
echo -n "venv module  : "; python3 -c "import venv" 2>/dev/null && echo "available" || echo "MISSING - need the python3-venv package"
echo "pip          : $(python3 -m pip --version 2>/dev/null || echo 'not available for python3')"
echo
echo "The dashboard needs Python 3 plus netCDF4, numpy and shapely. Those three"
echo "install as wheels; no compiler needed. It gets its OWN venv, so whatever"
echo "is installed system-wide does not matter much - but note it anyway:"
for m in netCDF4 numpy shapely; do
  python3 -c "import $m,sys; print('  %-9s %s' % ('$m', $m.__version__))" 2>/dev/null \
    || echo "  $m        (not installed system-wide - fine, the venv will bring it)"
done

sec "3. Shell tools the cron wrappers use"
for c in flock rsync find date mkdir cp curl tar crontab git node npm; do
  printf '  %-9s %s\n' "$c" "$(command -v "$c" 2>/dev/null || echo 'MISSING')"
done
echo "  (flock and rsync are the two that actually matter - flock stops two cron"
echo "   cycles colliding, rsync is how pages reach the webroot)"

sec "4. Web server"
for s in nginx apache2 httpd caddy lighttpd; do
  if command -v "$s" >/dev/null 2>&1 || pgrep -x "$s" >/dev/null 2>&1; then
    echo "  found: $s  $("$s" -v 2>&1 | head -1)"
  fi
done
echo
echo "listening sockets (look for 80 / 443):"
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | awk 'NR==1 || /:80 |:443 |:8080 /' | head -12
echo
echo "candidate config files:"
ls -d /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf \
      /etc/apache2/sites-enabled/* /etc/httpd/conf.d/*.conf \
      /etc/caddy/Caddyfile 2>/dev/null | head -20 || echo "  none readable as $(whoami)"
echo
echo "document roots declared in those files:"
grep -rhoE '^[[:space:]]*(root|DocumentRoot)[[:space:]]+[^;[:space:]]+' \
     /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null | sort -u | head -20 \
  || echo "  (not readable without root - ask whoever administers the box)"

sec "5. Where the Model Viewer v2 lives"
echo "searching for it (this is the neighbour the dashboard will sit beside)..."
for d in /srv /var/www /opt /home /usr/share/nginx /data /mnt; do
  [ -d "$d" ] || continue
  find "$d" -maxdepth 4 \( -iname '*model*dashboard*' -o -iname '*modviewer*' \
       -o -iname '*model_viewer*' -o -iname '*caricoos*' \) \
       -not -path '*/node_modules/*' 2>/dev/null | head -8
done
echo
echo "docker containers, if any:"
docker ps --format '  {{.Names}}  {{.Image}}  {{.Ports}}' 2>/dev/null | head -10 \
  || echo "  (docker not available to $(whoami))"

sec "6. Cron"
echo "this user's crontab:"
crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | head -20 || echo "  (empty or not permitted)"
echo
echo "system cron directories:"
ls /etc/cron.d/ 2>/dev/null | head -10
echo "systemd timers:"
systemctl list-timers --no-pager 2>/dev/null | head -8 || echo "  (systemd not available)"

sec "7. Disk"
df -h / /srv /var /home /data 2>/dev/null | sort -u
echo
echo "The dashboard itself is tiny - about 5 MB of code plus a few MB of cached"
echo "JSON. Logs rotate at 30 days. Budget 200 MB and you will never think about"
echo "it again."

sec "8. Outbound network - THE ONE THAT BLOCKS MIGRATIONS"
echo "The pipeline must reach these. A managed or firewalled host often cannot."
for h in dm1.caricoos.org api.weather.gov api.tidesandcurrents.noaa.gov \
         www.ndbc.noaa.gov dm2.caricoos.org; do
  code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' \
         -A 'CariCOOS Maritime Dashboard survey' "https://$h/" 2>/dev/null)
  case "$code" in
    000|"") printf '  %-36s UNREACHABLE  <-- blocker\n' "$h" ;;
    *)      printf '  %-36s reachable (HTTP %s)\n' "$h" "$code" ;;
  esac
done
echo
echo "api.weather.gov needs a descriptive User-Agent or it answers 403 - a 403"
echo "above is therefore fine and means the host CAN reach it."

sec "9. Anything already at the intended path?"
for d in /srv/maritime /var/www/maritime /opt/maritime; do
  [ -e "$d" ] && echo "  EXISTS: $d" || echo "  free:   $d"
done

echo
echo "=================================================================="
echo " Done. Paste all of the above back."
echo " Nothing here printed a password, key or .env content - if you see"
echo " anything that looks like a secret, redact it before sending."
echo "=================================================================="
