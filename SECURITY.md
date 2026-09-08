# Security policy

## Supported versions

Security fixes are applied to the latest tagged release. JobFlow 0.3.x is designed for
single-computer, loopback-only self-hosting and is not a hardened public internet service.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting when it is enabled for this repository.
Do not open a public issue containing credentials, resume files, access tokens, or exploit
details. Include the affected version, reproduction steps, impact, and any suggested fix.

## Local deployment boundary

The supplied Compose configuration binds the Web and API ports to `127.0.0.1`. Changing
those bindings to `0.0.0.0`, forwarding them through a router, or placing JobFlow on a
public server is outside the supported security model and requires independent TLS,
authentication hardening, monitoring, backups, and network controls.
