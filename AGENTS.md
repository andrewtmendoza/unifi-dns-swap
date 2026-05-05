# AGENTS

## Repo Shape
- This repo is a single-file CLI app. The only code entrypoint is `main.py`; there is no `src/` package yet.
- The project metadata lives in `pyproject.toml`, and `uv.lock` tracks the local package name. If you rename the project in `pyproject.toml`, run `uv lock` to refresh `uv.lock`.

## Commands
- Install/update dependencies with `uv sync`.
- Install local git hooks with `uv run pre-commit install`.
- Main CLI usage:
  - `uv run python main.py status`
  - `uv run python main.py set adguard`
  - `uv run python main.py set quad9`
  - `uv run python main.py set cloudflare`
  - `uv run python main.py set google`
- Focused verification used in this repo:
  - `uv run pre-commit run --all-files`
  - `uv run python -m py_compile main.py`
  - `uv run python main.py --help`
  - `uv run python main.py status --help`

## Environment
- The CLI calls `load_dotenv()` at import time, so a local `.env` file is loaded automatically.
- Keep secrets out of git: `.env` is ignored; `.env.template` is the tracked template.
- Current expected variables are `UNIFI_HOST`, `UNIFI_USERNAME`, `UNIFI_PASSWORD`, with optional `UNIFI_SITE`, `UNIFI_NETWORK`, and `ADGUARD_DNS_SERVERS`.

## Behavior To Preserve
- The tool only manages LAN/DHCP DNS. It does not touch WAN DNS.
- The default target is UniFi site `default` and network `Default` unless overridden by CLI options or env vars.
- `set adguard` requires `ADGUARD_DNS_SERVERS` to be configured; the public resolvers stay hardcoded in `main.py`.
- HTTPS verification is currently hardcoded off with `verify=False` because self-signed UniFi certs are expected. Do not document or implement secure-cert behavior unless you also change the code path.
- The update flow is: login -> fetch network config -> modify `dhcpd_dns_*` fields on the full network object -> PUT updated network -> GET again to verify.
- `verify=False` is intentionally suppressed for Bandit with `# nosec B501`; keep that suppression targeted to the request call instead of disabling the rule globally.

## Editing Notes
- If you change provider presets, update `PUBLIC_DNS_PROVIDERS` or the AdGuard env handling in `main.py`, plus the supported-provider list in `README.md` and `.env.template`.
- If you change CLI command names or options, update `README.md` examples in the same edit.
- Ruff replaces the usual Python style/import/modernization stack here; Bandit handles security checks. Do not add overlapping lint tools unless there is a concrete gap.
- CI mirrors the local pre-commit/compile/help checks in `.github/workflows/ci.yml`; keep those in sync.
- There is currently no test suite or task runner in the repo. Prefer small changes plus the focused verification commands above.

## Maintainer Git Setup
- Maintainer commits for this repo should use the GitHub no-reply email and SSH signing with `~/.ssh/id_ed25519.pub`, otherwise GitHub may reject the push for email privacy or mark commits as unverified.
- The intended repo-local git settings are: `user.email=andrewtmendoza@users.noreply.github.com`, `gpg.format=ssh`, `user.signingkey=$HOME/.ssh/id_ed25519.pub`, and `commit.gpgsign=true`.
