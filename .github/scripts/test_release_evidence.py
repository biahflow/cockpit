#!/usr/bin/env python3
"""Regression tests for immutable release evidence and workflow safety."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import release_evidence  # noqa: E402

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def hml_payload() -> dict:
    return {
        "schema_version": 1,
        "source_sha": SHA,
        "repository": "biahflow/pulse",
        "hml": {"workflow_run_id": 123, "workflow_run_attempt": 2, "status": "validated"},
        "images": {
            "backend": {
                "logical_name": "pulse-api",
                "digest": DIGEST,
                "source_repository": "us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-api",
                "runtime_ref": f"us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-api@{DIGEST}",
                "mirrors": [{"repository": "ghcr.io/biahflow/pulse/pulse-api", "digest": DIGEST}],
            },
            "frontend": {
                "logical_name": "pulse-web",
                "digest": DIGEST,
                "source_repository": "us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-web",
                "runtime_ref": f"us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-web@{DIGEST}",
                "mirrors": [{"repository": "ghcr.io/biahflow/pulse/pulse-web", "digest": DIGEST}],
            },
        },
    }


def production_payload() -> dict:
    return {
        "schema_version": 1,
        "source_sha": SHA,
        "repository": "biahflow/pulse",
        "release_tag": "v1.2.3",
        "hml": {"workflow_run_id": 123, "workflow_run_attempt": 2},
        "production": {
            "workflow_run_id": 456,
            "workflow_run_attempt": 3,
            "status": "validated",
        },
        "images": {
            "backend": {
                "logical_name": "pulse-api",
                "hml_repository": "us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-api",
                "hml_digest": DIGEST,
                "hml_runtime_ref": f"us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-api@{DIGEST}",
                "production_repository": "us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-api",
                "production_digest": DIGEST,
                "runtime_ref": f"us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-api@{DIGEST}",
            },
            "frontend": {
                "logical_name": "pulse-web",
                "hml_repository": "us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-web",
                "hml_digest": DIGEST,
                "hml_runtime_ref": f"us-east1-docker.pkg.dev/biahflow-hml/hml/pulse-web@{DIGEST}",
                "production_repository": "us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-web",
                "production_digest": DIGEST,
                "runtime_ref": f"us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-web@{DIGEST}",
            },
        },
    }


class HmlEvidenceTests(unittest.TestCase):
    def test_valid_evidence_passes(self) -> None:
        self.assertEqual(release_evidence.validate_hml(hml_payload())["source_sha"], SHA)

    def test_missing_field_fails_closed(self) -> None:
        payload = hml_payload()
        del payload["images"]["backend"]["runtime_ref"]
        with self.assertRaisesRegex(release_evidence.EvidenceError, "keys mismatch"):
            release_evidence.validate_hml(payload)

    def test_invalid_sha_fails_closed(self) -> None:
        payload = hml_payload()
        payload["source_sha"] = "main"
        with self.assertRaisesRegex(release_evidence.EvidenceError, "Git SHA"):
            release_evidence.validate_hml(payload)

    def test_mirror_digest_mismatch_fails_closed(self) -> None:
        payload = hml_payload()
        payload["images"]["backend"]["mirrors"][0]["digest"] = "sha256:" + "c" * 64
        with self.assertRaisesRegex(release_evidence.EvidenceError, "differs from the canonical"):
            release_evidence.validate_hml(payload)

    def test_runtime_digest_mismatch_fails_closed(self) -> None:
        payload = hml_payload()
        payload["images"]["frontend"]["runtime_ref"] = "example.test/image@sha256:" + "c" * 64
        with self.assertRaisesRegex(release_evidence.EvidenceError, "must equal"):
            release_evidence.validate_hml(payload)

    def test_unknown_fields_fail_closed(self) -> None:
        payload = hml_payload()
        payload["unexpected"] = True
        with self.assertRaisesRegex(release_evidence.EvidenceError, "keys mismatch"):
            release_evidence.validate_hml(payload)

    def test_cli_reports_validation_error_without_traceback(self) -> None:
        payload = hml_payload()
        payload["source_sha"] = "main"
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "release_evidence.py"),
                    "validate-hml",
                    "--file",
                    str(evidence),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be a lowercase 40-character Git SHA", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class ProductionEvidenceTests(unittest.TestCase):
    def test_valid_evidence_passes(self) -> None:
        self.assertEqual(
            release_evidence.validate_production(production_payload())["release_tag"], "v1.2.3"
        )

    def test_build_production_carries_hml_and_production_run_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hml_file = Path(directory) / "hml.json"
            hml_file.write_text(json.dumps(hml_payload()), encoding="utf-8")
            args = SimpleNamespace(
                hml_file=hml_file,
                release_tag="v1.2.3",
                run_id=456,
                run_attempt=3,
                backend_repository="us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-api",
                backend_digest=DIGEST,
                backend_runtime_ref=(
                    f"us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-api@{DIGEST}"
                ),
                frontend_repository="us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-web",
                frontend_digest=DIGEST,
                frontend_runtime_ref=(
                    f"us-east1-docker.pkg.dev/biahflow-prod/prod/pulse-web@{DIGEST}"
                ),
            )
            evidence = release_evidence.build_production(args)
        self.assertEqual(evidence["hml"]["workflow_run_attempt"], 2)
        self.assertEqual(evidence["production"]["workflow_run_attempt"], 3)
        self.assertEqual(
            evidence["images"]["backend"]["hml_runtime_ref"],
            hml_payload()["images"]["backend"]["runtime_ref"],
        )

    def test_prerelease_tag_fails_closed(self) -> None:
        payload = production_payload()
        payload["release_tag"] = "v1.2.3-rc.1"
        with self.assertRaisesRegex(release_evidence.EvidenceError, "stable SemVer"):
            release_evidence.validate_production(payload)

    def test_production_digest_mismatch_fails_closed(self) -> None:
        payload = production_payload()
        payload["images"]["backend"]["production_digest"] = "sha256:" + "c" * 64
        with self.assertRaisesRegex(release_evidence.EvidenceError, "HML == PROD"):
            release_evidence.validate_production(payload)

    def test_hml_runtime_reference_mismatch_fails_closed(self) -> None:
        payload = production_payload()
        payload["images"]["backend"]["hml_runtime_ref"] = "example.test/wrong@" + DIGEST
        with self.assertRaisesRegex(release_evidence.EvidenceError, "must equal"):
            release_evidence.validate_production(payload)

    def test_runtime_reference_mismatch_fails_closed(self) -> None:
        payload = production_payload()
        payload["images"]["backend"]["runtime_ref"] = "example.test/wrong@" + DIGEST
        with self.assertRaisesRegex(release_evidence.EvidenceError, "must equal"):
            release_evidence.validate_production(payload)


class WorkflowSafetyTests(unittest.TestCase):
    def test_all_workflows_are_valid_yaml(self) -> None:
        for path in sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml")):
            with self.subTest(path=path.name):
                self.assertIsInstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)

    def test_production_workflow_contains_no_application_build(self) -> None:
        workflow = (
            (REPOSITORY_ROOT / ".github" / "workflows" / "promote-prod.yml")
            .read_text(encoding="utf-8")
            .lower()
        )
        forbidden = (
            "docker build ",
            "docker buildx build",
            "docker/build-push-action",
            "gcloud builds submit",
            "kaniko",
            "pack build",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, workflow)

    def test_hml_publishes_once_then_copies_the_canonical_manifest(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "deploy-hml.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('docker push "$gcp_ref"', workflow)
        self.assertNotIn('docker push "$ghcr_ref"', workflow)
        self.assertIn('--tag "$ghcr_ref" "$gcp_repository@$gcp_digest"', workflow)
        self.assertIn('if [ "$ghcr_digest" != "$gcp_digest" ]; then', workflow)

    def test_runtime_guards_handle_cloud_run_v1_and_v2_resource_shapes(self) -> None:
        for filename in ("deploy-hml.yml", "promote-prod.yml"):
            workflow = (REPOSITORY_ROOT / ".github" / "workflows" / filename).read_text(
                encoding="utf-8"
            )
            with self.subTest(filename=filename):
                self.assertNotIn("value(spec.template.template.containers[0].image)", workflow)
                self.assertIn(".template.template.containers[0].image", workflow)
                self.assertIn(".spec.template.spec.template.spec.containers[0].image", workflow)
                self.assertIn(".template.containers[0].image", workflow)
                self.assertIn(".spec.template.spec.containers[0].image", workflow)

    def test_production_workflow_has_release_guards(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "promote-prod.yml").read_text(
            encoding="utf-8"
        )
        required = (
            "github.ref_protected",
            "merge-base --is-ancestor",
            "validate-hml",
            "--prefer-index=false",
            "validate-production",
            "environment: production",
            "actions/download-artifact@v4",
            "actions/upload-artifact@v4",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, workflow)


if __name__ == "__main__":
    unittest.main()
