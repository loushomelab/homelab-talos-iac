#!/usr/bin/env bash
# Run on grokbot-box only AFTER the policy and Connector routes are merged and
# reconciled. This script is a manual runbook; it must not run in CI.
#
# Install tailscale, tailscaled, and the official Tailscale get-authkey utility:
# https://tailscale.com/docs/features/oauth-clients#get-authkey-utility
# Supply TAILSCALE_OPERATOR_OAUTH_CLIENT_ID and
# TAILSCALE_OPERATOR_OAUTH_CLIENT_SECRET via the environment, for example:
# doppler run --project k8s --config prd -- ./scripts/grokbot-tailscale-join.sh
# The OAuth client needs auth_keys permission for tag:grokbot. An admin owns
# that tag in policy and must authorize the client for it. If the existing
# operator client cannot mint this tag, an admin must extend its allowed tags
# or provide a dedicated OAuth client / auth-key path instead.
#
# Userspace networking exposes SOCKS5 and HTTP proxies at localhost:1055;
# applications must explicitly use a compatible proxy. SOCKS5 UDP support is
# not guaranteed, so verify the DNS client's transport and proxy compatibility.
# State persists under GROKBOT_TS_STATE_DIR (default ~/.local/state/grokbot-tailscale).
# Rollback: run tailscale --socket="$GROKBOT_TS_STATE_DIR/tailscaled.sock" logout,
# remove the device in the Tailscale admin console, then revert the PR to remove
# the Connector routes and policy changes. Set the variable to the actual path.
set -euo pipefail
umask 077

: "${TAILSCALE_OPERATOR_OAUTH_CLIENT_ID:?Set the Tailscale OAuth client ID}"
: "${TAILSCALE_OPERATOR_OAUTH_CLIENT_SECRET:?Set the Tailscale OAuth client secret}"
for command in tailscale tailscaled get-authkey; do
  command -v "$command" >/dev/null || { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

state_dir=${GROKBOT_TS_STATE_DIR:-"$HOME/.local/state/grokbot-tailscale"}
mkdir -p "$state_dir"
chmod 700 "$state_dir"
socket="$state_dir/tailscaled.sock"
if [[ -e "$socket" ]]; then
  printf 'Socket already exists: %s; stop the existing daemon first.\n' "$socket" >&2
  exit 1
fi
key_file=$(mktemp "$state_dir/authkey.XXXXXXXX")
daemon_pid=''
cleanup() {
  rm -f "$key_file"
  if [[ -n "$daemon_pid" ]]; then
    kill "$daemon_pid" 2>/dev/null || true
    wait "$daemon_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# get-authkey uses the Tailscale API and defaults to a single-use,
# non-ephemeral, preauthorized key. Explicit flags document those defaults.
TS_API_CLIENT_ID=$TAILSCALE_OPERATOR_OAUTH_CLIENT_ID \
TS_API_CLIENT_SECRET=$TAILSCALE_OPERATOR_OAUTH_CLIENT_SECRET \
  get-authkey -tags tag:grokbot -reusable=false -ephemeral=false -preauth=true > "$key_file"

tailscaled --tun=userspace-networking --socks5-server=localhost:1055 \
  --outbound-http-proxy-listen=localhost:1055 --state="$state_dir/tailscaled.state" \
  --socket="$socket" >"$state_dir/tailscaled.log" 2>&1 &
daemon_pid=$!
for ((i = 0; i < 50; i++)); do
  [[ -S "$socket" ]] && break
  kill -0 "$daemon_pid" 2>/dev/null || { printf 'tailscaled failed; check its local log.\n' >&2; exit 1; }
  sleep 0.1
done
[[ -S "$socket" ]] || { printf 'tailscaled socket did not become ready.\n' >&2; exit 1; }
tailscale --socket="$socket" up --auth-key="file:$key_file" --hostname=grokbot-box --accept-routes
# Leave tailscaled running after successful join; its state and log are local.
daemon_pid=''
printf 'Connected. Configure applications to use the local proxy on port 1055.\n'
