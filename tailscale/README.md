# Tailscale GitOps

Files in this directory are the source of truth for the tailnet. Changes ship
through pull requests and are applied by GitHub Actions on merge to `main`.

- `policy.hujson` — ACL policy (`.github/workflows/tailscale-acl.yml`)
- `dns-split.json` — split DNS map (`.github/workflows/tailscale-dns.yml`).
  A merge to `main` PUTs this file in full to `/api/v2/tailnet/-/dns/split-dns`.
  Global nameservers, MagicDNS, and search paths are not managed here.

OAuth clients live in Doppler `k8s/prd` and are mirrored as GitHub Actions
secrets of the same name.
