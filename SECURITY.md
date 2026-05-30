# Security Policy

## Supported Versions

The latest released `0.x` version on PyPI receives security fixes. Pre-1.0 the
API may change; pin a version and watch releases.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Report privately via one of:

- GitHub [Security Advisories](https://github.com/dozken/ibkr-trader-core/security/advisories/new) (preferred)
- Email **dosmukhamed@gmail.com** with subject `SECURITY: ibkr-trader-core`

Please include: affected version/commit, reproduction steps, and impact. We aim
to acknowledge within 72 hours and to ship a fix or mitigation before any public
disclosure.

## Scope notes for this project

This is trading software that connects to a brokerage. Take extra care with:

- **Credentials** — IBKR creds and API keys live in `.env` (gitignored). Never
  commit secrets. CI runs `gitleaks` on every push as a backstop.
- **Order routing** — a bug that places, sizes, or cancels orders incorrectly is
  a security-class issue, not just a functional one. Flag it as such.
- **The compliance/audit chain** — the cryptographic audit log
  (`audit_integrity_loop`) is a safety control; report any way to forge or break
  the hash chain privately.

See also [docs/SECURITY.md](docs/SECURITY.md) for in-depth operational guidance.
