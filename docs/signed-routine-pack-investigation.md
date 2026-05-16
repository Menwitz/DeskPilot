# Signed Routine Pack Investigation

This is a later-release investigation track. DeskPilot does not currently trust
routine packs because of cryptographic signatures. Current pack trust is local
and explicit: `builtin`, `trusted_local`, or `unverified_local`.

## Goals

- Verify pack origin before install or promotion.
- Detect tampering of manifest, routine YAML, task/playbook files, fixtures,
  docs, tests, and proof expectations.
- Keep local execution usable without any network service.
- Avoid implying that a signature makes unsafe automation acceptable.

## Candidate Signing Model

- `routine-pack.yaml` keeps the pack metadata and declares signed file globs.
- A detached signature file, for example `routine-pack.sig`, signs a canonical
  manifest digest.
- A generated `pack-digest.json` records each included file path, size, and
  SHA-256 digest.
- The signature covers `pack-digest.json`; the digest covers pack files.
- Trust roots are local: an operator imports a publisher public key into a local
  keyring before a pack can become `trusted_local`.

## Verification Flow

1. Load `routine-pack.yaml`.
2. Validate the manifest schema and relative paths.
3. Build the local file digest from declared globs.
4. Compare the digest with `pack-digest.json`.
5. Verify `routine-pack.sig` against the operator's local trusted keyring.
6. Run the normal pack conflict detector and pack-level test runner.
7. Keep trust warnings visible when signatures are missing, expired, revoked, or
   produced by an unknown key.

## Open Questions

- Whether to use Sigstore bundle verification, Minisign, age-plugin-sign,
  GPG, or a small Ed25519-only verifier.
- How key rotation and revocation should work without a required online
  service.
- Whether built-in packs should be signed at release build time or only covered
  by repository provenance.
- How to display signed-but-high-risk packs in the operator app without
  collapsing safety review into a binary trusted/untrusted label.

## Non-Goals

- No remote auto-install marketplace in the Windows beta.
- No automatic execution based only on a valid signature.
- No signature bypass for approval manifests, safety gates, allowed windows,
  redaction policy, proof requirements, or conflict detection.
