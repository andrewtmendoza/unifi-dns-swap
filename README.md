# UniFi DNS Swap

Set the client-facing LAN/DHCP DNS servers or WAN/upstream DNS servers for a UniFi network.

This tool updates UniFi LAN/DHCP DNS settings and WAN/upstream DNS settings through the UniFi Network API.

## Why This Exists

I use local DNS in my homelab, but sometimes that resolver needs maintenance. This script gives me a quick way to switch my UniFi LAN/DHCP DNS settings between the UniFi gateway and a custom resolver such as AdGuard Home or Pi-hole.

Public DNS providers like Cloudflare, Google, and Quad9 usually belong upstream of your local resolver in most homelab setups, not as the direct DNS servers handed to clients.

Supported provider presets:

- Recommended LAN/DHCP providers:
- `gateway`: configured by `GATEWAY_DNS_SERVER` in `.env`, defaults to `192.168.1.1`
- `custom`: configured by `CUSTOM_DNS_SERVERS` in `.env`

- Direct public DNS providers, explicit opt-in required:
- `quad9`: `9.9.9.9`, `149.112.112.112`
- `cloudflare`: `1.1.1.1`, `1.0.0.1`
- `google`: `8.8.8.8`, `8.8.4.4`

For WAN/upstream DNS, use the `upstream` command instead of handing public resolvers directly to clients.

## Requirements

- Python `>=3.11`
- `uv`
- A reachable UniFi gateway/controller
- A local UniFi user with Network -> Site Admin privileges

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
GATEWAY_DNS_SERVER=192.168.1.1
CUSTOM_DNS_SERVERS=192.168.1.216
CUSTOM_UPSTREAM_DNS_SERVERS=9.9.9.9,149.112.112.112
```

Optional overrides:

```bash
UNIFI_SITE=default
UNIFI_NETWORK=Default
```

The script automatically loads `.env` on startup.

Use a dedicated local UniFi user with Network -> Site Admin privileges for this script instead of a personal account.

## Usage

Client-facing LAN/DHCP DNS:

Run the script with the provider you want to apply:

```bash
uv run python main.py set gateway
uv run python main.py set custom
```

If you intentionally want to hand a public resolver directly to clients, you must opt in explicitly:

```bash
uv run python main.py set quad9 --allow-local-dns-breakage
uv run python main.py set cloudflare --allow-local-dns-breakage
uv run python main.py set google --allow-local-dns-breakage
```

Check the current DHCP DNS without changing anything:

```bash
uv run python main.py status
```

Gateway upstream DNS:

```bash
uv run python main.py upstream status --wan "Internet 1"
uv run python main.py upstream set quad9 --wan "Internet 1"
uv run python main.py upstream set cloudflare --wan "Internet 1"
uv run python main.py upstream set google --wan "Internet 1"
uv run python main.py upstream set custom --wan "Internet 1"
```

By default the script:

- targets site `default`
- targets network `Default`
- uses insecure HTTPS because UniFi gateways commonly use self-signed certificates
- defaults `gateway` DNS to `192.168.1.1` unless `GATEWAY_DNS_SERVER` is set

You can override the site or network at runtime:

```bash
uv run python main.py set quad9 --site default --network Default
uv run python main.py status --site default --network Default
```

For upstream commands, override the site and optionally select the WAN by name:

```bash
uv run python main.py upstream status --site default --wan "Internet 1"
uv run python main.py upstream set custom --site default --wan "Internet 1"
```

## Notes

- `set` updates client-facing LAN/DHCP DNS only. It does not modify WAN DNS.
- `upstream` updates WAN/Internet upstream DNS only. It does not modify LAN/DHCP DNS fields.
- For normal homelab usage, point clients at `gateway` or `custom` so local LAN DNS records such as `*.localdomain` keep working.
- Public DNS providers like Cloudflare, Google, and Quad9 are usually better configured upstream on your gateway or local resolver instead of being handed directly to clients.
- If you directly hand a public DNS provider to clients, local LAN DNS records may stop resolving unless that public resolver can see your private DNS zone.
- The LAN command reads the current network config first, updates the `dhcpd_dns_*` fields, then reads the network back to verify the change.
- The upstream command reads the current WAN `networkconf` object first, updates only `wan_dns_preference`, `wan_dns1`, and `wan_dns2`, then reads the WAN object back to verify the change.
- Some UniFi gateways expose multiple WAN objects, such as `Internet 1` and `Internet 2`, even when only one is actively used. In that case, rerun `upstream` commands with `--wan NAME` to choose the target explicitly.
- Existing clients may continue using the old DNS servers until they renew their DHCP lease.
- `.env` is ignored by git; use `.env.template` as the tracked example.
- `status` can only identify the current provider as `custom` when `CUSTOM_DNS_SERVERS` is set.
- `upstream status` can only identify the current provider as `custom` when `CUSTOM_UPSTREAM_DNS_SERVERS` is set.
- The current implementation disables TLS certificate verification with `verify=False`. Only run it against a UniFi host and network you trust.
- This project uses the UniFi Network `/proxy/network/api/s/{site}/rest/networkconf` endpoint for both LAN and upstream DNS, which is not a stable public API and may require changes across UniFi releases.

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
uv run python main.py set --help
uv run python main.py status --help
uv run python main.py upstream --help
uv run python main.py upstream status --help
uv run python main.py upstream set --help
```
- Run all local lint/security checks with `uv run pre-commit run --all-files`.
