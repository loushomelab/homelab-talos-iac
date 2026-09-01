# AGENTS.md

## Repository Overview
GitOps Infrastructure-as-Code (IaC) repository managing a Talos Linux Kubernetes homelab cluster via Argo CD. It follows the **App-of-Apps** pattern with tiered sync waves for deterministic bootstrap and automated continuous delivery.

### Strict GitOps Principles & Constraints
1. **Zero Direct Cluster Mutation:** **NEVER** use `kubectl apply`, `kubectl create`, `kubectl edit`, or `kubectl delete` to mutate the live cluster. All changes must be made declaratively via Git commits.
2. **Avoid Kustomize:** Avoid Kustomize in Argo CD applications and configurations. Prefer native Kubernetes manifests (`directory: { recurse: true }`) or Helm chart `valuesObject` over Kustomize overlays.
3. **Mandatory Delivery & Change Verification:** Do NOT finish a task by merely checking if an application is green. Always verify that:
   - Argo CD has reconciled the **exact target commit SHA** (`status.sync.revision`).
   - The **specific modified fields/resources** are actively present in live cluster state.
   - Workload rollouts complete and endpoints respond correctly (unless cluster network is unreachable).

---

## Local Pre-Commit Validation & Testing

Run these commands locally for client-side validation before pushing to Git:

```bash
# 1. Single Manifest / File Dry-Run Validation (Syntax & Schema only)
kubectl apply --dry-run=client -f argocd/apps/workloads/forgejo.yaml
kubectl apply --dry-run=client -f argocd/configs/infrastructure/ingressroute/manifests/

# 2. Syntax, Formatting & JSON Validation
git diff --check
node -e 'JSON.parse(require("fs").readFileSync("renovate.json", "utf8"))'

# 3. Single Invariant / Assertion Testing (Python)
python3 -c 'from pathlib import Path; assert "gethomepage.dev/enabled" in Path("argocd/apps/workloads/forgejo.yaml").read_text()'
```

---

## Post-Commit Delivery & Change Verification

After pushing changes to `main`, verify that the submitted changes have taken effect:

```bash
# 1. Verify Argo CD is syncing the EXACT target commit SHA (not previous state)
TARGET_SHA=$(git rev-parse HEAD)
kubectl get application <app-name> -n argocd -o jsonpath='{.status.sync.revision}'
# If not synced yet, trigger immediate sync for the commit:
kubectl -n argocd patch application <app-name> --type merge -p "{\"operation\":{\"sync\":{\"prune\":true,\"revision\":\"$TARGET_SHA\"}}}"

# 2. Wait for Workload Rollout to Complete
kubectl rollout status deployment/<name> -n <namespace> --timeout=120s

# 3. Inspect Live Cluster State to PROVE the Modified Fields are Applied
# Example A: Verify new IngressRoute annotations / routes are present
kubectl get ingressroute <name> -n <namespace> -o jsonpath='{.metadata.annotations}'
# Example B: Verify updated container image or environment variables
kubectl get deployment <name> -n <namespace> -o jsonpath='{.spec.template.spec.containers[0].image}'
# Example C: Verify generated ExternalSecret or ConfigMap contents
kubectl get configmap <name> -n <namespace> -o yaml

# 4. Live Endpoint & Health Probe
curl -ks https://<service>.646499453.xyz:8443 -o /dev/null -w "%{http_code}\n"
```

---

## Sync Waves & Delivery Architecture

Rollouts strictly follow sync waves (`argocd.argoproj.io/sync-wave`) to ensure zero race conditions:
- **Wave 0 (Operators):** `cert-manager`, `external-secrets-operator`, `prometheus-crds`, `reflector`
- **Wave 1 (Core Infra & Secrets):** `metallb`, `longhorn`, `doppler-cluster-store`, `external-secrets`
- **Wave 2 (Routing & Identity):** `traefik` (VIP `192.168.50.230`), `authentik` (SSO/OIDC)
- **Wave 3 (Monitoring Stack):** `grafana`, `mimir`, `alloy` (eBPF), `pyroscope`, `pulse`, `umami`
- **Wave 4 (User Workloads):** `homepage`, `forgejo`, `n8n`

---

## Directory Structure & Conventions

```
.
├── argocd/
│   ├── bootstrap/
│   │   ├── root-app.yaml            # Root App-of-Apps Application (tracks main)
│   │   ├── values.yaml              # Argo CD Helm values (OIDC, RBAC, Ingress)
│   │   └── init/
│   │       ├── projects/            # Argo CD AppProjects (infra, security, monitoring, workloads)
│   │       └── tiers/               # Tier Applications with sync waves (0 to 4)
│   ├── apps/                        # Argo CD Application CRDs (Helm & Git sources)
│   │   ├── infrastructure/          # 00-operators, 10-core, 20-services
│   │   ├── security/                # 10-core (ESO), 20-services (authentik)
│   │   ├── monitoring/              # grafana, mimir, alloy, pulse, umami, etc.
│   │   └── workloads/               # forgejo, homepage
│   └── configs/                     # Pure Kubernetes manifests (prefer over Kustomize)
│       ├── infrastructure/          # metallb, cert-manager, ingressroutes
│       ├── security/                # authentik blueprints, external-secrets
│       ├── monitoring/              # PVCs, ingress, middlewares
│       └── workloads/homepage/      # Homepage YAML config files
├── docs/                            # Architecture specs and plans (gitignored)
└── renovate.json                    # Automated dependency updates (weekend automerge)
```

---

## Code Style & Implementation Guidelines

### 1. YAML & Manifest Formatting
- **Indentation:** Exactly 2 spaces (no tabs). Unix LF (`\n`) line endings.
- **Multi-Document Files:** Separate resources with `---`.
- **Comments:** Document the *why* behind non-standard settings.

### 2. Argo CD Application Standards
- **Finalizers:** Always include `resources-finalizer.argocd.argoproj.io` for cascading deletion.
- **Sync Policy:** Automated sync with `prune: true` and `selfHeal: true`.
- **Sync Options:** `CreateNamespace=true` for workload apps; `RespectIgnoreDifferences=true` for root/tiers.
- **Storage & Workloads:** Use `storageClassName: longhorn`, `accessModes: [ReadWriteOnce]`, and `strategy.type: Recreate` for RWO volumes.
- **OCI Helm Charts:** Specify `repoURL: '<registry>/<org>'` (omit `https://` / `oci://` prefix) with `chart: '<name>'`.

### 3. Database Topology & Storage Standards
- **Auth/Core App PG (`192.168.50.151` / `DB_AUTH_POSTGRESQL`):** Dedicated to identity, core business, and automation assets (`authentik`, `forgejo`, `n8n`). High PBS backup priority.
- **Observability PG (`192.168.50.152` / `DB_OBS_POSTGRESQL`):** Dedicated to metrics, telemetry, and analytics (`grafana`, `umami`).
- **Storage Separation:** Structured data must reside on LXC PostgreSQL. Longhorn PVC is reserved for static/binary assets, community plugins, and temp cache (avoid SQLite on PVC for high-concurrency workloads).
- **Execution Data Pruning:** Workload apps using LXC DB must enable auto-pruning (e.g. 7-day TTL) to prevent storage bloat.
- **Cross-Repo Provisioning:** Never run ad-hoc SQL. Declare `postgresql_role` and `postgresql_database` in `../homelab-pve/databases/main.tf` and let Terraform Cloud reconcile.

### 4. Secret Management & Wave Dependencies (Zero Secrets in Git)
- All secrets reside in Doppler (`k8s` / `prd`) and sync via `ExternalSecret` referencing `doppler-cluster-store`.
- Use `engineVersion: v2` for `ExternalSecret` templates when transforming tokens or credentials.
- **Wave 1 Namespace Pre-requisite:** `all-external-secrets.yaml` runs in Wave 1. If an `ExternalSecret` targets a new namespace (e.g. `n8n`), ensure the `Namespace` resource is explicitly declared in `all-external-secrets.yaml` so sync does not fail before Wave 4.

### 5. Ingress, Networking & Authentication
- **Entrypoint:** Port 8443 (`websecure`) via Traefik VIP `192.168.50.230`.
- **TLS Secret:** Always specify `wildcards-646499453-xyz-tls` (synced across namespaces via Reflector).
- **Domain Pattern:** `https://<service>.646499453.xyz:8443` or `https://<name>.pve.646499453.xyz:8443`.
- **Authentik Protection Selection:**
  - **Native OIDC:** Configure `OAuth2Provider` + `Application` in `blueprint-apps.yaml` for apps supporting native OIDC (`forgejo`, `grafana`, `nexterm`).
  - **Traefik ForwardAuth:** Configure `ProxyProvider` (`mode: forward_single`) bound to `authentik Embedded Outpost` and add `traefik.ingress.kubernetes.io/router.middlewares: traefik-authentik-forwardauth@kubernetescrd` on Ingress for apps without native SSO (`n8n`, `longhorn`, `traefik`).

### 6. Homepage Service Discovery Annotations
```yaml
annotations:
  gethomepage.dev/enabled: "true"
  gethomepage.dev/name: "<ServiceName>"
  gethomepage.dev/description: "<Short Description>"
  gethomepage.dev/group: "Infrastructure" # Identity, Dashboards, Monitoring, CI/CD, Development
  gethomepage.dev/icon: "sh-<service>.svg" # selfh.st/icons or PNG
  gethomepage.dev/href: "https://<service>.646499453.xyz:8443"
  gethomepage.dev/pod-selector: "app.kubernetes.io/name=<app-name>"
  gethomepage.dev/widget.type: "<widget-type>"
  gethomepage.dev/widget.url: "http://<service>.<namespace>.svc.cluster.local:<port>"
  gethomepage.dev/widget.key: "{{HOMEPAGE_VAR_<KEY_NAME>}}"
```

---

## Git & Commit Conventions

- **Conventional Commits:** `<type>(<scope>): <subject>`
  - Types: `feat`, `fix`, `chore`, `docs`, `refactor`
  - Scopes: `homepage`, `traefik`, `forgejo`, `authentik`, `monitoring`, `metallb`, `deps`
  - Examples: `feat(workloads): add forgejo application with postgresql and authentik oidc`
- **Workflow:** Branch from `main` -> Validate locally with dry-run -> Open PR -> Merge to `main` -> Verify exact commit SHA sync & live state.
