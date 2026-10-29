"""CLI regressions with real Kustomize and isolated, non-sensitive fixtures."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_manifests.py"
HOMEPAGE = Path("argocd/configs/workloads/homepage/manifests")
MANIFEST = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: example\n"
SENTINEL = "PRIVATE_FIXTURE_VALUE_MUST_NOT_BE_LOGGED"


class ValidationCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / HOMEPAGE
        self.write("argocd/apps/app.yaml", MANIFEST)
        self.write("argocd/configs/ordinary/resource.yaml", MANIFEST)
        self.write(HOMEPAGE / "resource.yaml", MANIFEST)
        self.write(HOMEPAGE / "config/template.yaml", "unparseable: {{APP_TEMPLATE}}\n")
        self.write(HOMEPAGE / "kustomization.yaml", (
            "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n"
            "resources:\n  - resource.yaml\nconfigMapGenerator:\n"
            "  - name: generated\n    files:\n      - config/template.yaml\n"
        ))
        self.env = os.environ.copy()
        self.env["KUBECONFIG"] = str(self.root / "invalid-kubeconfig")
        self.write("invalid-kubeconfig", "not: [a kubeconfig\n")
        self.env["KUBERNETES_MASTER"] = "http://127.0.0.1:1"

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_cli(self, target="configs"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), target, "--root", str(self.root)],
            capture_output=True, text=True, env=self.env, check=False,
        )

    def fake_kubectl(self, output, returncode=0):
        # Permit exactly one local render command. Any discovery/mutation fails.
        executable = self.write("bin/kubectl", (
            f"#!{sys.executable}\nimport sys\n"
            f"assert sys.argv[1:] == ['kustomize', {str(self.home)!r}]\n"
            f"print({output!r}, file=sys.stdout if {returncode} == 0 else sys.stderr)\n"
            f"sys.exit({returncode})\n"
        ))
        executable.chmod(0o700)
        self.env["PATH"] = str(executable.parent)

    def assert_failure(self, result, location):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(location, result.stderr)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_real_kustomize_works_with_invalid_kubeconfig_and_template_yaml(self):
        self.assertIsNotNone(shutil.which("kubectl"), "install kubectl before running regressions")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Homepage: 2 rendered resources", result.stdout)

    def test_apps_need_no_kubectl_or_cluster(self):
        self.env["PATH"] = str(self.root / "no-tools")
        self.assertEqual(self.run_cli("apps").returncode, 0)

    def test_invalid_ordinary_yaml_has_location_without_values(self):
        self.write("argocd/configs/ordinary/resource.yaml", f"password: [{SENTINEL}\n")
        result = self.run_cli()
        self.assert_failure(result, "ordinary/resource.yaml:")
        self.assertIn("invalid YAML", result.stderr)

    def test_ordinary_manifest_missing_kind_fails(self):
        self.write("argocd/configs/ordinary/resource.yaml", MANIFEST.replace("kind: ConfigMap\n", ""))
        self.assert_failure(self.run_cli(), "ordinary/resource.yaml, document 1: missing or invalid kind")

    def test_homepage_source_failure_identifies_file(self):
        self.write(HOMEPAGE / "resource.yaml", f"apiVersion: [{SENTINEL}\n")
        self.assert_failure(self.run_cli(), "homepage/manifests/resource.yaml:")

    def test_rendered_structure_is_validated(self):
        self.fake_kubectl(f"apiVersion: v1\nkind: Secret\nstringData:\n  password: {SENTINEL}\n")
        self.assert_failure(self.run_cli(), "kustomization.yaml (rendered output), document 1")

    def test_rendered_yaml_failure_is_sanitized(self):
        self.fake_kubectl(f"password: [{SENTINEL}\n")
        self.assert_failure(self.run_cli(), "kustomization.yaml (rendered output):")

    def test_renderer_failure_is_sanitized(self):
        self.fake_kubectl(SENTINEL, returncode=1)
        self.assert_failure(self.run_cli(), "kustomization.yaml: local Kustomize render failed")

    def test_remote_resource_rejected_before_renderer(self):
        path = self.home / "kustomization.yaml"
        path.write_text(path.read_text().replace("resource.yaml", "https://example.invalid/base"))
        self.fake_kubectl(SENTINEL)
        self.assert_failure(self.run_cli(), "references must be existing files")

    def test_remote_build_feature_rejected_before_renderer(self):
        with (self.home / "kustomization.yaml").open("a") as handle:
            handle.write("openapi:\n  path: https://example.invalid/schema.json\n")
        self.fake_kubectl(SENTINEL)
        self.assert_failure(self.run_cli(), "unsupported build fields")

    def test_missing_generator_file_fails(self):
        (self.home / "config/template.yaml").unlink()
        self.assert_failure(self.run_cli(), "generator files[1]")

    def test_generator_symlink_outside_build_rejected(self):
        template = self.home / "config/template.yaml"
        template.unlink()
        template.symlink_to(self.write("outside.yaml", SENTINEL))
        self.assert_failure(self.run_cli(), "references must be existing files")

    def test_missing_renderer_is_actionable(self):
        self.env["PATH"] = str(self.root / "no-tools")
        self.assert_failure(self.run_cli(), "missing kubectl")

    def test_duplicate_keys_rejected_without_value_leak(self):
        self.write("argocd/apps/app.yaml", MANIFEST + f"kind: {SENTINEL}\n")
        self.assert_failure(self.run_cli("apps"), "duplicate key")

    def test_lists_validate_each_item(self):
        self.write("argocd/apps/app.yaml", "apiVersion: v1\nkind: List\nitems:\n  - kind: Secret\n")
        self.assert_failure(self.run_cli("apps"), "item 1: missing or invalid apiVersion")

    def test_empty_file_fails(self):
        self.write("argocd/apps/app.yaml", "# only a comment\n---\n")
        self.assert_failure(self.run_cli("apps"), "no resources found")

    def test_recursive_resource_list_fails_without_traceback(self):
        self.write("argocd/apps/app.yaml", "&loop\napiVersion: v1\nkind: List\nitems: [*loop]\n")
        self.assert_failure(self.run_cli("apps"), "recursive or excessively nested resource list")

    def test_unknown_kustomization_is_not_silently_skipped(self):
        self.write("argocd/configs/ordinary/kustomization.yaml", "kind: Kustomization\n")
        self.assert_failure(self.run_cli(), "unregistered build input")


if __name__ == "__main__":
    unittest.main()
