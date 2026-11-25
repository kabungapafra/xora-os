# Security

XORA is a privacy-focused OS, so security reports matter a lot.

**Please don't open a public issue for a vulnerability.** Use GitHub's private reporting instead:
the repository's **Security** tab › **Report a vulnerability**. You'll get an answer within 7 days.

Especially welcome:

- traffic leaking outside Tor while Anon mode is on, or outside the VPN while the VPN kill switch is on (DNS, IPv6, WebRTC, apps that bypass the system resolver)
- Fabric pairing or permission bypasses (a device doing more than it was allowed)
- anything that lets an app or a LAN neighbour change the system, read secrets, or feed fake updates

## Current status, honestly

Anon mode and the kill switches have been tested against the real kernel firewall, but they have **not**
been independently audited. Don't rely on XORA where your safety depends on it until they are.

Images are built on GitHub and signed with Sigstore (keyless). Verify one with:

```bash
cosign verify ghcr.io/<owner>/xora-os:latest \
  --certificate-identity-regexp 'https://github.com/<owner>/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```
