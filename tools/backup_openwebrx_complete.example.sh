#!/bin/bash
set -euo pipefail
umask 077
FTP="ftp://NAS_HOST:21/backup/openwebrx"
STAMP=$(date +'%Y-%m-%d_%H-%M-%S')
WORK=$(mktemp -d /tmp/openwebrx-backup.XXXXXX)
ARCHIVE="/tmp/openwebrx_full_$STAMP.tar.gz"
NAME=$(basename "$ARCHIVE")
trap 'rm -rf "$WORK"' EXIT

dpkg-query -W openwebrx openwebrxplus python3-csdr libcsdr0 > "$WORK/packages.txt" 2>/dev/null || true
sudo -n tar -C / -czf "$ARCHIVE" \
  usr/lib/python3/dist-packages/htdocs \
  usr/lib/python3/dist-packages/owrx \
  usr/lib/python3/dist-packages/csdr \
  usr/lib/python3/dist-packages/pycsdr \
  etc/openwebrx var/lib/openwebrx \
  home/radio/backup_openwebrx.sh \
  home/radio/backup_openwebrx_complete.sh \
  var/lib/openwebrx-custom \
  usr/local/sbin/openwebrx-custom-save \
  usr/local/sbin/openwebrx-custom-restore \
  etc/apt/apt.conf.d/99-openwebrx-custom-restore \
  lib/systemd/system/openwebrx.service \
  etc/systemd/system/openwebrx-backup.service \
  etc/systemd/system/openwebrx-backup.timer \
  usr/bin/openwebrx \
  -C "$WORK" packages.txt
sudo -n chown radio:radio "$ARCHIVE"
tar -tzf "$ARCHIVE" > "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins/receiver/rig_skin_v88/rig_skin.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins/receiver/rig_skin_v88/rig_skin.css' "$WORK/contents.txt"
grep -Fxq 'etc/openwebrx/openwebrx.conf' "$WORK/contents.txt"
grep -Fxq 'var/lib/openwebrx/settings.json' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/index.html' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins/receiver/init.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins/receiver/audio_filter/audio_filter.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/plugins/receiver/audio_filter/nf_bridge.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/aircraft-map.html' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/aircraft-window.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/htdocs/air-leaflet.js' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/owrx/controllers/aircraft.py' "$WORK/contents.txt"
grep -Fxq 'usr/lib/python3/dist-packages/owrx/http.py' "$WORK/contents.txt"
grep -Fxq 'var/lib/openwebrx/receiver_avatar.png' "$WORK/contents.txt"
grep -Fxq 'usr/local/sbin/openwebrx-custom-restore' "$WORK/contents.txt"
grep -Fxq 'var/lib/openwebrx-custom/paths.list' "$WORK/contents.txt"
LOCAL_HASH=$(sha256sum "$ARCHIVE" | awk '{print $1}')
curl --fail --silent --show-error --netrc --ftp-create-dirs -T "$ARCHIVE" "$FTP/$NAME"
REMOTE_HASH=$(curl --fail --silent --show-error --netrc "$FTP/$NAME" | sha256sum | awk '{print $1}')
if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
  echo "Backup checksum mismatch: $NAME" >&2
  exit 1
fi
echo "Backup verified on NAS: $NAME ($LOCAL_HASH)"
rm -f "$ARCHIVE"
