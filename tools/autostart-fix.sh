#!/usr/bin/env bash
# Make the home hub come back by itself after a power cut — no password, no login.
# Run on the mini PC:  sudo bash ~/homehub/ha-config/www/panel/tools/autostart-fix.sh
#  1. Services: Docker, Tailscale, avahi, cron start on boot
#  2. Wi-Fi: connects at boot for the whole system (not only after you log in)
#  3. Disk encryption: unlocks itself at boot (your passphrase keeps working as a backup)

[ "$(id -u)" = 0 ] || { echo "Run it with sudo:  sudo bash $0"; exit 1; }
say(){ echo; echo "== $*"; }

say "1/3 Services start on boot"
for s in docker containerd tailscaled avahi-daemon cron NetworkManager; do
  systemctl list-unit-files "$s.service" --no-legend 2>/dev/null | grep -q . || continue
  systemctl enable "$s" >/dev/null 2>&1 && echo "  $s: on"
done
# containers come back after a reboot
for c in $(docker ps -a --format '{{.Names}}'); do
  case "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$c")" in
    no|"") [[ $c == *matter* ]] || { docker update --restart=unless-stopped "$c" >/dev/null; echo "  $c: now restarts automatically"; } ;;
  esac
done

say "2/3 Wi-Fi"
if command -v nmcli >/dev/null; then
  found=0
  while IFS=: read -r name type; do
    [ "$type" = 802-11-wireless ] || continue; found=1
    perms=$(nmcli -g connection.permissions con show "$name")
    flags=$(nmcli -g 802-11-wireless-security.psk-flags con show "$name" 2>/dev/null); flags=${flags%% *}
    if [ -z "$perms" ] && [ "${flags:-0}" = 0 ]; then echo "  '$name' already connects at boot"; continue; fi
    nmcli con modify "$name" connection.permissions "" connection.autoconnect yes
    if [ "${flags:-0}" != 0 ]; then
      read -rsp "  Wi-Fi password for '$name': " pw < /dev/tty; echo
      nmcli con modify "$name" 802-11-wireless-security.psk-flags 0 802-11-wireless-security.psk "$pw"
    fi
    echo "  '$name' now connects at boot, before anyone logs in"
  done < <(nmcli -t -f NAME,TYPE con show)
  [ $found = 0 ] && echo "  no Wi-Fi connections (Ethernet) — nothing to do"
else echo "  NetworkManager not used — the network already starts at boot"; fi

say "3/3 Disk encryption"
if [ ! -s /etc/crypttab ] || ! grep -qv '^\s*#' /etc/crypttab; then
  echo "  the disk isn't encrypted — nothing to do"
else
  mkdir -p -m 700 /etc/keys
  cp /etc/crypttab /etc/crypttab.before-autounlock
  changed=0
  while read -r name src key opts; do
    [[ -z $name || $name == \#* ]] && continue
    [[ $opts == *luks* || -z $opts ]] || continue
    if [ "$key" != none ] && [ -n "$key" ]; then echo "  $name already unlocks with a key file"; continue; fi
    dev=$( [[ $src == UUID=* ]] && blkid -U "${src#UUID=}" || echo "$src" )
    kf="/etc/keys/$name.key"
    [ -f "$kf" ] || { dd if=/dev/urandom of="$kf" bs=512 count=1 status=none; chmod 400 "$kf"; }
    if ! cryptsetup open --test-passphrase --key-file "$kf" "$dev" 2>/dev/null; then
      echo "  Type your current disk passphrase once (the one you type at boot):"
      cryptsetup luksAddKey "$dev" "$kf" < /dev/tty || { echo "  passphrase not accepted — nothing changed"; continue; }
    fi
    awk -v n="$name" -v k="$kf" '$1==n && ($3=="none" || $3==""){ $3=k } {print}' OFS='\t' /etc/crypttab > /etc/crypttab.new && mv /etc/crypttab.new /etc/crypttab
    changed=1; echo "  $name will unlock itself"
  done < /etc/crypttab.before-autounlock
  if [ $changed = 1 ]; then
    mkdir -p /etc/cryptsetup-initramfs
    grep -q '^KEYFILE_PATTERN=' /etc/cryptsetup-initramfs/conf-hook 2>/dev/null || echo 'KEYFILE_PATTERN="/etc/keys/*.key"' >> /etc/cryptsetup-initramfs/conf-hook
    grep -q '^UMASK=' /etc/initramfs-tools/initramfs.conf || echo 'UMASK=0077' >> /etc/initramfs-tools/initramfs.conf
    echo "  rebuilding the boot image (takes a minute)…"
    update-initramfs -u -k all >/dev/null 2>&1
    if lsinitramfs "/boot/initrd.img-$(uname -r)" | grep -q 'cryptroot/keyfiles'; then
      echo "  done and checked — the key is inside the boot image"
    else
      echo "  couldn't add the key to the boot image — undoing, your boot is unchanged"
      cp /etc/crypttab.before-autounlock /etc/crypttab; update-initramfs -u -k all >/dev/null 2>&1
    fi
  fi
fi

echo; echo "All set. Test it: sudo reboot — then wait ~3 minutes without touching the mini PC."
