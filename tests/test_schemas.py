"""Real schema-gate regressions. Prepare locked schemas and tools before running."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_schemas import CACHE, ValidationError, convert, digest, load_lock, normalize, prepare, schema_path


SENTINEL = "PRIVATE_FIXTURE_VALUE_MUST_NOT_BE_LOGGED"
CONFIGMAP = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "fixture"},
             "data": {"unicode": "Unicode survives the YAML/JSON boundary: 🚀"}}


class SchemaCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "argocd/apps/fixture.yaml"
        self.manifest.parent.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env["KUBECONFIG"] = str(self.root / "bad-kubeconfig")
        (self.root / "bad-kubeconfig").write_text("invalid: [kubeconfig\n")
        self.env["KUBERNETES_MASTER"] = "http://127.0.0.1:1"
        self.write(CONFIGMAP)

    def write(self, doc):
        self.manifest.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    def cli(self, cache=CACHE, target="apps"):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_schemas.py"), "--root", str(self.root),
             "--cache", str(cache), *(["--target", target] if target else [])],
            capture_output=True, text=True, env=self.env, check=False,
        )

    def assert_rejected(self, result, summary):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(summary, result.stdout)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_real_valid_unicode_manifest_needs_no_kubeconfig(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validated=1 skipped=0 failed=0", result.stdout)

    def test_known_core_field_type_and_unknown_field_fail_without_values(self):
        for doc in [dict(CONFIGMAP, data={"password": {"private": SENTINEL}}),
                    dict(CONFIGMAP, unknownField=SENTINEL)]:
            with self.subTest(doc_keys=list(doc)):
                self.write(doc)
                self.assert_rejected(self.cli(), "validated=0 skipped=0 failed=1")

    def test_key_crd_valid_baselines_pass_and_invalid_specs_fail(self):
        fixtures = [
            ("argoproj.io/v1alpha1", "Application", {"project": "default", "source": {
                "repoURL": "https://example.invalid/repo.git", "path": "manifests"},
                "destination": {"server": "https://kubernetes.default.svc", "namespace": "fixture"}},
             "project", {"private": SENTINEL}),
            ("external-secrets.io/v1", "ExternalSecret", {
                "refreshInterval": "1h", "secretStoreRef": {"name": "fixture", "kind": "ClusterSecretStore"},
                "data": [{"secretKey": "test", "remoteRef": {"key": "test"}}]},
             "refreshInterval", {"private": SENTINEL}),
            ("traefik.io/v1alpha1", "IngressRoute", {"entryPoints": ["web"], "routes": [
                {"kind": "Rule", "match": "Host(`example.invalid`)", "services": [{"name": "fixture", "port": 80}]}]},
             "entryPoints", {"private": SENTINEL}),
            ("metallb.io/v1beta1", "IPAddressPool", {"addresses": ["192.0.2.0/24"]},
             "addresses", {"private": SENTINEL}),
        ]
        for api, kind, spec, key, invalid in fixtures:
            with self.subTest(kind=kind):
                doc = {"apiVersion": api, "kind": kind, "metadata": {"name": "fixture"}, "spec": spec}
                self.write(doc)
                result = self.cli()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                bad = copy.deepcopy(doc)
                bad["spec"][key] = invalid
                self.write(bad)
                self.assert_rejected(self.cli(), "validated=0 skipped=0 failed=1")
                bad = copy.deepcopy(doc)
                bad["spec"]["definitelyUnknownField"] = SENTINEL
                self.write(bad)
                self.assert_rejected(self.cli(), "validated=0 skipped=0 failed=1")

    def test_unknown_group_and_unknown_version_cannot_fall_back_by_kind(self):
        for api in ("unknown.example/v1", "v99"):
            with self.subTest(api=api):
                self.write(dict(CONFIGMAP, apiVersion=api))
                self.assert_rejected(self.cli(), "validated=0 skipped=1 failed=0 missing_schema=1")

    def test_missing_locked_schema_is_counted_and_fails(self):
        self.assert_rejected(self.cli(self.root / "empty-cache"), "skipped=1 failed=0 missing_schema=1")

    def test_corrupt_schema_fails_without_fallback_or_value_leak(self):
        cache = self.root / "corrupt-cache"
        path = schema_path(cache, "v1", "ConfigMap")
        path.parent.mkdir(parents=True)
        path.write_text(SENTINEL)
        self.assert_rejected(self.cli(cache), "validated=0 skipped=0 failed=1")

    def test_nested_list_items_are_individually_schema_checked(self):
        bad = dict(CONFIGMAP, data={"password": {"private": SENTINEL}})
        self.write({"apiVersion": "v1", "kind": "List", "items": [CONFIGMAP, {
            "apiVersion": "v1", "kind": "List", "items": [bad]}]})
        result = self.cli()
        self.assert_rejected(result, "validated=1 skipped=0 failed=1")
        self.assertIn("item 2, item 1", result.stdout)

    def test_bootstrap_resources_checked_and_values_reported_as_input(self):
        bootstrap = self.root / "argocd/bootstrap"
        bootstrap.mkdir()
        (bootstrap / "resource.yaml").write_text(yaml.safe_dump(CONFIGMAP, allow_unicode=True))
        (bootstrap / "values.yaml").write_text("helm: values\n")
        result = self.cli(target="bootstrap")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("values.yaml: Helm values", result.stdout)
        (bootstrap / "resource.yaml").write_text(yaml.safe_dump(dict(CONFIGMAP, typo=SENTINEL)))
        self.assert_rejected(self.cli(target="bootstrap"), "failed=1")

    def test_real_homepage_configmap_and_rendered_deployment_are_checked(self):
        home = self.root / "argocd/configs/workloads/homepage/manifests"
        home.mkdir(parents=True)
        (home / "resource.yaml").write_text(yaml.safe_dump(CONFIGMAP, allow_unicode=True))
        (home / "template.txt").write_text("template: {{APP_VAR}}\n")
        (home / "kustomization.yaml").write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n"
            "resources: [resource.yaml]\nconfigMapGenerator:\n- name: generated\n  files: [template.txt]\n")
        result = self.cli(target="configs")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validated=3 skipped=0 failed=0", result.stdout)
        # Inject a schema-only error in rendered output, keeping source YAML valid.
        executable = self.root / "bin/kubectl"
        executable.parent.mkdir()
        bad = dict(CONFIGMAP, data={"password": {"private": SENTINEL}})
        executable.write_text(f"#!{sys.executable}\nprint({yaml.safe_dump(bad)!r})\n")
        executable.chmod(0o700)
        self.env["PATH"] = str(executable.parent) + os.pathsep + self.env["PATH"]
        result = self.cli(target="configs")
        self.assert_rejected(result, "validated=1 skipped=0 failed=1")
        self.assertIn("(rendered output), document 1", result.stdout)

    def test_missing_kubeconform_is_actionable_and_has_summary(self):
        self.env["PATH"] = str(self.root / "missing-tools")
        result = self.cli()
        self.assert_rejected(result, "input_or_tool_error=1")
        self.assertIn("missing kubeconform", result.stderr)

    def test_unclassified_manifests_are_rejected_in_full_gate(self):
        (self.root / "argocd/unregistered.yaml").write_text(yaml.safe_dump(CONFIGMAP))
        result = self.cli(target=None)
        self.assert_rejected(result, "input_or_tool_error=1")
        self.assertIn("unclassified manifest", result.stderr)

    def test_wrong_tool_version_is_rejected(self):
        executable = self.root / "bin/kubeconform"
        executable.parent.mkdir()
        executable.write_text(f"#!{sys.executable}\nprint('v0.0.0')\n")
        executable.chmod(0o700)
        self.env["PATH"] = str(executable.parent)
        result = self.cli()
        self.assert_rejected(result, "input_or_tool_error=1")
        self.assertIn("install kubeconform v0.7.0", result.stderr)


class SchemaPreparation(unittest.TestCase):
    def test_prepared_cache_reuse_checks_hashes_without_network(self):
        # A prepared cache must be sufficient even when all networking is denied.
        with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network request")):
            prepare(load_lock(), CACHE)
        for source in load_lock()["sources"]:
            for entry in source["schemas"]:
                path = schema_path(CACHE, entry["apiVersion"], entry["kind"])
                self.assertEqual(digest(path.read_bytes()), entry["sha256"])

    def test_unknown_properties_are_closed_but_preserved_maps_remain_open(self):
        result = normalize({"type": "object", "properties": {
            "nullable": {"type": "string"}, "properties": {"type": "string"},
            "opaque": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
            "ports": {"type": "array", "items": {"type": "object", "properties": {
                "port": {"x-kubernetes-int-or-string": True}}}}}})
        self.assertFalse(result["additionalProperties"])
        self.assertIn("nullable", result["properties"])
        self.assertIn("properties", result["properties"])
        self.assertNotIn("additionalProperties", result["properties"]["opaque"])
        self.assertFalse(result["properties"]["ports"]["items"]["additionalProperties"])
        self.assertEqual(result["properties"]["ports"]["items"]["properties"]["port"]["anyOf"],
                         [{"type": "integer"}, {"type": "string"}])

    def test_external_schema_refs_are_rejected_before_use(self):
        with self.assertRaises(ValidationError):
            convert(json.dumps({"$ref": "https://example.invalid/untrusted.json"}).encode(),
                    {"format": "json"}, {})

    def test_source_checksum_mismatch_cannot_populate_cache(self):
        from io import BytesIO
        with tempfile.TemporaryDirectory() as temporary:
            with patch("urllib.request.urlopen", return_value=BytesIO(b"unexpected source contents")):
                with self.assertRaisesRegex(ValidationError, "source checksum mismatch"):
                    prepare(load_lock(), Path(temporary))
            self.assertEqual(list(Path(temporary).rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
