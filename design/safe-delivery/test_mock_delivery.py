"""Exercise model failures through its process exit status, entirely offline."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
INVENTORY = json.loads((HERE / "observed.json").read_text())
SHA = INVENTORY["baseline"]


def fixture(app="n8n"):
    row = next(a for a in INVENTORY["applications"] if a["app"] == app)
    # These outcomes are invented for the model; they are NOT live evidence.
    workloads = {f"{w['kind']}/{w['namespace']}/{w['name']}": 1
                 for w in row["workloads"]}
    target = {
        "spec_digest": "synthetic-reviewed-spec-digest",
        "source_mode": row["source_mode"], "sources": row["sources"],
        "revisions": row["observed_revisions"],
        "field_checks": {"reviewed-field-digest": "synthetic-match"},
        "workloads": workloads,
        "no_workload_reason": "configuration-only application" if not workloads else "",
        "endpoint": {"required": bool(workloads), "accepted_statuses": [200],
                     "not_applicable_reason": "configuration-only" if not workloads else ""},
    }
    return {
        "now": 1000, "request": {"app": app, "action": "verify"},
        "plan": {"repo_url": "https://github.com/loushomelab/homelab-talos-iac.git",
                 "local_head": SHA, "remote_head": SHA, "clean": True,
                 "created_at": 900, "max_age_seconds": 300,
                 "applications": {app: deepcopy(target)}},
        "observed": {
            "app": app, "remote_head": SHA, "captured_at": 990,
            "parent_revision": SHA, "spec_digest": target["spec_digest"],
            "source_mode": target["source_mode"], "sources": deepcopy(target["sources"]),
            "revisions": deepcopy(target["revisions"]), "comparison_matches": True,
            "operation_running": False, "current_target_operation_failed": False,
            "error_conditions": [], "sync": "Synced", "health": "Healthy",
            "field_checks": deepcopy(target["field_checks"]),
            "workloads": {key: {"desired": count, "total": count, "updated": count,
                                "ready": count, "generation": 2, "observed_generation": 2,
                                "current_revision": "new", "update_revision": "new"}
                          for key, count in workloads.items()},
            "endpoint": {"tls_verified": True, "status": 200, "assertion_passed": True},
        },
    }


def change(data, path, value):
    for part in path[:-1]:
        data = data[part]
    data[path[-1]] = value


class ContractModel(unittest.TestCase):
    def check_process(self, data, code, stage):
        result = subprocess.run([sys.executable, str(HERE / "mock_delivery.py")],
                                input=json.dumps(data), text=True, capture_output=True,
                                timeout=5, check=False)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["stage"], stage)
        self.assertEqual(verdict["ok"], code == 0)

    def test_source_types_and_workload_kinds(self):
        for app in ("homepage", "forgejo", "n8n", "n8n-sandbox", "argocd-self-managed",
                    "traefik", "external-secrets"):
            with self.subTest(app=app):
                self.check_process(fixture(app), 0, "verified")

    def test_failures_reach_process_exit(self):
        cases = [
            ("unknown", ["request", "app"], "unknown", "input"),
            ("shell input", ["request", "app"], "n8n; touch forbidden", "input"),
            ("sync forbidden", ["request", "action"], "sync", "input"),
            ("old checkout", ["plan", "local_head"], "ee08022" + "0" * 33, "baseline"),
            ("dirty", ["plan", "clean"], False, "baseline"),
            ("remote advanced", ["observed", "remote_head"], "f" * 40, "baseline"),
            ("old plan", ["plan", "created_at"], 100, "baseline"),
            ("old evidence", ["observed", "captured_at"], 100, "baseline"),
            ("future evidence", ["observed", "captured_at"], 1001, "baseline"),
            ("old tier", ["observed", "parent_revision"], "f" * 40, "parent"),
            ("values changed same chart", ["observed", "spec_digest"], "old-values", "parent"),
            ("changed mode", ["observed", "source_mode"], "source", "source"),
            ("changed repo", ["observed", "sources", 1, "repoURL"], "other.git", "source"),
            ("changed path", ["observed", "sources", 1, "path"], "other", "source"),
            ("missing revision", ["observed", "revisions"], ["2.1.1"], "revision"),
            ("all sha", ["observed", "revisions"], [SHA, SHA], "revision"),
            ("wrong git commit", ["observed", "revisions"], ["2.1.1", "f" * 40], "revision"),
            ("old comparison", ["observed", "comparison_matches"], False, "revision"),
            ("failed sync", ["observed", "current_target_operation_failed"], True, "reconcile"),
            ("running sync", ["observed", "operation_running"], True, "reconcile"),
            ("comparison error", ["observed", "error_conditions"], ["ComparisonError"], "reconcile"),
            ("out of sync", ["observed", "sync"], "OutOfSync", "reconcile"),
            ("degraded", ["observed", "health"], "Degraded", "reconcile"),
            ("wrong field", ["observed", "field_checks"], {"field": "old"}, "fields"),
            ("missing workload", ["observed", "workloads"], {}, "workload"),
            ("rollout failed", ["observed", "workloads", "Deployment/n8n/n8n", "ready"], 0, "workload"),
            ("old generation", ["observed", "workloads", "Deployment/n8n/n8n", "observed_generation"], 1, "workload"),
            ("extra old replicas", ["observed", "workloads", "Deployment/n8n/n8n", "total"], 2, "workload"),
            ("bad TLS", ["observed", "endpoint", "tls_verified"], False, "endpoint"),
            ("login redirect not service", ["observed", "endpoint", "status"], 302, "endpoint"),
            ("wrong endpoint content", ["observed", "endpoint", "assertion_passed"], False, "endpoint"),
        ]
        for name, path, value, stage in cases:
            with self.subTest(case=name):
                data = fixture()
                change(data, path, value)
                self.check_process(data, 1, stage)

    def test_external_repo_and_order_are_independent(self):
        data = fixture("n8n-sandbox")
        data["observed"]["revisions"] = [SHA]
        self.check_process(data, 1, "revision")
        data = fixture()
        data["observed"]["sources"].reverse()
        data["observed"]["revisions"].reverse()
        self.check_process(data, 1, "source")

    def test_zero_capacity_and_stateful_revision(self):
        data = fixture("traefik")
        key = "DaemonSet/traefik/traefik"
        data["plan"]["applications"]["traefik"]["workloads"][key] = 0
        data["observed"]["workloads"][key] = dict.fromkeys(
            ("desired", "ready", "updated", "total", "generation", "observed_generation"), 0)
        self.check_process(data, 1, "workload")
        data = fixture("n8n-sandbox")
        data["observed"]["workloads"]["StatefulSet/n8n/sandbox-privileged-runner"]["current_revision"] = "old"
        self.check_process(data, 1, "workload")

    def test_bad_input(self):
        self.check_process({}, 2, "input")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--example":
        print(json.dumps(fixture(), indent=2))
    else:
        unittest.main()
