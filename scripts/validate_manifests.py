#!/usr/bin/env python3
"""Offline YAML/basic Kubernetes envelope checks; no API or schema discovery."""

import argparse
from pathlib import Path
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("ERROR: missing PyYAML; install scripts/requirements-validation.txt first")


HOMEPAGE = Path("argocd/configs/workloads/homepage/manifests")
KUSTOMIZATION_NAMES = {"kustomization.yaml", "kustomization.yml", "Kustomization"}


class ValidationError(Exception):
    pass


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys without logging their values."""

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    None, None, "duplicate mapping key", key_node.start_mark
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def documents(content, label):
    try:
        return [doc for doc in yaml.load_all(content, Loader=UniqueLoader) if doc is not None]
    except (yaml.YAMLError, ValueError, TypeError, RecursionError) as error:
        mark = getattr(error, "problem_mark", None)
        location = f":{mark.line + 1}:{mark.column + 1}" if mark else ""
        # Parser exceptions include source snippets; never print them.
        raise ValidationError(f"{label}{location}: invalid YAML or duplicate key") from None


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ValidationError(f"{path}: cannot read UTF-8 input") from None


def resource(doc, label):
    if not isinstance(doc, dict):
        raise ValidationError(f"{label}: resource must be a mapping")
    for field in ("apiVersion", "kind"):
        if not isinstance(doc.get(field), str) or not doc[field].strip():
            raise ValidationError(f"{label}: missing or invalid {field}")
    if doc["kind"] == "Kustomization":
        raise ValidationError(f"{label}: Kustomization is a build input, not a resource")
    if doc["kind"] == "List":
        if not isinstance(doc.get("items"), list) or not doc["items"]:
            raise ValidationError(f"{label}: List requires nonempty items")
        return sum(resource(item, f"{label}, item {i}") for i, item in enumerate(doc["items"], 1))
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict) or not any(
        isinstance(metadata.get(key), str) and metadata[key].strip()
        for key in ("name", "generateName")
    ):
        raise ValidationError(f"{label}: metadata requires name or generateName")
    return 1


def validate(content, label):
    docs = documents(content, label)
    if not docs:
        raise ValidationError(f"{label}: no resources found")
    try:
        return sum(resource(doc, f"{label}, document {i}") for i, doc in enumerate(docs, 1))
    except RecursionError:
        raise ValidationError(f"{label}: recursive or excessively nested resource list") from None


def yaml_files(directory):
    files = sorted(p for p in directory.rglob("*") if p.suffix.lower() in {".yaml", ".yml", ".json"})
    if not directory.is_dir() or not files:
        raise ValidationError(f"{directory}: no manifest files found")
    return files


def local_file(directory, value, label):
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label}: expected a local file reference")
    path = directory / value
    if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
        raise ValidationError(f"{label}: references must be existing files within Homepage manifests")
    return path


def render_homepage(root):
    directory = root / HOMEPAGE
    path = directory / "kustomization.yaml"
    docs = documents(read(path), path)
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValidationError(f"{path}: expected one Kustomization mapping")
    config = docs[0]
    # This deliberately supports only the existing local build. Reject additional
    # build features instead of accidentally enabling remote bases/plugins/Helm.
    allowed = {"apiVersion", "kind", "namespace", "resources", "configMapGenerator", "generatorOptions"}
    if set(config) - allowed or config.get("kind") != "Kustomization":
        raise ValidationError(f"{path}: unsupported build fields; review offline support first")
    refs = config.get("resources")
    if not isinstance(refs, list) or not refs:
        raise ValidationError(f"{path}: resources must be a nonempty local file list")
    for i, ref in enumerate(refs, 1):
        source = local_file(directory, ref, f"{path}, resources[{i}]")
        validate(read(source), source)
    generators = config.get("configMapGenerator", [])
    if not isinstance(generators, list):
        raise ValidationError(f"{path}: configMapGenerator must be a list")
    for generator in generators:
        if not isinstance(generator, dict) or set(generator) - {"name", "files"}:
            raise ValidationError(f"{path}: only existing local file ConfigMap generators are supported")
        refs = generator.get("files")
        if not isinstance(refs, list):
            raise ValidationError(f"{path}: generator files must be a local file list")
        for i, ref in enumerate(refs, 1):
            # Kustomize permits key=path file references.
            value = ref.split("=", 1)[-1] if isinstance(ref, str) else ref
            local_file(directory, value, f"{path}, generator files[{i}]")
    try:
        result = subprocess.run(
            ["kubectl", "kustomize", str(directory)],
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
        )
    except FileNotFoundError:
        raise ValidationError(f"{path}: missing kubectl (local Kustomize renderer required)") from None
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise ValidationError(f"{path}: local Kustomize render failed or timed out") from None
    if result.returncode:
        # Renderer diagnostics may include ConfigMap contents or credentials.
        raise ValidationError(f"{path}: local Kustomize render failed; check referenced input files")
    return validate(result.stdout, f"{path} (rendered output)")


def run(root, target):
    directory = root / "argocd" / target
    count = 0
    for path in yaml_files(directory):
        if target == "configs":
            if path.is_relative_to(root / HOMEPAGE / "config"):
                continue  # Application template data, consumed by configMapGenerator.
            if path.name in KUSTOMIZATION_NAMES:
                if path != root / HOMEPAGE / "kustomization.yaml":
                    raise ValidationError(f"{path}: unregistered build input; add an explicit offline renderer")
                continue
        count += validate(read(path), path)
    print(f"OK: {target}: {count} source resources passed YAML/basic structure checks")
    if target == "configs":
        rendered = render_homepage(root)
        print(f"OK: Homepage: {rendered} rendered resources passed YAML/basic structure checks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("apps", "configs"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        run(args.root.resolve(), args.target)
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
