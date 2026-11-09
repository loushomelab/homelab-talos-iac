#!/usr/bin/env python3
"""Offline schema gate using the existing manifest classification and renderer."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from prepare_schemas import CACHE, ROOT, check_refs, digest, load_lock, schema_path
from validate_manifests import ValidationError, run, run_all


def validate(root, cache, targets, lock):
    resources = []
    def collect(doc, label):
        resources.append((doc, label))
    if targets:
        for target in targets:
            run(root, target, collect)
    else:
        run_all(root, collect)
    registry = {(entry["apiVersion"], entry["kind"]): entry
                for source in lock["sources"] for entry in source["schemas"]}
    totals = Counter(validated=0, skipped=0, failed=0, missing_schema=0)
    coverage = {}
    with tempfile.TemporaryDirectory(prefix="manifest-schema-") as temporary:
        labels = {}
        checked = set()
        for index, (doc, label) in enumerate(resources):
            identity = (doc["apiVersion"], doc["kind"])
            counts = coverage.setdefault(identity, Counter(validated=0, skipped=0, failed=0))
            entry = registry.get(identity)
            path = schema_path(cache, *identity) if entry else None
            if not entry or not path.is_file():
                totals["skipped"] += 1
                totals["missing_schema"] += 1
                counts["skipped"] += 1
                print(f"MISSING_SCHEMA: {label}: add a reviewed schema or run scripts/prepare_schemas.py")
                continue
            try:
                if identity not in checked:
                    data = path.read_bytes()
                    if digest(data) != entry["sha256"]:
                        raise ValidationError("checksum mismatch")
                    check_refs(json.loads(data))
                    checked.add(identity)
            except (OSError, ValueError, ValidationError):
                totals["failed"] += 1
                counts["failed"] += 1
                print(f"SCHEMA_ERROR: {label}: locked schema is corrupt or unsafe; prepare it again")
                continue
            filename = str(Path(temporary) / f"{index}.json")
            # kubeconform's YAML reader rejects JSON surrogate-pair escapes.
            Path(filename).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            labels[filename] = (label, counts)

        if labels:
            try:
                version = subprocess.run(["kubeconform", "-v"], capture_output=True, text=True, timeout=10, check=False)
                if version.returncode or version.stdout.strip() != lock["kubeconform_version"]:
                    raise ValidationError(f'install kubeconform {lock["kubeconform_version"]} from its release archive')
                result = subprocess.run(
                    ["kubeconform", "-strict", "-verbose", "-summary", "-output", "json",
                     "-kubernetes-version", lock["kubernetes_version"],
                     "-schema-location", str(cache / "{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"),
                     *labels], capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
                )
                report = json.loads(result.stdout)
                # Do not accept partial/empty output or any implicit kubeconform skip.
                statuses = {"statusValid": "validated", "statusInvalid": "failed", "statusError": "failed"}
                rows = report["resources"]
                if (len(rows) != len(labels) or {row["filename"] for row in rows} != set(labels)
                        or any(row["status"] not in statuses for row in rows)
                        or report["summary"]["skipped"] != 0
                        or result.returncode not in {0, 1}):
                    raise ValueError("incomplete schema report")
                for row in rows:
                    label, counts = labels[row["filename"]]
                    status = statuses[row["status"]]
                    totals[status] += 1
                    counts[status] += 1
                    if status == "failed":
                        # Raw messages include offending field values; print location only.
                        print(f"SCHEMA_FAILED: {label}: resource does not pass its locked schema")
            except FileNotFoundError:
                raise ValidationError("missing kubeconform; install the version in validation/schema-lock.json") from None
            except (OSError, UnicodeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
                raise ValidationError("kubeconform failed or returned an incomplete report; raw diagnostics suppressed") from None

    for (api, kind), counts in sorted(coverage.items()):
        print(f'COVERAGE: {api} {kind}: validated={counts["validated"]} skipped={counts["skipped"]} failed={counts["failed"]}')
    print(f'SUMMARY: Kubernetes {lock["kubernetes_version"]}: validated={totals["validated"]} '
          f'skipped={totals["skipped"]} failed={totals["failed"]} missing_schema={totals["missing_schema"]}')
    return int(bool(totals["skipped"] or totals["failed"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--target", choices=("apps", "configs", "bootstrap"), action="append")
    args = parser.parse_args()
    try:
        return validate(args.root.resolve(), args.cache.resolve(), args.target, load_lock())
    except (ValidationError, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        message = str(error) if isinstance(error, ValidationError) else "invalid schema configuration or input; raw diagnostics suppressed"
        print(f"ERROR: {message}", file=sys.stderr)
        print("SUMMARY: validated=0 skipped=0 failed=1 input_or_tool_error=1")
        return 1


if __name__ == "__main__":
    sys.exit(main())
