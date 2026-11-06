#!/usr/bin/env python3
"""Explicit network preparation of reviewed, checksum-locked schema sources."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from validate_manifests import ValidationError, documents, read


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "validation/schema-lock.json"
CACHE = ROOT / ".cache/validation-schemas"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def schema_path(cache, api_version, kind):
    # Same full-group layout as kubeconform's Group/ResourceKind/APIVersion template.
    if not re.fullmatch(r"[a-z0-9.-]+(?:/[a-z0-9]+)?", api_version) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", kind):
        raise ValidationError("invalid schema resource identity")
    group, version = api_version.split("/") if "/" in api_version else (api_version, api_version)
    return cache / group / f"{kind.lower()}_{version}.json"


def normalize(schema):
    """Convert structural OpenAPI to strict JSON Schema, retaining opaque maps."""
    if isinstance(schema, list):
        return [normalize(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = copy.deepcopy(schema)
    # Traverse schema positions only: a user field named "nullable" or
    # "properties" inside a properties map is not a schema keyword.
    for key in ("properties", "patternProperties", "definitions", "$defs"):
        if isinstance(result.get(key), dict):
            result[key] = {name: normalize(value) for name, value in result[key].items()}
    for key in ("items", "additionalProperties", "not", "contains"):
        if isinstance(result.get(key), (dict, list)):
            result[key] = normalize(result[key])
    for key in ("allOf", "anyOf", "oneOf"):
        if isinstance(result.get(key), list):
            result[key] = normalize(result[key])
    if result.get("format") == "int-or-string" or result.get("x-kubernetes-int-or-string"):
        result.pop("format", None)
        result.pop("type", None)
        result["anyOf"] = [{"type": "integer"}, {"type": "string"}]
    if "properties" in result and not result.get("x-kubernetes-preserve-unknown-fields"):
        result.setdefault("additionalProperties", False)
    if result.pop("nullable", False) and isinstance(result.get("type"), str):
        result["type"] = [result["type"], "null"]
    return result


def encoded(schema):
    # Canonical bytes make the generated output independently checksum-verifiable.
    return (json.dumps(schema, sort_keys=True, separators=(",", ":")) + "\n").encode()


def convert(data, source, entry):
    if source["format"] == "json":
        schema = json.loads(data)
    else:
        definitions = documents(data.decode("utf-8"), source["name"])
        matches = [version["schema"]["openAPIV3Schema"]
                   for crd in definitions if crd.get("kind") == "CustomResourceDefinition"
                   and crd["spec"]["names"]["kind"] == entry["kind"]
                   for version in crd["spec"]["versions"]
                   if f'{crd["spec"]["group"]}/{version["name"]}' == entry["apiVersion"]
                   and version.get("served")]
        if len(matches) != 1:
            raise ValidationError(f'{source["name"]}: expected one served CRD schema')
        schema = normalize(copy.deepcopy(matches[0]))
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        schema.setdefault("properties", {}).update({
            "apiVersion": {"type": "string", "enum": [entry["apiVersion"]]},
            "kind": {"type": "string", "enum": [entry["kind"]]},
        })
    check_refs(schema)
    return encoded(schema)


def check_refs(value):
    if isinstance(value, dict):
        if "$ref" in value and not value["$ref"].startswith("#"):
            raise ValidationError("external schema references are unsupported; vendor standalone schemas")
        for child in value.values():
            check_refs(child)
    elif isinstance(value, list):
        for child in value:
            check_refs(child)


def load_lock(path=LOCK):
    lock = json.loads(read(path))
    identities = set()
    for source in lock["sources"]:
        # No floating branches, arbitrary hosts, cluster discovery, or schema catalogs.
        if not re.fullmatch(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/[0-9a-f]{40}/[\w./-]+", source["url"]):
            raise ValidationError("schema sources must be immutable raw GitHub commit URLs")
        if source["format"] not in {"json", "crd"}:
            raise ValidationError("unsupported schema source format")
        if source["format"] == "json" and f'/v{lock["kubernetes_version"]}-standalone-strict/' not in source["url"]:
            raise ValidationError("core schema version differs from the Kubernetes target")
        for entry in source["schemas"]:
            identity = (entry["apiVersion"], entry["kind"])
            schema_path(Path("."), *identity)
            if identity in identities:
                raise ValidationError("duplicate schema identity in lock")
            identities.add(identity)
    return lock


def prepare(lock, cache):
    for source in lock["sources"]:
        if all((path := schema_path(cache, entry["apiVersion"], entry["kind"])).is_file()
               and digest(path.read_bytes()) == entry["sha256"] for entry in source["schemas"]):
            continue
        try:
            with urllib.request.urlopen(source["url"], timeout=60) as response:
                data = response.read()
        except (OSError, urllib.error.URLError):
            raise ValidationError(f'{source["name"]}: trusted schema download failed') from None
        if digest(data) != source["sha256"]:
            raise ValidationError(f'{source["name"]}: source checksum mismatch')
        for entry in source["schemas"]:
            output = convert(data, source, entry)
            if digest(output) != entry["sha256"]:
                raise ValidationError(f'{source["name"]}: generated schema checksum mismatch')
            path = schema_path(cache, entry["apiVersion"], entry["kind"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(output)
    print(f'OK: prepared {sum(len(source["schemas"]) for source in lock["sources"])} locked schemas')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    try:
        prepare(load_lock(), args.cache.resolve())
    except (ValidationError, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        message = str(error) if isinstance(error, ValidationError) else "invalid schema lock or source; raw diagnostics suppressed"
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
