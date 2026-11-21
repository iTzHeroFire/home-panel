#!/usr/bin/env bash
# Home hub clean-up & tune-up. Safe to run more than once.
# Run on the mini PC:  sudo bash ~/homehub/ha-config/www/panel/tools/cleanup.sh
# Nothing personal is deleted: no Home Assistant config, backups or Docker volumes.

[ "$(id -u)" = 0 ] || { echo "Run it with sudo:  sudo bash $0"; exit 1; }
HUB="$(realpath "$(dirname "$0")/../../../..")"          # .../homehub
CFG="$HUB/ha-config"
[ -f "$CFG/configuration.yaml" ] || { echo "Can't find $CFG/configuration.yaml"; exit 1; }
REPORT="$HUB/cleanup-report.txt"
say(){ echo; echo "== $*"; }
free_gb(){ df -BM --output=avail / | tail -1 | tr -dc 0-9; }
BEFORE=$(free_gb); RESTART_HA=0; RESTART_DOCKER=0

say "1/8 Old system packages and package cache"
apt-get -y -qq autoremove --purge >/dev/null 2>&1
apt-get -y -qq clean
echo "done"

say "2/8 System logs: trim to 100 MB and keep them capped"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
journalctl --vacuum-size=100M -q
echo "done"

say "3/8 Docker: old images, stopped containers, build cache (your data volumes are kept)"
docker container prune -f >/dev/null
docker image prune -a -f | tail -1
docker builder prune -a -f >/dev/null 2>&1
if [ ! -f /etc/docker/daemon.json ]; then
  printf '{\n  "log-driver": "json-file",\n  "log-opts": { "max-size": "10m", "max-file": "2" }\n}\n' > /etc/docker/daemon.json
  RESTART_DOCKER=1; echo "container logs now capped at 20 MB each"
fi

say "4/8 Matter server (nothing uses it: the AC and lights connect without Matter)"
MATTER=$(docker ps -a --format '{{.Names}} {{.Image}}' | awk '/matter-server/{print $1; exit}')
if [ -n "$MATTER" ]; then
  if grep -q '"matter"' "$CFG/.storage/core.device_registry" 2>/dev/null; then
    echo "kept: a Matter device is paired"
  else
    docker update --restart=no "$MATTER" >/dev/null; docker stop "$MATTER" >/dev/null
    echo "stopped '$MATTER' and it won't start on boot (frees RAM and CPU)"
    echo "to bring it back later:  sudo docker update --restart=unless-stopped $MATTER && sudo docker start $MATTER"
  fi
else echo "not running"; fi

say "5/8 Home Assistant database: keep 7 days of history, write to disk less often"
if ! grep -q '^recorder:' "$CFG/configuration.yaml"; then
  cp "$CFG/configuration.yaml" "$CFG/configuration.yaml.before-cleanup"
  printf '\nrecorder:\n  purge_keep_days: 7\n  commit_interval: 15\n' >> "$CFG/configuration.yaml"
  RESTART_HA=1; echo "added (backup: configuration.yaml.before-cleanup)"
else echo "already configured, left alone"; fi

say "6/8 Home Assistant leftovers (old logs, speech cache)"
rm -f "$CFG"/home-assistant.log.* "$CFG"/home-assistant.log.old "$CFG"/home-assistant.log.fault
rm -rf "$CFG"/tts/* 2>/dev/null
find "$CFG" -maxdepth 1 -name '*.bak' -mtime +7 -delete
echo "done"

say "7/8 Boot straight to console if a desktop was installed (a desktop wastes RAM on a hub)"
if [ "$(systemctl get-default)" = graphical.target ]; then
  systemctl set-default multi-user.target >/dev/null 2>&1
  echo "switched; takes effect after reboot (undo: sudo systemctl set-default graphical.target)"
else echo "already console-only"; fi

say "8/8 Applying"
[ $RESTART_DOCKER = 1 ] && { systemctl restart docker; echo "Docker restarted (Home Assistant comes back by itself)"; RESTART_HA=0; }
if [ $RESTART_HA = 1 ]; then
  HA=$(docker ps --format '{{.Names}} {{.Image}}' | awk '/home-assistant/{print $1; exit}')
  [ -n "$HA" ] && docker restart "$HA" >/dev/null && echo "Home Assistant restarted"
fi
AFTER=$(free_gb)

{
  echo "Home hub report — $(date)"
  echo "Disk freed: $(( AFTER - BEFORE )) MB   (free now: $((AFTER/1024)) GB)"
  echo; echo "--- Memory"; free -h
  echo; echo "--- Disk"; df -h / | tail -1
  echo; echo "--- Containers"; docker ps --format '{{.Names}}  {{.Status}}'
  echo; echo "--- Container memory"; docker stats --no-stream --format '{{.Name}}  {{.MemUsage}}  CPU {{.CPUPerc}}'
  echo; echo "--- HA database size"; du -sh "$CFG"/home-assistant_v2.db 2>/dev/null
  echo; echo "--- HA backups"; du -sh "$CFG"/backups 2>/dev/null; ls -1 "$CFG"/backups 2>/dev/null | head -20
  echo; echo "--- Custom integrations"; ls -1 "$CFG"/custom_components 2>/dev/null
  echo; echo "--- Biggest files in your home folder (over 50 MB)"; find "$HUB/.." -xdev -type f -size +50M -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -10 | awk -F'\t' '{printf "%6d MB  %s\n", $1/1048576, $2}'
  echo; echo "--- Running services"; systemctl list-units --type=service --state=running --no-legend | awk '{print $1}'
  echo; echo "--- Top memory users"; ps -eo rss,comm --sort=-rss | head -8 | awk 'NR>1{printf "%5d MB  %s\n", $1/1024, $2}'
} > "$REPORT" 2>&1
chown --reference="$HUB" "$REPORT" 2>/dev/null
echo; cat "$REPORT"
echo; echo "Saved to $REPORT. Send this to Claude for the next round."
