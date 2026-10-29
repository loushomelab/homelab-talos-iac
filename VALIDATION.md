# Local validation

`task val:all` checks applications, configs and Renovate JSON locally. It does
not need kubeconfig, Kubernetes API discovery or a reachable cluster. These
tasks never apply, patch, delete, sync or deploy resources.

Prepare dependencies **before going offline**:

```sh
python3 -m venv .tmp/validation-venv
.tmp/validation-venv/bin/python -m pip install -r scripts/requirements-validation.txt
export PATH="$PWD/.tmp/validation-venv/bin:$PATH"
task val:all
```

Requirements: Python 3.10+, pinned PyYAML, `kubectl` with bundled Kustomize,
Node.js (Renovate JSON syntax), and Go Task v3 for the task shortcuts. Tested
with Python 3.14, kubectl 1.37.2 / Kustomize 5.8.1. For air-gapped setup,
preinstall these tools and cache the PyYAML wheel; pip can install using
`--no-index --find-links <wheel-directory>`. Validation downloads nothing and
uses no schema files.

Without Go Task, run the equivalent commands from the repository root:

```sh
.tmp/validation-venv/bin/python scripts/validate_manifests.py apps
.tmp/validation-venv/bin/python scripts/validate_manifests.py configs
node -e 'JSON.parse(require("fs").readFileSync("renovate.json", "utf8"))'
```

Use `task val:apps`, `task val:configs` or `task val:renovate` individually.
You can also select the interpreter with `task val:configs PYTHON=<python-path>`.

All YAML/YML/JSON manifests under `argocd/apps` and `argocd/configs` are parsed
with duplicate-key detection. Each resource needs string `apiVersion`, `kind`
and `metadata.name` or `metadata.generateName`; Kubernetes `List` items are
checked recursively. Blank document separators are allowed, empty files fail.

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

This is **YAML and basic resource structure validation**, not Kubernetes or CRD
schema validation. It cannot verify fields under `spec`, API availability,
references, admission rules or runtime behavior. CI schema versions, missing
schema policy and CRD coverage remain a separate follow-up; the existing CI
workflow is unchanged.

Regression checks (same dependencies, no cluster):

```sh
.tmp/validation-venv/bin/python -m unittest discover -s tests -v
pre-commit run --all-files
```
