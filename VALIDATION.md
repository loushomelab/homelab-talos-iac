# Local and CI validation

`task val:all` checks applications, configs, bootstrap resources, Kubernetes/CRD
schemas and Renovate JSON locally. It does not need kubeconfig, Kubernetes API
discovery or a reachable cluster. These
tasks never apply, patch, delete, sync or deploy resources.

Prepare dependencies **before going offline**:

```sh
python3 -m venv .tmp/validation-venv
.tmp/validation-venv/bin/python -m pip install -r scripts/requirements-validation.txt
export PATH="$PWD/.tmp/validation-venv/bin:$PATH"
task val:prepare-schemas
task val:all
```

Requirements: Python 3.10+, pinned PyYAML, **kubeconform v0.7.0 from its release
archive**, `kubectl` with bundled Kustomize, Node.js (Renovate JSON syntax), and
Go Task v3 for the task shortcuts. CI pins kubectl v1.36.0 and verifies both
tool archives/binaries with SHA256. Local validation also accepts a newer
kubectl's bundled Kustomize. A `go install` kubeconform binary reporting
`development` is rejected; use the versioned release archive. For air-gapped setup,
preinstall these tools and cache the PyYAML wheel; pip can install using
`--no-index --find-links <wheel-directory>`. Prepare or copy the locked schema
cache (`.cache/validation-schemas/`) before disconnecting. **Validation downloads
nothing.** Only `val:prepare-schemas` performs explicit network preparation.

Without Go Task, run the equivalent commands from the repository root:

```sh
.tmp/validation-venv/bin/python scripts/validate_manifests.py apps
.tmp/validation-venv/bin/python scripts/validate_manifests.py configs
.tmp/validation-venv/bin/python scripts/validate_manifests.py bootstrap
.tmp/validation-venv/bin/python scripts/validate_schemas.py
node -e 'JSON.parse(require("fs").readFileSync("renovate.json", "utf8"))'
```

Use `task val:apps`, `task val:configs`, `task val:bootstrap`, `task val:schemas`
or `task val:renovate` individually. The first three check YAML/basic structure;
`val:schemas` is the complete schema gate.
You can also select the interpreter with `task val:configs PYTHON=<python-path>`.

All YAML/YML/JSON manifests under `argocd/apps`, `argocd/configs` and
`argocd/bootstrap` are parsed
with duplicate-key detection. Each resource needs string `apiVersion`, `kind`
and `metadata.name` or `metadata.generateName`; Kubernetes `List` items are
checked recursively. Blank document separators are allowed, empty files fail.
Bootstrap's `values.yaml` is explicitly reported as Helm values, not a resource.
The complete gate rejects manifests outside these registered directories.

Homepage's existing `manifests/kustomization.yaml` is a build input. Its
`config/` directory contains application templates (including placeholders
that are not standalone YAML). Those templates are consumed as opaque files
by the existing ConfigMap generator. The validator checks source manifests,
runs `kubectl kustomize` locally and checks every generated resource, including
the ConfigMap. It does not parse the embedded Homepage template language.
Only the current local-file build features are supported; remote resources,
paths outside Homepage, new build fields and other unregistered Kustomizations
fail before rendering. No migration or additional Kustomize usage is introduced.
The output lists the Kustomization and every generator file as build inputs,
with the reason they are not checked as standalone resources. YAML/YML/JSON
files under `config/` must be referenced by a ConfigMap generator; unreferenced
templates fail instead of being silently excluded. Unregistered build files
also fail when named `Kustomization` without a file extension.

Failures return nonzero and identify the file/document or the Homepage build
and rendered document. YAML errors include line/column when available. Raw
parser/renderer diagnostics and resource bodies are suppressed to avoid logging
configuration values or credentials.

## Schema policy and coverage

Local `task val:schemas` and the CI schema job run the **same script**, calling
the existing HOM-2/HOM-3 classifier and Homepage renderer. There is no separate
CI glob, template exclusion list, default remote schema registry or
`-ignore-missing-schemas`. Source resources and rendered output receive schema
checks; embedded Homepage template strings remain opaque ConfigMap data.

`validation/schema-lock.json` targets **Kubernetes 1.36.0**, verified available
in kubeconform's default maintained schema project, `yannh/kubernetes-json-schema`.
Its standalone-strict schemas are pinned to commit
`86d045595d3f93b703bbf439cf9eb4bd6830d58f`. The lock records immutable URLs,
release versions, source SHA256 and canonical output SHA256. Preparation checks
both hashes; validation rechecks cached schema hashes and permits only local
schema files. External `$ref` downloads are rejected. CRDs come directly from
their official projects rather than a floating third-party catalog.

| Family | Locked release | Covered resource kinds |
| --- | --- | --- |
| Kubernetes | 1.36.0, standalone-strict | Deployment, StatefulSet, Job, EndpointSlice, Ingress, ClusterRole, ClusterRoleBinding, ConfigMap, Namespace, PersistentVolumeClaim, Service, ServiceAccount |
| Argo CD | v3.5.3 (chart 10.9.1) | Application, AppProject |
| External Secrets | v2.10.0 | ExternalSecret, ClusterSecretStore (`external-secrets.io/v1`) |
| Traefik chart | v41.5.0 (Traefik v3.7.13) | IngressRoute, IngressRouteTCP, Middleware, MiddlewareTCP, ServersTransport |
| MetalLB | v0.16.1 | IPAddressPool, L2Advertisement |
| cert-manager | v1.21.2 | Certificate, ClusterIssuer |
| Grafana Operator | v5.25.0 | Grafana, GrafanaDashboard |

CRD conversion closes declared property maps, preserves upstream
`additionalProperties` and `x-kubernetes-preserve-unknown-fields` regions,
and converts nullable/int-or-string fields. Opaque Helm `valuesObject` fields
are intentionally preserved according to the official Argo CD CRD; nested
Helm chart values are not validated. Metadata coverage follows each upstream
schema. CEL, admission webhooks, API discovery, references between resources,
Helm-rendered workloads and runtime behavior are outside this offline gate.
Pinned versions describe declared repository dependencies, not observed live CRDs.

Every run reports per-GVK coverage and a `validated/skipped/failed/missing_schema`
summary. Unknown GVKs and absent cache entries count as `skipped` and
`missing_schema`, **and fail the command**. Invalid resources or corrupt schemas
count as `failed`. Parser/tool failures also return nonzero with an explicit
input/tool error summary. No missing schema is treated as validation success.

At main `1cc7690` plus the accepted PR #137 tool dependency, the valid baseline
is **175 checks: 168 source + 7 Homepage rendered**, covering 27 GVKs, with zero
skips/failures. Six Homepage source objects are checked again after rendering;
counts describe checks, not distinct deployed objects. Four key CRD families
have both valid and deliberately invalid regression fixtures. Tests also cover
unknown GVK/version, missing/corrupt schemas, rendered schema errors, Unicode,
recursive Lists, tool errors and secret-safe diagnostics.

To update coverage, review the official release corresponding to the declared
chart, resolve its immutable commit, download that reviewed source and compute
its SHA256. Use `prepare_schemas.convert` and `digest` to compute each canonical
output hash, then update the lock in a PR. New GVKs must be explicitly added;
neither preparation nor validation discovers arbitrary schema sources. Re-run
preparation, the full gate and regressions after every lock update.

Regression checks (same dependencies, no cluster):

```sh
.tmp/validation-venv/bin/python -m unittest discover -s tests -v
pre-commit run --all-files
```
