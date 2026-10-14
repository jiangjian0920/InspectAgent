from __future__ import annotations

from app.inventory.catalog import AssetCatalog, escape_promql_regex


def test_resolve_by_alias_and_ip(catalog: AssetCatalog):
    by_ip = catalog.resolve("192.168.59.130")
    by_alias = catalog.resolve("app-server-01")
    assert by_ip is not None and by_alias is not None
    assert by_ip.resource_id == by_alias.resource_id == "server-prod-130"


def test_resolve_unknown_returns_none(catalog: AssetCatalog):
    assert catalog.resolve("192.168.59.131") is None


def test_instance_regex_escapes_dots(catalog: AssetCatalog):
    regex = catalog.instance_regex()
    assert "192[.]168[.]59[.]130:9100" in regex
    assert escape_promql_regex("a.b") == "a[.]b"
