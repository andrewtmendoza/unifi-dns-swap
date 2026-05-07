# UniFi DNS Swap

Set the LAN/DHCP DNS servers for a UniFi network.

This tool updates UniFi LAN/DHCP DNS settings through the UniFi Network API.

## Why This Exists

I use AdGuard Home in my homelab, but sometimes that server needs maintenance. This script gives me a quick way to switch my UniFi LAN/DHCP DNS settings from my local AdGuard Home instance to a cloud-hosted resolver like Cloudflare, Google, or Quad9.

When maintenance is complete and AdGuard Home is back online, I can switch the network back to my local DNS with one command.

Supported provider presets:

- `adguard`: configured by `ADGUARD_DNS_SERVERS` in `.env`
- `quad9`: `9.9.9.9`, `149.112.112.112`
- `cloudflare`: `1.1.1.1`, `1.0.0.1`
- `google`: `8.8.8.8`, `8.8.4.4`

## Requirements

- Python `>=3.11`
- `uv`
- A reachable UniFi gateway/controller
- A local UniFi admin account that can edit network settings

## Setup

Install dependencies:

```bash
uv sync
```

Install the git hooks:

```bash
uv run pre-commit install
```

Create a local environment file from the template:

```bash
cp .env.template .env
```

Fill in the required values in `.env`:

```bash
UNIFI_HOST=https://192.168.1.1
UNIFI_USERNAME=your-local-admin
UNIFI_PASSWORD=your-password
ADGUARD_DNS_SERVERS=192.168.1.216
```

Optional overrides:

```bash
UNIFI_SITE=default
UNIFI_NETWORK=Default
```

The script automatically loads `.env` on startup.

Use a dedicated local UniFi admin account for this script instead of a personal account.

## Usage

Run the script with the provider you want to apply:

```bash
uv run python main.py set adguard
uv run python main.py set quad9
uv run python main.py set cloudflare
uv run python main.py set google
```

Check the current DHCP DNS without changing anything:

```bash
uv run python main.py status
```

By default the script:

- targets site `default`
- targets network `Default`
- uses insecure HTTPS because UniFi gateways commonly use self-signed certificates

You can override the site or network at runtime:

```bash
uv run python main.py set quad9 --site default --network Default
uv run python main.py status --site default --network Default
```

## Notes

- This updates LAN/DHCP DNS only. It does not modify WAN DNS.
- The script reads the current network config first, updates the DHCP DNS fields, then reads the network back to verify the change.
- Existing clients may continue using the old DNS servers until they renew their DHCP lease.
- `.env` is ignored by git; use `.env.template` as the tracked example.
- `status` can only identify the current provider as `adguard` when `ADGUARD_DNS_SERVERS` is set.
- The current implementation disables TLS certificate verification with `verify=False`. Only run it against a UniFi host and network you trust.
- This project uses the UniFi Network `/proxy/network/api/s/{site}/rest/networkconf` endpoint, which is not a stable public API and may require changes across UniFi releases.

## Development

Install dependencies and hooks:

```bash
uv sync
uv run pre-commit install
```

Run the local verification suite:

```bash
uv run pre-commit run --all-files
uv run python -m py_compile main.py
uv run python main.py --help
uv run python main.py status --help
```
- Run all local lint/security checks with `uv run pre-commit run --all-files`.
