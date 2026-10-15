{
echo "== HOST"; hostname -f; whoami; uname -srm
[ -r /etc/os-release ] && . /etc/os-release && echo "$PRETTY_NAME"
echo "tz: $(cat /etc/timezone 2>/dev/null || date +%Z)  now: $(date '+%F %T %Z')"
echo "== PYTHON"; python3 -V; python3 -c 'import venv' 2>&1 | head -1
echo "== TOOLS"; for c in flock rsync curl tar crontab git node; do printf '%s=%s ' $c "$(command -v $c || echo NO)"; done; echo
echo "== NGINX"; nginx -v 2>&1; ls /etc/nginx/sites-enabled/ 2>/dev/null
grep -rhoE '^[[:space:]]*(root|DocumentRoot)[[:space:]]+[^;[:space:]]+' /etc/nginx 2>/dev/null | sort -u | head
echo "== NEIGHBOURS"; ls -d /raid/*/ 2>/dev/null | head
ls -d /raid/*/CARICOOS* /raid/*/*odel* 2>/dev/null | head
echo "== CRON"; crontab -l 2>/dev/null | grep -vE '^#|^$' | head -20
echo "== DISK"; df -h / /raid 2>/dev/null | sort -u
echo "== OUTBOUND"
for h in dm1.caricoos.org api.weather.gov api.tidesandcurrents.noaa.gov www.ndbc.noaa.gov dm2.caricoos.org; do
  printf '%s -> %s\n' "$h" "$(curl -s -o /dev/null -m 15 -w '%{http_code}' -A 'survey' https://$h/ 2>/dev/null || echo FAIL)"
done
echo "== END"
} 2>&1
