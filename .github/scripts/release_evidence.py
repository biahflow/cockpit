#!/usr/bin/env python3
"""Serialize and validate immutable HML/production release evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[a-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9._/-]+$")
RELEASE_TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
LOGICAL_IMAGES = {"backend": "pulse-api", "frontend": "pulse-web"}


class EvidenceError(ValueError):
    """Raised when release evidence is incomplete or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _positive_int(value: Any, field: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        f"{field} must be a positive integer",
    )
    return value


def _sha(value: Any, field: str = "source_sha") -> str:
    _require(
        isinstance(value, str) and SHA_RE.fullmatch(value) is not None,
        f"{field} must be a lowercase 40-character Git SHA",
    )
    return value


def _digest(value: Any, field: str) -> str:
    _require(
        isinstance(value, str) and DIGEST_RE.fullmatch(value) is not None,
        f"{field} must be a sha256 digest",
    )
    return value


def _repository(value: Any, field: str) -> str:
    _require(
        isinstance(value, str) and REPOSITORY_RE.fullmatch(value) is not None,
        f"{field} must be a container repository without tag or digest",
    )
    _require(
        "@" not in value and not value.endswith("/"),
        f"{field} must not contain a digest or trailing slash",
    )
    return value


def _runtime_ref(value: Any, repository: str, digest: str, field: str) -> str:
    expected = f"{repository}@{digest}"
    _require(value == expected, f"{field} must equal {expected}")
    return expected


def _exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{field} must be an object")
    actual = set(value)
    _require(
        actual == expected,
        f"{field} keys mismatch: expected {sorted(expected)}, got {sorted(actual)}",
    )
    return value


def validate_hml(payload: Any) -> dict[str, Any]:
    root = _exact_keys(
        payload,
        {"schema_version", "source_sha", "repository", "hml", "images"},
        "evidence",
    )
    _require(root["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    _sha(root["source_sha"])
    _require(
        isinstance(root["repository"], str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", root["repository"]),
        "repository must be owner/name",
    )

    hml = _exact_keys(root["hml"], {"workflow_run_id", "workflow_run_attempt", "status"}, "hml")
    _positive_int(hml["workflow_run_id"], "hml.workflow_run_id")
    _positive_int(hml["workflow_run_attempt"], "hml.workflow_run_attempt")
    _require(hml["status"] == "validated", "hml.status must be validated")

    images = _exact_keys(root["images"], set(LOGICAL_IMAGES), "images")
    for key, logical_name in LOGICAL_IMAGES.items():
        image = _exact_keys(
            images[key],
            {"logical_name", "digest", "source_repository", "runtime_ref", "mirrors"},
            f"images.{key}",
        )
        _require(
            image["logical_name"] == logical_name,
            f"images.{key}.logical_name must be {logical_name}",
        )
        digest = _digest(image["digest"], f"images.{key}.digest")
        source_repository = _repository(
            image["source_repository"], f"images.{key}.source_repository"
        )
        _runtime_ref(image["runtime_ref"], source_repository, digest, f"images.{key}.runtime_ref")
        _require(
            isinstance(image["mirrors"], list) and image["mirrors"],
            f"images.{key}.mirrors must be a non-empty list",
        )
        seen: set[str] = set()
        for index, raw_mirror in enumerate(image["mirrors"]):
            mirror = _exact_keys(
                raw_mirror, {"repository", "digest"}, f"images.{key}.mirrors[{index}]"
            )
            repository = _repository(
                mirror["repository"], f"images.{key}.mirrors[{index}].repository"
            )
            _require(
                repository not in seen,
                f"images.{key}.mirrors contains duplicate repository {repository}",
            )
            seen.add(repository)
            _require(
                _digest(mirror["digest"], f"images.{key}.mirrors[{index}].digest") == digest,
                f"images.{key}.mirrors[{index}] digest differs from the canonical digest",
            )
    return root


def validate_production(payload: Any) -> dict[str, Any]:
    root = _exact_keys(
        payload,
        {
            "schema_version",
            "source_sha",
            "repository",
            "release_tag",
            "hml",
            "production",
            "images",
        },
        "evidence",
    )
    _require(root["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    _sha(root["source_sha"])
    _require(
        isinstance(root["repository"], str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", root["repository"]),
        "repository must be owner/name",
    )
    _require(
        isinstance(root["release_tag"], str) and RELEASE_TAG_RE.fullmatch(root["release_tag"]),
        "release_tag must be stable SemVer vX.Y.Z",
    )

    hml = _exact_keys(root["hml"], {"workflow_run_id", "workflow_run_attempt"}, "hml")
    _positive_int(hml["workflow_run_id"], "hml.workflow_run_id")
    _positive_int(hml["workflow_run_attempt"], "hml.workflow_run_attempt")
    production = _exact_keys(
        root["production"],
        {"workflow_run_id", "workflow_run_attempt", "status"},
        "production",
    )
    _positive_int(production["workflow_run_id"], "production.workflow_run_id")
    _positive_int(production["workflow_run_attempt"], "production.workflow_run_attempt")
    _require(production["status"] == "validated", "production.status must be validated")

    images = _exact_keys(root["images"], set(LOGICAL_IMAGES), "images")
    for key, logical_name in LOGICAL_IMAGES.items():
        image = _exact_keys(
            images[key],
            {
                "logical_name",
                "hml_repository",
                "hml_digest",
                "hml_runtime_ref",
                "production_repository",
                "production_digest",
                "runtime_ref",
            },
            f"images.{key}",
        )
        _require(
            image["logical_name"] == logical_name,
            f"images.{key}.logical_name must be {logical_name}",
        )
        hml_repository = _repository(image["hml_repository"], f"images.{key}.hml_repository")
        hml_digest = _digest(image["hml_digest"], f"images.{key}.hml_digest")
        _runtime_ref(
            image["hml_runtime_ref"],
            hml_repository,
            hml_digest,
            f"images.{key}.hml_runtime_ref",
        )
        production_digest = _digest(image["production_digest"], f"images.{key}.production_digest")
        _require(production_digest == hml_digest, f"images.{key} violates HML == PROD digest")
        repository = _repository(
            image["production_repository"], f"images.{key}.production_repository"
        )
        _runtime_ref(
            image["runtime_ref"],
            repository,
            production_digest,
            f"images.{key}.runtime_ref",
        )
    return root


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON evidence from {path}: {exc}") from exc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_hml(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_sha": args.source_sha,
        "repository": args.repository,
        "hml": {
            "workflow_run_id": args.run_id,
            "workflow_run_attempt": args.run_attempt,
            "status": "validated",
        },
        "images": {
            "backend": {
                "logical_name": "pulse-api",
                "digest": args.backend_digest,
                "source_repository": args.backend_repository,
                "runtime_ref": args.backend_runtime_ref,
                "mirrors": [
                    {
                        "repository": args.backend_mirror_repository,
                        "digest": args.backend_mirror_digest,
                    }
                ],
            },
            "frontend": {
                "logical_name": "pulse-web",
                "digest": args.frontend_digest,
                "source_repository": args.frontend_repository,
                "runtime_ref": args.frontend_runtime_ref,
                "mirrors": [
                    {
                        "repository": args.frontend_mirror_repository,
                        "digest": args.frontend_mirror_digest,
                    }
                ],
            },
        },
    }
    return validate_hml(payload)


def build_production(args: argparse.Namespace) -> dict[str, Any]:
    hml = validate_hml(load_json(args.hml_file))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_sha": hml["source_sha"],
        "repository": hml["repository"],
        "release_tag": args.release_tag,
        "hml": {
            "workflow_run_id": hml["hml"]["workflow_run_id"],
            "workflow_run_attempt": hml["hml"]["workflow_run_attempt"],
        },
        "production": {
            "workflow_run_id": args.run_id,
            "workflow_run_attempt": args.run_attempt,
            "status": "validated",
        },
        "images": {
            "backend": {
                "logical_name": "pulse-api",
                "hml_repository": hml["images"]["backend"]["source_repository"],
                "hml_digest": hml["images"]["backend"]["digest"],
                "hml_runtime_ref": hml["images"]["backend"]["runtime_ref"],
                "production_repository": args.backend_repository,
                "production_digest": args.backend_digest,
                "runtime_ref": args.backend_runtime_ref,
            },
            "frontend": {
                "logical_name": "pulse-web",
                "hml_repository": hml["images"]["frontend"]["source_repository"],
                "hml_digest": hml["images"]["frontend"]["digest"],
                "hml_runtime_ref": hml["images"]["frontend"]["runtime_ref"],
                "production_repository": args.frontend_repository,
                "production_digest": args.frontend_digest,
                "runtime_ref": args.frontend_runtime_ref,
            },
        },
    }
    return validate_production(payload)


def _common_image_arguments(parser: argparse.ArgumentParser, prefix: str) -> None:
    parser.add_argument(f"--{prefix}-repository", required=True)
    parser.add_argument(f"--{prefix}-digest", required=True)
    parser.add_argument(f"--{prefix}-runtime-ref", required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    write_hml = commands.add_parser("write-hml", help="write validated HML evidence")
    write_hml.add_argument("--output", type=Path, required=True)
    write_hml.add_argument("--source-sha", required=True)
    write_hml.add_argument("--repository", required=True)
    write_hml.add_argument("--run-id", type=int, required=True)
    write_hml.add_argument("--run-attempt", type=int, required=True)
    for prefix in ("backend", "frontend"):
        _common_image_arguments(write_hml, prefix)
        write_hml.add_argument(f"--{prefix}-mirror-repository", required=True)
        write_hml.add_argument(f"--{prefix}-mirror-digest", required=True)

    validate_hml_parser = commands.add_parser("validate-hml", help="validate HML evidence")
    validate_hml_parser.add_argument("--file", type=Path, required=True)
    validate_hml_parser.add_argument("--source-sha")
    validate_hml_parser.add_argument("--repository")
    validate_hml_parser.add_argument("--run-id", type=int)
    validate_hml_parser.add_argument("--run-attempt", type=int)

    write_prod = commands.add_parser("write-production", help="write validated production evidence")
    write_prod.add_argument("--output", type=Path, required=True)
    write_prod.add_argument("--hml-file", type=Path, required=True)
    write_prod.add_argument("--release-tag", required=True)
    write_prod.add_argument("--run-id", type=int, required=True)
    write_prod.add_argument("--run-attempt", type=int, required=True)
    for prefix in ("backend", "frontend"):
        _common_image_arguments(write_prod, prefix)

    validate_prod_parser = commands.add_parser(
        "validate-production", help="validate production evidence"
    )
    validate_prod_parser.add_argument("--file", type=Path, required=True)
    return root


def main() -> int:
    argument_parser = parser()
    args = argument_parser.parse_args()
    try:
        if args.command == "write-hml":
            write_json(args.output, build_hml(args))
        elif args.command == "validate-hml":
            payload = validate_hml(load_json(args.file))
            if args.source_sha is not None:
                _require(
                    payload["source_sha"] == args.source_sha,
                    "evidence source_sha does not match requested SHA",
                )
            if args.repository is not None:
                _require(
                    payload["repository"] == args.repository,
                    "evidence repository does not match current repository",
                )
            if args.run_id is not None:
                _require(
                    payload["hml"]["workflow_run_id"] == args.run_id,
                    "evidence run_id does not match selected HML run",
                )
            if args.run_attempt is not None:
                _require(
                    payload["hml"]["workflow_run_attempt"] == args.run_attempt,
                    "evidence run_attempt is stale",
                )
        elif args.command == "write-production":
            write_json(args.output, build_production(args))
        elif args.command == "validate-production":
            validate_production(load_json(args.file))
        else:  # pragma: no cover - argparse enforces the command set
            raise EvidenceError(f"unsupported command {args.command}")
    except EvidenceError as exc:
        argument_parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
