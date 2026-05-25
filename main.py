from __future__ import annotations

import os
from typing import Any

import requests
import typer
import urllib3
from dotenv import load_dotenv

PUBLIC_DNS_PROVIDERS = {
    "quad9": ["9.9.9.9", "149.112.112.112"],
    "cloudflare": ["1.1.1.1", "1.0.0.1"],
    "google": ["8.8.8.8", "8.8.4.4"],
}
DIRECT_PUBLIC_DNS_PROVIDER_NAMES = tuple(PUBLIC_DNS_PROVIDERS)
PROVIDER_NAMES = ("gateway", "custom", *PUBLIC_DNS_PROVIDERS)
UPSTREAM_PROVIDER_NAMES = ("custom", *PUBLIC_DNS_PROVIDERS)

DEFAULT_SITE = "default"
DEFAULT_NETWORK = "Default"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_GATEWAY_DNS_SERVER = "192.168.1.1"

load_dotenv()

app = typer.Typer(
    add_completion=False,
    help="Set the client-facing LAN/DHCP DNS provider for a UniFi network.",
)
upstream_app = typer.Typer(help="Manage UniFi WAN/Internet upstream DNS.")
app.add_typer(upstream_app, name="upstream")


class UnifiDnsError(Exception):
    pass


def parse_dns_servers(value: str, env_name: str) -> list[str]:
    dns_servers = [item.strip() for item in value.split(",") if item.strip()]
    if dns_servers:
        return dns_servers
    raise UnifiDnsError(
        f"Environment variable {env_name} must contain one or more "
        "comma-separated DNS servers"
    )


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise UnifiDnsError(f"Missing required environment variable: {name}")


def get_custom_dns_servers(required: bool) -> list[str] | None:
    value = os.getenv("CUSTOM_DNS_SERVERS", "").strip()
    if not value:
        if required:
            raise UnifiDnsError(
                "Missing required environment variable: CUSTOM_DNS_SERVERS"
            )
        return None
    return parse_dns_servers(value, "CUSTOM_DNS_SERVERS")


def get_custom_upstream_dns_servers(required: bool) -> list[str] | None:
    value = os.getenv("CUSTOM_UPSTREAM_DNS_SERVERS", "").strip()
    if not value:
        if required:
            raise UnifiDnsError(
                "Missing required environment variable: CUSTOM_UPSTREAM_DNS_SERVERS"
            )
        return None
    return parse_dns_servers(value, "CUSTOM_UPSTREAM_DNS_SERVERS")


def get_gateway_dns_servers() -> list[str]:
    value = os.getenv("GATEWAY_DNS_SERVER", DEFAULT_GATEWAY_DNS_SERVER).strip()
    return parse_dns_servers(value, "GATEWAY_DNS_SERVER")


def get_dns_providers() -> dict[str, list[str]]:
    providers = {"gateway": get_gateway_dns_servers()}
    custom_dns = get_custom_dns_servers(required=False)
    if custom_dns is not None:
        providers["custom"] = custom_dns
    providers.update(PUBLIC_DNS_PROVIDERS)
    return providers


def get_provider_dns(provider: str) -> list[str]:
    if provider == "gateway":
        return get_gateway_dns_servers()
    if provider == "custom":
        custom_dns = get_custom_dns_servers(required=True)
        if custom_dns is None:
            raise UnifiDnsError(
                "Missing required environment variable: CUSTOM_DNS_SERVERS"
            )
        return custom_dns
    return PUBLIC_DNS_PROVIDERS[provider]


def get_upstream_provider_dns(provider: str) -> list[str]:
    if provider == "custom":
        custom_dns = get_custom_upstream_dns_servers(required=True)
        if custom_dns is None:
            raise UnifiDnsError(
                "Missing required environment variable: CUSTOM_UPSTREAM_DNS_SERVERS"
            )
        return custom_dns
    return PUBLIC_DNS_PROVIDERS[provider]


def is_direct_public_dns_provider(provider: str) -> bool:
    return provider in DIRECT_PUBLIC_DNS_PROVIDER_NAMES


def build_base_url(host: str) -> str:
    host = host.rstrip("/")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"https://{host}"


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = session.request(
        method,
        url,
        json=payload,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        verify=False,
    )
    csrf_token = response.headers.get("X-CSRF-Token") or response.headers.get(
        "X-Updated-Csrf-Token"
    )
    if csrf_token:
        session.headers["X-CSRF-Token"] = csrf_token

    try:
        data = response.json()
    except ValueError as exc:
        raise UnifiDnsError(
            f"{method} {url} returned non-JSON response: {response.text}"
        ) from exc

    if not response.ok:
        raise UnifiDnsError(
            f"{method} {url} failed with HTTP {response.status_code}: {data}"
        )

    return data


def login(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
) -> None:
    payload = {"username": username, "password": password, "rememberMe": False}
    request_json(session, "POST", f"{base_url}/api/auth/login", payload=payload)


def get_networks(
    session: requests.Session,
    base_url: str,
    site: str,
) -> list[dict[str, Any]]:
    response = request_json(
        session,
        "GET",
        f"{base_url}/proxy/network/api/s/{site}/rest/networkconf",
    )
    networks = response.get("data")
    if not isinstance(networks, list):
        raise UnifiDnsError("UniFi API returned an unexpected network list payload")
    return networks


def find_network(networks: list[dict[str, Any]], network_name: str) -> dict[str, Any]:
    for network in networks:
        if network.get("name") == network_name:
            return network
    raise UnifiDnsError(f"Could not find network named {network_name!r}")


def current_dns_from_network(network: dict[str, Any]) -> list[str]:
    dns_servers = []
    for index in range(1, 5):
        value = str(network.get(f"dhcpd_dns_{index}", "")).strip()
        if value:
            dns_servers.append(value)
    return dns_servers


def provider_name_for_dns(dns_servers: list[str]) -> str:
    for provider, configured_dns in get_dns_providers().items():
        if dns_servers == configured_dns:
            return provider
    return "custom"


def get_wan_configs(
    session: requests.Session,
    base_url: str,
    site: str,
) -> list[dict[str, Any]]:
    return [
        network
        for network in get_networks(session, base_url, site)
        if network.get("purpose") == "wan"
    ]


def find_target_wan(
    wan_configs: list[dict[str, Any]],
    wan_name: str | None,
) -> dict[str, Any]:
    if wan_name is not None:
        for wan_config in wan_configs:
            if wan_config.get("name") == wan_name:
                return wan_config
        available_names = (
            ", ".join(
                sorted(
                    str(wan.get("name", "")) for wan in wan_configs if wan.get("name")
                )
            )
            or "none"
        )
        raise UnifiDnsError(
            f"Could not find WAN network named {wan_name!r}. Available WAN networks: "
            f"{available_names}"
        )

    if len(wan_configs) == 1:
        return wan_configs[0]

    available_names = (
        ", ".join(
            sorted(str(wan.get("name", "")) for wan in wan_configs if wan.get("name"))
        )
        or "none"
    )
    raise UnifiDnsError(
        "Multiple WAN networks found: "
        f"{available_names}. Rerun with --wan NAME to choose the target."
    )


def current_upstream_dns_from_wan_config(wan_config: dict[str, Any]) -> list[str]:
    dns_servers = []
    for key in ("wan_dns1", "wan_dns2"):
        value = str(wan_config.get(key, "")).strip()
        if value:
            dns_servers.append(value)
    return dns_servers


def upstream_provider_name_for_dns(dns_servers: list[str]) -> str:
    providers = dict(PUBLIC_DNS_PROVIDERS)
    custom_dns = get_custom_upstream_dns_servers(required=False)
    if custom_dns is not None:
        providers["custom"] = custom_dns

    for provider, configured_dns in providers.items():
        if dns_servers == configured_dns:
            return provider
    return "custom"


def build_updated_network(
    network: dict[str, Any],
    dns_servers: list[str],
) -> dict[str, Any]:
    if len(dns_servers) > 4:
        raise UnifiDnsError("UniFi supports at most 4 DHCP DNS servers")

    payload = dict(network)
    payload["dhcpd_dns_enabled"] = True

    for index in range(1, 5):
        payload[f"dhcpd_dns_{index}"] = ""

    for index, dns_server in enumerate(dns_servers, start=1):
        payload[f"dhcpd_dns_{index}"] = dns_server

    return payload


def build_updated_wan_config(
    wan_config: dict[str, Any],
    dns_servers: list[str],
) -> dict[str, Any]:
    if len(dns_servers) > 2:
        raise UnifiDnsError("UniFi supports at most 2 upstream DNS servers per WAN")

    payload = dict(wan_config)
    payload["wan_dns_preference"] = "manual"
    payload["wan_dns1"] = ""
    payload["wan_dns2"] = ""

    for index, dns_server in enumerate(dns_servers, start=1):
        payload[f"wan_dns{index}"] = dns_server

    return payload


def update_network(
    session: requests.Session,
    base_url: str,
    site: str,
    network_id: str,
    payload: dict[str, Any],
) -> None:
    request_json(
        session,
        "PUT",
        f"{base_url}/proxy/network/api/s/{site}/rest/networkconf/{network_id}",
        payload=payload,
    )


def get_network(
    session: requests.Session,
    base_url: str,
    site: str,
    network_id: str,
) -> dict[str, Any]:
    response = request_json(
        session,
        "GET",
        f"{base_url}/proxy/network/api/s/{site}/rest/networkconf/{network_id}",
    )
    networks = response.get("data")
    if not isinstance(networks, list) or len(networks) != 1:
        raise UnifiDnsError("UniFi API returned an unexpected network payload")
    return networks[0]


def get_wan_config(
    session: requests.Session,
    base_url: str,
    site: str,
    wan_id: str,
) -> dict[str, Any]:
    wan_config = get_network(session, base_url, site, wan_id)
    if wan_config.get("purpose") != "wan":
        raise UnifiDnsError(f"Network object {wan_id!r} is not a WAN configuration")
    return wan_config


def get_session_config() -> tuple[str, str, str]:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    host = build_base_url(get_required_env("UNIFI_HOST"))
    username = get_required_env("UNIFI_USERNAME")
    password = get_required_env("UNIFI_PASSWORD")
    return host, username, password


def get_target_network(
    session: requests.Session,
    host: str,
    site: str,
    network_name: str,
) -> dict[str, Any]:
    network = find_network(get_networks(session, host, site), network_name)
    network_id = str(network.get("_id", "")).strip()
    if not network_id:
        raise UnifiDnsError(f"Network {network_name!r} is missing an _id")
    return network


def show_status(site: str, network_name: str) -> int:
    host, username, password = get_session_config()

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    try:
        login(session, host, username, password)
        network = get_target_network(session, host, site, network_name)
        current_dns = current_dns_from_network(network)
        provider_name = provider_name_for_dns(current_dns)

        typer.echo(f"Network: {network_name}")
        typer.echo(f"DHCP DNS enabled: {network.get('dhcpd_dns_enabled') is True}")
        typer.echo(f"Current DHCP DNS: {', '.join(current_dns) or 'not set'}")
        typer.echo(f"Detected provider: {provider_name}")
        return 0
    except (requests.RequestException, UnifiDnsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1
    finally:
        session.close()


def apply_provider(provider: str, site: str, network_name: str) -> int:
    host, username, password = get_session_config()
    requested_dns = get_provider_dns(provider)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    try:
        login(session, host, username, password)
        network = get_target_network(session, host, site, network_name)
        network_id = str(network["_id"])

        current_dns = current_dns_from_network(network)
        typer.echo(f"Network: {network_name}")
        typer.echo(f"Current DHCP DNS: {', '.join(current_dns) or 'not set'}")
        typer.echo(f"Requested provider: {provider} ({', '.join(requested_dns)})")

        if current_dns == requested_dns and network.get("dhcpd_dns_enabled") is True:
            typer.echo("No changes needed.")
            return 0

        update_network(
            session,
            host,
            site,
            network_id,
            build_updated_network(network, requested_dns),
        )

        verified_network = get_network(session, host, site, network_id)
        verified_dns = current_dns_from_network(verified_network)
        typer.echo(f"Verified DHCP DNS: {', '.join(verified_dns) or 'not set'}")

        if verified_dns != requested_dns:
            raise UnifiDnsError(
                "Verification failed: the read-back DNS values do not match "
                "the requested provider"
            )

        typer.echo("DNS updated successfully.")
        return 0
    except (requests.RequestException, UnifiDnsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1
    finally:
        session.close()


def show_upstream_status(site: str, wan_name: str | None) -> int:
    host, username, password = get_session_config()

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    try:
        login(session, host, username, password)
        wan_config = find_target_wan(get_wan_configs(session, host, site), wan_name)
        current_dns = current_upstream_dns_from_wan_config(wan_config)
        provider_name = upstream_provider_name_for_dns(current_dns)

        typer.echo(f"WAN: {wan_config.get('name')}")
        typer.echo(
            f"Current upstream DNS: {', '.join(current_dns) or 'automatic/not set'}"
        )
        typer.echo(
            "Upstream DNS preference: "
            f"{wan_config.get('wan_dns_preference', 'unknown')}"
        )
        typer.echo(f"Detected provider: {provider_name}")
        return 0
    except (requests.RequestException, UnifiDnsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1
    finally:
        session.close()


def apply_upstream_provider(provider: str, site: str, wan_name: str | None) -> int:
    host, username, password = get_session_config()
    requested_dns = get_upstream_provider_dns(provider)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    try:
        login(session, host, username, password)
        wan_config = find_target_wan(get_wan_configs(session, host, site), wan_name)
        wan_id = str(wan_config.get("_id", "")).strip()
        if not wan_id:
            raise UnifiDnsError(f"WAN {wan_config.get('name')!r} is missing an _id")

        current_dns = current_upstream_dns_from_wan_config(wan_config)
        typer.echo(f"WAN: {wan_config.get('name')}")
        typer.echo(
            f"Current upstream DNS: {', '.join(current_dns) or 'automatic/not set'}"
        )
        typer.echo(f"Requested provider: {provider} ({', '.join(requested_dns)})")

        if (
            current_dns == requested_dns
            and wan_config.get("wan_dns_preference") == "manual"
        ):
            typer.echo("No changes needed.")
            return 0

        update_network(
            session,
            host,
            site,
            wan_id,
            build_updated_wan_config(wan_config, requested_dns),
        )

        verified_wan_config = get_wan_config(session, host, site, wan_id)
        verified_dns = current_upstream_dns_from_wan_config(verified_wan_config)
        typer.echo(
            f"Verified upstream DNS: {', '.join(verified_dns) or 'automatic/not set'}"
        )

        if verified_dns != requested_dns:
            raise UnifiDnsError(
                "Verification failed: the read-back upstream DNS values do not "
                "match the requested provider"
            )

        typer.echo("Upstream DNS updated successfully.")
        return 0
    except (requests.RequestException, UnifiDnsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        return 1
    finally:
        session.close()


@app.command(
    "set",
    context_settings={"allow_extra_args": False, "ignore_unknown_options": False},
)
def set_provider(
    provider: str = typer.Argument(
        ...,
        metavar="PROVIDER",
        help=(
            "LAN/DHCP DNS provider preset. "
            "Recommended: gateway, custom. "
            f"Other presets: {', '.join(sorted(PUBLIC_DNS_PROVIDERS))}."
        ),
        case_sensitive=False,
    ),
    site: str = typer.Option(
        os.getenv("UNIFI_SITE", DEFAULT_SITE),
        "--site",
        help="UniFi site name.",
    ),
    network: str = typer.Option(
        os.getenv("UNIFI_NETWORK", DEFAULT_NETWORK),
        "--network",
        help="LAN network name.",
    ),
    allow_local_dns_breakage: bool = typer.Option(
        False,
        "--allow-local-dns-breakage",
        help=(
            "Allow handing a public DNS provider directly to clients. "
            "This bypasses local LAN DNS such as *.localdomain."
        ),
    ),
) -> None:
    provider = provider.lower()
    if provider not in PROVIDER_NAMES:
        valid_providers = ", ".join(sorted(PROVIDER_NAMES))
        typer.echo(
            f"Error: unknown provider {provider!r}. Choose one of: {valid_providers}",
            err=True,
        )
        raise typer.Exit(code=1)

    if is_direct_public_dns_provider(provider) and not allow_local_dns_breakage:
        typer.echo(
            "Error: direct public DNS providers bypass local LAN DNS. "
            "Use 'gateway' or 'custom' for normal LAN DNS, or rerun with "
            "--allow-local-dns-breakage if you intentionally want clients to "
            f"use {provider} directly.",
            err=True,
        )
        raise typer.Exit(code=1)

    if is_direct_public_dns_provider(provider):
        typer.echo(
            "Warning: this will hand public DNS directly to clients and may "
            "break local LAN DNS such as *.localdomain.",
            err=True,
        )

    exit_code = apply_provider(provider, site, network)
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command()
def status(
    site: str = typer.Option(
        os.getenv("UNIFI_SITE", DEFAULT_SITE),
        "--site",
        help="UniFi site name.",
    ),
    network: str = typer.Option(
        os.getenv("UNIFI_NETWORK", DEFAULT_NETWORK),
        "--network",
        help="LAN network name.",
    ),
) -> None:
    exit_code = show_status(site, network)
    if exit_code:
        raise typer.Exit(code=exit_code)


@upstream_app.command("status")
def upstream_status(
    site: str = typer.Option(
        os.getenv("UNIFI_SITE", DEFAULT_SITE),
        "--site",
        help="UniFi site name.",
    ),
    wan: str | None = typer.Option(
        None,
        "--wan",
        help="WAN network name, such as 'Internet 1'.",
    ),
) -> None:
    exit_code = show_upstream_status(site, wan)
    if exit_code:
        raise typer.Exit(code=exit_code)


@upstream_app.command(
    "set",
    context_settings={"allow_extra_args": False, "ignore_unknown_options": False},
)
def set_upstream_provider(
    provider: str = typer.Argument(
        ...,
        metavar="PROVIDER",
        help=(
            "WAN/Internet upstream DNS provider preset. "
            f"Choose one of: {', '.join(sorted(UPSTREAM_PROVIDER_NAMES))}."
        ),
        case_sensitive=False,
    ),
    site: str = typer.Option(
        os.getenv("UNIFI_SITE", DEFAULT_SITE),
        "--site",
        help="UniFi site name.",
    ),
    wan: str | None = typer.Option(
        None,
        "--wan",
        help="WAN network name, such as 'Internet 1'.",
    ),
) -> None:
    provider = provider.lower()
    if provider not in UPSTREAM_PROVIDER_NAMES:
        valid_providers = ", ".join(sorted(UPSTREAM_PROVIDER_NAMES))
        typer.echo(
            f"Error: unknown upstream provider {provider!r}. Choose one of: "
            f"{valid_providers}",
            err=True,
        )
        raise typer.Exit(code=1)

    exit_code = apply_upstream_provider(provider, site, wan)
    if exit_code:
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
