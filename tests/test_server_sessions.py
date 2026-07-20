import pytest

from lab_equipment_mcp import server


def test_supported_devices_use_independent_backends() -> None:
    assert server.dpo2012b.backend is server.dpo2012b_backend
    assert server.afg2125.backend is server.afg2125_backend
    assert server.dpo2012b_backend is not server.afg2125_backend
    assert server.discovery_backend is not server.dpo2012b_backend
    assert server.discovery_backend is not server.afg2125_backend


def test_disconnect_all_closes_each_backend(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        server.dpo2012b_backend, "disconnect", lambda: calls.append("dpo")
    )
    monkeypatch.setattr(
        server.afg2125_backend, "disconnect", lambda: calls.append("afg")
    )
    monkeypatch.setattr(
        server.discovery_backend, "disconnect", lambda: calls.append("discovery")
    )
    assert server.disconnect_instrument() == "Disconnected all instruments"
    assert calls == ["dpo", "afg", "discovery"]


def test_identify_requires_device_prefix_when_both_connected(monkeypatch) -> None:
    monkeypatch.setattr(server.dpo2012b_backend, "_resource_name", "USB0::scope::INSTR")
    monkeypatch.setattr(server.afg2125_backend, "_resource_name", "ASRL5::INSTR")
    with pytest.raises(ValueError, match="Multiple instruments"):
        server.identify_instrument()
