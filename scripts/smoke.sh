#!/usr/bin/env bash
# Smoke test OmniChat with two real clients on a dedicated server:
#   server (runSmokeServer) + Speaker (runClient) + Listener (runSmokeListener)
#   → Listener is teleported in front of Speaker → Speaker chats → screenshot from Listener's view → log check.
# Needs universal-modder's `um` (Claude Code plugin) and a one-time `um win setup` (gfxcapture ffmpeg).
#
#   scripts/smoke.sh                      # default message
#   scripts/smoke.sh -m "привет" -k       # custom message, keep everything running afterwards
#   scripts/smoke.sh -f                   # don't wait for the user to stop touching keyboard/mouse
#
# Exit code: 0 = no errors in logs, 1 = errors found, 2 = setup/launch failure.
set -uo pipefail

MSG="omnichat smoke test"
KEEP=0
FORCE=0
TIMEOUT=300
PORT=25599
while getopts "m:kf" o; do
  case $o in
    m) MSG="$OPTARG" ;;
    k) KEEP=1 ;;
    f) FORCE=1 ;;
    *) sed -n '2,11p' "$0"; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/smoke"
SRV="$ROOT/run/smoke/server"
LIS="$ROOT/run/smoke/listener"
SPEAKER_LOG="$ROOT/run/logs/latest.log"
SERVER_LOG="$SRV/logs/latest.log"
LISTENER_LOG="$LIS/logs/latest.log"
UM_BIN="${UM_BIN:-$HOME/.claude2/plugins/marketplaces/universal-modder/bin}"
command -v um >/dev/null 2>&1 || export PATH="$UM_BIN:$PATH"
command -v um >/dev/null 2>&1 || { echo "um not found (set UM_BIN)"; exit 2; }
mkdir -p "$OUT"

mcproc() { powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ROOT/scripts/mcproc.ps1")" "$@" | tr -d '\r'; }
drive() { um win drive --proc java --no-retry "$@" 2>&1 | tail -n +2; }
cleanup() { mcproc kill "dli\.env=(client|server)" >/dev/null; }
fail() { echo "[smoke] $1"; (( KEEP )) || cleanup; exit 2; }

# wait_log <file> <regex> <since-epoch>: the log must be newer than <since> (latest.log is rotated per launch)
wait_log() {
  local t0; t0=$(date +%s)
  while (( $(date +%s) - t0 < TIMEOUT )); do
    [ -f "$1" ] && (( $(stat -c %Y "$1") >= $3 )) && grep -qE "$2" "$1" && return 0
    sleep 3
  done
  return 1
}

# gradlew re-parses "$@" through `eval`, so arguments with spaces must be shell-escaped once more
gradle_bg() { local log=$1; shift; (cd "$ROOT" && ./gradlew "$@" >"$OUT/$log" 2>&1) & }

# --- 0. server + listener dirs: offline flat creative world, Speaker is op, models shared via junctions
mkdir -p "$SRV/config/omnichat" "$LIS/config/omnichat"
echo "eula=true" >"$SRV/eula.txt"
cat >"$SRV/server.properties" <<EOF
server-port=$PORT
online-mode=false
enforce-secure-profile=false
level-type=minecraft\:flat
gamemode=creative
difficulty=peaceful
spawn-monsters=false
generate-structures=false
view-distance=6
spawn-protection=0
motd=OmniChat smoke
EOF
cat >"$SRV/ops.json" <<EOF
[{"uuid":"1cc8a86a-983d-3262-9cf1-03a730bec70b","name":"Speaker","level":4,"bypassesPlayerLimit":false}]
EOF
for d in "$SRV" "$LIS"; do
  m="$d/config/omnichat/models"
  [ -L "$m" ] && continue
  rmdir "$m" 2>/dev/null   # a client that ran before the junction leaves an empty dir; never deletes real files
  [ -e "$m" ] && fail "$m exists and is not a junction"
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '$(cygpath -w "$m")' -Target '$(cygpath -w "$ROOT/run/config/omnichat/models")'" >/dev/null
done

# an unfocused client opens the pause menu, which swallows the chat key (and hides the view): turn that off
set_opt() {  # set_opt <options.txt> <key> <value>
  if grep -q "^$2:" "$1" 2>/dev/null; then sed -i "s/^$2:.*/$2:$3/" "$1"; else echo "$2:$3" >>"$1"; fi
}
set_opt "$ROOT/run/options.txt" pauseOnLostFocus false
set_opt "$LIS/options.txt" pauseOnLostFocus false

# --- 1. server
cleanup
start=$(date +%s)
echo "[smoke] starting server on :$PORT"
gradle_bg server.log runSmokeServer
wait_log "$SERVER_LOG" "Done \(" "$start" || fail "server didn't start, see $OUT/server.log"

# --- 2. Speaker, then Listener (one at a time: both share the Loom/Gradle caches)
echo "[smoke] Speaker joining"
gradle_bg speaker.log runClient "$(printf '%q' "--args=--username Speaker --quickPlayMultiplayer localhost:$PORT")"
wait_log "$SERVER_LOG" "Speaker joined the game" "$start" || fail "Speaker didn't join, see $OUT/speaker.log"
echo "[smoke] Listener joining"
gradle_bg listener.log runSmokeListener
wait_log "$SERVER_LOG" "Listener joined the game" "$start" || fail "Listener didn't join, see $OUT/listener.log"
echo "[smoke] both joined after $(( $(date +%s) - start ))s"
sleep 5   # Fabric JOIN fires before the player is fully set up; let the world and voice map settle

speaker_pid=$(mcproc pid "dli.env=client.*username Speaker")
listener_pid=$(mcproc pid "dli.env=client.*username Listener")
listener_hwnd=$(mcproc hwnd "$listener_pid")
[ -n "$speaker_pid" ] && [ -n "$listener_hwnd" ] || fail "can't find client windows"

# --- 3. don't steal input from a human who is typing
if (( ! FORCE )); then
  calm=0
  for _ in $(seq 1 20); do
    idle=$(drive idle | awk '{print $NF}')
    awk "BEGIN{exit !($idle >= 5)}" && { calm=1; break; }
    echo "[smoke] user active (idle ${idle}s), waiting…"; sleep 3
  done
  (( calm )) || fail "user kept typing for a minute; rerun when away from the keyboard (or with -f)"
fi

# --- 4. as Speaker: put Listener 3 blocks in front, facing Speaker; then say the message
say() {  # opens chat in the focused Speaker window and sends $1
  [ "$(mcproc focus "$speaker_pid")" = "True" ] || fail "couldn't focus Speaker's window"
  drive "key 0x54" >/dev/null; sleep 0.7
  if LC_ALL=C grep -q '[^ -~]' <<<"$1"; then
    # WinDrive's stdin goes through the OEM codepage and mangles non-ASCII: paste via clipboard instead
    local b64; b64=$(printf '%s' "$1" | base64 -w0)
    powershell -NoProfile -Command "Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$b64')))"
    drive "key 0x11 down" "key 0x56" "key 0x11 up" "key 0x0D" >/dev/null
  else
    drive "type $1" "key 0x0D" >/dev/null
  fi
}
say "/execute at Speaker run tp Listener ^ ^ ^3 facing entity Speaker eyes"
sleep 1.5
say "$MSG"
echo "[smoke] Speaker said: $MSG"
sleep 1.5   # bubble shows right away; TTS takes a moment

# --- 5. screenshot from Listener's point of view (full + 1/3 copy for cheap viewing)
shot="$OUT/listener.png"
um win shot "$shot" --hwnd "$listener_hwnd" --scale 0.33 >/dev/null || echo "[smoke] screenshot failed"
sleep 4   # generation runs on the worker thread; give it time before reading logs

# --- 6. log check
# dev clients run with offline accounts: authlib 401 and Realms errors are expected noise
NOISE="Failed to fetch user properties|Failed to fetch Realms|Realms|authlib|profile key pair|No key layers in MapLike"
: >"$OUT/errors.log"; : >"$OUT/omnichat.log"
for pair in "server:$SERVER_LOG" "speaker:$SPEAKER_LOG" "listener:$LISTENER_LOG"; do
  name=${pair%%:*}; log=${pair#*:}
  grep -E "\(OmniChat\)" "$log" | sed "s/^/[$name] /" >>"$OUT/omnichat.log"
  { grep -nE "/(ERROR|FATAL)\]" "$log" | grep -vE "$NOISE"
    grep -nE "Exception|Caused by" "$log" | grep -iE "omnichat|sherpa|onnx"; } | sort -n -u | sed "s/^/[$name] /" >>"$OUT/errors.log"
done
heard=$(grep -cF "$MSG" "$LISTENER_LOG")
# Listener must actually voice it: "TTS playing" comes from OpenAL reporting AL_PLAYING
played=$(grep -c "TTS playing" "$LISTENER_LOG")
errs=$(wc -l <"$OUT/errors.log")

(( KEEP )) || { cleanup; wait 2>/dev/null; }

echo "--- omnichat log"; tail -n 20 "$OUT/omnichat.log"
echo "--- listener received the message: $([ "$heard" -gt 0 ] && echo yes || echo NO)"
echo "--- listener played TTS: $([ "$played" -gt 0 ] && echo yes || echo NO)"
echo "--- errors: $errs"; head -n 20 "$OUT/errors.log"
echo "--- screenshot: ${shot%.png}_small.png"
(( errs == 0 && heard > 0 && played > 0 ))
