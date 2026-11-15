"""HOM-7 isolated contract model. JSON in, verdict out; no live adapters.

The approved plan and observations are synthetic, trusted test inputs. This is
not a production verifier, revision resolver, sync command or security boundary.
"""

import json
import re
import sys


class Rejected(Exception):
    def __init__(self, stage, reason):
        self.stage, self.reason = stage, reason


def require(ok, stage, reason):
    if not ok:
        raise Rejected(stage, reason)


def verify(data):
    plan, observed = data["plan"], data["observed"]
    app = data["request"]["app"]
    require(app in plan["applications"], "input", "unknown_application")
    expected = plan["applications"][app]
    require(observed["app"] == app, "input", "wrong_application")
    require(data["request"]["action"] == "verify", "input", "mutation_forbidden")
    require(plan["clean"] and plan["local_head"] == plan["remote_head"],
            "baseline", "stale_or_dirty_checkout")
    require(observed["remote_head"] == plan["remote_head"],
            "baseline", "remote_moved")
    for timestamp in (plan["created_at"], observed["captured_at"]):
        require(0 <= data["now"] - timestamp <= plan["max_age_seconds"],
                "baseline", "expired_or_future_evidence")
    require(observed["parent_revision"] == plan["remote_head"],
            "parent", "parent_revision_mismatch")
    require(observed["spec_digest"] == expected["spec_digest"],
            "parent", "application_spec_mismatch")
    require(observed["source_mode"] == expected["source_mode"],
            "source", "source_mode_changed")
    require(observed["sources"] == expected["sources"],
            "source", "ordered_source_identity_mismatch")
    sources, revisions = expected["sources"], expected["revisions"]
    require(len(sources) > 0 and len(sources) == len(revisions),
            "source", "incomplete_plan")
    for source, revision in zip(sources, revisions):
        if "chart" in source:
            require(revision == source["targetRevision"] and
                    re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", revision),
                    "source", "chart_requires_exact_version")
        else:
            require(re.fullmatch(r"[0-9a-f]{40}", revision),
                    "source", "git_requires_full_commit")
            # Only this repository may be bound to the approved main SHA.
            if source["repoURL"] == plan["repo_url"]:
                require(revision == plan["remote_head"], "source", "wrong_git_target")
    require(observed["revisions"] == revisions,
            "revision", "exact_revision_vector_mismatch")
    require(observed["comparison_matches"], "revision", "stale_compared_to")
    require(not observed["operation_running"] and
            not observed["current_target_operation_failed"],
            "reconcile", "operation_not_successful")
    require(not observed["error_conditions"] and
            observed["sync"] == "Synced" and observed["health"] == "Healthy",
            "reconcile", "application_not_ready")
    require(expected["field_checks"] and
            observed["field_checks"] == expected["field_checks"],
            "fields", "changed_fields_missing_or_wrong")
    require(set(observed["workloads"]) == set(expected["workloads"]),
            "workload", "workload_set_mismatch")
    require(bool(expected["workloads"]) or expected["no_workload_reason"],
            "workload", "unexplained_empty_workload_set")
    for key, desired in expected["workloads"].items():
        actual = observed["workloads"][key]
        kind = key.split("/", 1)[0]
        require(kind in ("Deployment", "StatefulSet", "DaemonSet"),
                "workload", "unsupported_workload_kind")
        require(desired > 0 and actual["desired"] == desired,
                "workload", "zero_or_unexpected_capacity")
        require(actual["observed_generation"] == actual["generation"] and
                actual["updated"] == desired and actual["ready"] == desired and
                actual["total"] == desired,
                "workload", "rollout_incomplete")
        if kind == "StatefulSet":
            require(actual["current_revision"] == actual["update_revision"],
                    "workload", "statefulset_revision_mismatch")
    endpoint = expected["endpoint"]
    if endpoint["required"]:
        require(observed["endpoint"]["tls_verified"] and
                observed["endpoint"]["status"] in endpoint["accepted_statuses"] and
                observed["endpoint"]["assertion_passed"],
                "endpoint", "endpoint_assertion_failed")
    else:
        require(bool(endpoint["not_applicable_reason"]),
                "endpoint", "unexplained_endpoint_skip")
    return {"ok": True, "stage": "verified", "scope": "synthetic_only"}


def main():
    try:
        result = verify(json.load(sys.stdin))
    except Rejected as error:
        # Fixed identifiers only: never print source input, values or secrets.
        print(json.dumps({"ok": False, "stage": error.stage, "reason": error.reason}))
        return 1
    except (ValueError, KeyError, TypeError, AttributeError):
        print(json.dumps({"ok": False, "stage": "input", "reason": "invalid_fixture"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
