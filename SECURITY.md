# Security policy

This repository is pre-release and does not yet publish supported security
branches. Do not report suspected vulnerabilities in public issues. After the
GitHub repository is created, use its private vulnerability-reporting channel;
until then, contact the maintainers privately.

Renderer wheels are executable application dependencies. Static discovery does
not import them, but explicit enablement of a Python renderer runs code with the
host Streamlit process's authority. The PRIMS validation boundary constrains
browser output; it does not sandbox Python.

Reports should include the affected commit or wheel version, reproduction,
impact, and whether untrusted graph data alone can trigger the behavior.

Every push and pull request is scanned for committed credentials across Git
history. If a credential is found, revoke and rotate it before removing it from
the repository; rewriting the current file does not invalidate a leaked secret.
Security reports and scheduled compatibility reports must not include graph
payloads, tenant identifiers, environment dumps, tokens, or private URLs.

Hosted activation requirements for private reporting, protected release
environments, and trusted publishing are listed in
`docs/release-activation.md`.
