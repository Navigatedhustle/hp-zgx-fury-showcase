# Security policy

## Supported versions

| Version | Security maintenance |
|---|---|
| v3.1.0 | Current hardened demonstration release |
| v3.0.0 and older | Historical snapshots; upgrade before reuse |

This is demonstration software, provided as is under the repository license. It is not a supported HP product or an internet-facing production service.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/security/advisories/new). The repository has private reporting enabled. Include the release/commit, affected area, expected behavior and a minimal fictional reproduction. Do not include credentials, private hostnames, customer identity, visitor media or unreviewed diagnostics. Do not publish exploit details in a public issue. Use [ordinary issues](https://github.com/Navigatedhustle/hp-zgx-fury-showcase/issues) for nonsensitive bugs.

## Deployment boundary

Application and model HTTP listeners bind to loopback. Use the workstation locally or through your organization's approved SSH/private Tailscale access policy. Those account and network policies are the access boundary. Never expose the demo directly to the public internet, enable public Funnel access, or forward model ports to visitors.

Presenter controls deliberately have no PIN or separate presenter role. Approved network users are trusted demo operators. Exact Host/Origin validation, JSON or CSRF-token mutation protection and browser policies add layers within that boundary; they are not an independent authentication system. A hostile process running as the same OS account is outside the isolation guarantee.

## Untrusted data and generated code

Model responses, uploaded documents, names and fetched public metadata remain untrusted. Ordinary output is escaped or allowlisted; generated interactive HTML uses an opaque origin and network-denying policy with checked message bridges. PDF/Office/logo decoding runs in networkless bounded workers. Model files use immutable revisions and explicit SHA256 checks; no verification marker substitutes for hashing actual bytes.

Agent Factory keeps its networkless namespace sandbox and existing workflow limits. Atlas developer tools explicitly execute generated Python/SQL in a separate PID/network/filesystem namespace plus Landlock/seccomp, against an ephemeral read-only copy of fictional data. Result collection accepts bounded regular artifacts only. These are practical containment layers, not a claim of formally verified protection or suitability for hostile multi-tenant hosting.

Private runtime files use owner permissions; core dumps are disabled for services. The identity-checked controller uses pinned process descriptors for signals. Bounded queues, upload/connection/time limits and log retention protect availability without changing the model serving reservations. Persistent workspace storage is checked before execution and monitored during it; a short polling window can permit a burst above the nominal directory threshold. Private namespace temporary filesystems have a hard size limit.

## Visitor privacy

Only the consented Action Trailer camera flow may collect a real visitor image. It performs local processing, stores media outside the source checkout and deletes it on Done, New visitor, explicit deletion, idle expiry and service startup. Visitor media, appearance descriptions and session credentials must never be added to Git, release files, screenshots or bug reports. Other uploads use fictional/public demonstration material. Check real camera, microphone, speaker and remote-client behavior at your site.

## Scope and limitations

The verified platform is the documented Ubuntu ARM64 GB300 profile. Windows/macOS build-tool advisories do not establish a vulnerability in that supported installation path; they are not a claim that those upstream packages are universally patched. The NVIDIA SBSA wheel metadata warning is disclosed separately from native/GPU validation. Dependencies, model licenses, residual assumptions and verification scope are recorded in the release documentation and SBOMs. Human review of generated content remains necessary.
