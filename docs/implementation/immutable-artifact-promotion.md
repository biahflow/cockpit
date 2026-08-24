# Immutable Artifact Promotion — Implementation Contract

## Objective

Implement the Pulse release invariant defined by ADR 0042:

```text
build once on main
→ resolve immutable image digests
→ deploy those digests to HML
→ validate HML
→ release tag from homologated main SHA
→ promote the same digests
→ deploy the same digests to PROD
```

Production must not rebuild application source.

## Implemented topology

`.github/workflows/deploy-hml.yml` is the sole application build path. For every eligible SHA on
`main`, it builds each application image at most once, publishes the result to Artifact Registry
and GHCR, resolves the immutable manifest digest, and checks the OCI source-revision label. If a
rerun finds only one copy, it copies that manifest to the missing registry without rebuilding.

HML migration, services and scheduler are all updated with digest-pinned references. The workflow
then verifies the image reported by every runtime resource and writes a versioned evidence file.
Its artifact name includes the source SHA, workflow run and attempt, so a rerun cannot overwrite or
silently replace another candidate.

`.github/workflows/promote-prod.yml` accepts only stable `vX.Y.Z` tags. It requires a protected tag
whose target is reachable from `main`, identifies exactly one successful HML run for that SHA,
downloads the evidence artifact and validates its archive digest and contents. Production copies
the HML manifests to the configured Artifact Registry with `docker buildx imagetools create`; the
workflow contains no application build step.

After migration, service and scheduler updates, the production workflow verifies every runtime
digest, writes production evidence containing both HML and PROD references, validates that the two
digests are identical for each logical image, and uploads the result.

## Evidence schema

The schema is implemented and tested by `.github/scripts/release_evidence.py` and
`.github/scripts/test_release_evidence.py`.

HML evidence contains:

- schema version, source repository and full source SHA;
- HML workflow run ID and attempt;
- logical image name (`backend` or `frontend`), immutable digest and source repository;
- the digest-pinned runtime reference and every registry mirror verified at that digest.

Production evidence adds the authorized stable release tag and records HML and PROD repositories,
runtime references and digests side by side. Unknown fields, mutable references, invalid digests,
unexpected repositories, stale run coordinates or divergent HML/PROD digests fail validation.

The evidence artifacts use the repository retention configured by GitHub. Changing that retention
is an administrative decision; the workflow does not invent a shorter policy.

## Safety

- No `docker build` or equivalent application build in the PROD promotion path.
- Tag target must be reachable from `main`.
- Release must fail closed when digest evidence is missing, ambiguous or does not match HML validation.
- Artifact retention must preserve release candidates and rollback candidates according to repository policy.
- Rollback reuses a known-good digest; it does not rebuild source.

## Configuration boundary

The `production` GitHub environment must define these variables:

- `PROD_GCP_PROJECT_ID`
- `PROD_GCP_REGION`
- `PROD_GCP_REGISTRY`
- `PROD_GCP_WIF_PROVIDER`
- `PROD_GCP_SERVICE_ACCOUNT`
- `PROD_API_SERVICE`
- `PROD_WEB_SERVICE`
- `PROD_MIGRATION_JOB`
- `PROD_SCHEDULER_WORKER_POOL`
- `PROD_INTEGRATION_CHECK_JOB`

The workflow validates all values before authentication and fails closed if any value is missing or
malformed. Environment protection rules and a protected `v*` tag rule are external GitHub
configuration and remain human gates.

The configured production identity must be able to read the HML source manifests, write the PROD
repository, update/execute the named Cloud Run jobs, update the services and worker pool, and read
those resources back for runtime verification. The WIF provider must restrict trust to this
repository and the authorized release-tag path. These IAM bindings remain infrastructure
configuration; they are not created by the application workflow.

## Evidence

The implementation should make it possible to prove:

```text
source SHA X
HML backend  = digest A
PROD backend = digest A
HML frontend = digest B
PROD frontend = digest B
```

## References

- `docs/adr/0042-trunk-based-main-hml-tag-producao.md`
- `.github/workflows/deploy-hml.yml`
- `.github/workflows/promote-prod.yml`
- `.github/scripts/release_evidence.py`
- `biahflow/engineeringOS/workflows/trunk-based-delivery.md`
