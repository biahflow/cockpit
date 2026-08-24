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

## Current baseline

`.github/workflows/deploy-hml.yml` currently builds `cockpit-api` and `cockpit-web` on `push` to `main`, publishes SHA-tagged images, and deploys HML from those tags.

The hardening target is to make digest identity explicit and reusable as release evidence.

## Required implementation

1. HML pipeline builds each application image once per eligible `main` SHA.
2. After push, resolve the immutable registry digest for each image.
3. Persist/emit release evidence mapping:
   - source SHA;
   - image logical name;
   - registry/repository;
   - immutable digest;
   - HML workflow run.
4. Deploy HML using `repository@sha256:<digest>` or equivalent digest-pinned reference.
5. Verify runtime revision corresponds to the expected digest.
6. Production release is triggered by an authorized release tag pointing to a commit reachable from protected `main`.
7. Production workflow retrieves the digest evidence associated with that SHA.
8. If PROD uses a different registry/project, copy/retag the same manifest/blob by digest without executing a new application build.
9. Deploy PROD using the promoted digest-pinned references.
10. Verify runtime digest after deployment.
11. Preserve audit evidence proving HML digest == PROD digest for each application image.

## Safety

- No `docker build` or equivalent application build in the PROD promotion path.
- Tag target must be reachable from `main`.
- Release must fail closed when digest evidence is missing, ambiguous or does not match HML validation.
- Artifact retention must preserve release candidates and rollback candidates according to repository policy.
- Rollback reuses a known-good digest; it does not rebuild source.

## Configuration boundary

Concrete PROD project, registry, service and authorization values belong to environment/repository configuration. Do not hard-code secrets or invent environment identifiers when they are not already defined.

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
- `biahflow/engineeringOS/workflows/trunk-based-delivery.md`
