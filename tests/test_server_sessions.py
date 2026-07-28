import pytest

from lab_equipment_mcp import server


def test_supported_devices_use_independent_backends() -> None:
    assert server.dpo2012b.backend is server.dpo2012b_backend
    assert server.afg2125.backend is server.afg2125_backend
    assert server.agilent33500b.backend is server.agilent33500b_backend
    assert server.sdg1062x.backend is server.sdg1062x_backend
    assert server.m8811.backend is server.m8811_backend
    assert server.dpo2012b_backend is not server.afg2125_backend
    assert server.discovery_backend is not server.dpo2012b_backend
    assert server.discovery_backend is not server.afg2125_backend
    assert server.agilent33500b_backend is not server.dpo2012b_backend
    assert server.agilent33500b_backend is not server.afg2125_backend
    assert server.discovery_backend is not server.agilent33500b_backend
    assert server.sdg1062x_backend is not server.discovery_backend
    assert server.sdg1062x_backend is not server.agilent33500b_backend
    assert server.m8811_backend is not server.discovery_backend


def test_disconnect_all_closes_each_backend(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        server.dpo2012b_backend, "disconnect", lambda: calls.append("dpo")
    )
    monkeypatch.setattr(
        server.afg2125_backend, "disconnect", lambda: calls.append("afg")
    )
    monkeypatch.setattr(
        server.agilent33500b_backend, "disconnect", lambda: calls.append("agilent")
    )
    monkeypatch.setattr(
        server.sdg1062x_backend, "disconnect", lambda: calls.append("siglent")
    )
    monkeypatch.setattr(
        server.discovery_backend, "disconnect", lambda: calls.append("discovery")
    )
    monkeypatch.setattr(server.m8811, "disconnect", lambda: calls.append("m8811"))
    assert server.disconnect_instrument() == "Disconnected all instruments"
    assert calls == ["dpo", "afg", "agilent", "siglent", "m8811", "discovery"]


def test_identify_requires_device_prefix_when_both_connected(monkeypatch) -> None:
    monkeypatch.setattr(server.dpo2012b_backend, "_resource_name", "USB0::scope::INSTR")
    monkeypatch.setattr(server.afg2125_backend, "_resource_name", "ASRL5::INSTR")
    with pytest.raises(ValueError, match="Multiple instruments"):
        server.identify_instrument()


def test_generic_identify_redacts_m8811_serial(monkeypatch) -> None:
    monkeypatch.setattr(server.m8811_backend, "_resource_name", "ASRL7::INSTR")
    monkeypatch.setattr(
        server.m8811,
        "identity",
        lambda: {
            "manufacturer": "MAYNUO",
            "model": "M8811",
            "serial": "redacted",
            "firmware": "V2.6",
            "resource": "ASRL7::INSTR",
            "connection_type": "ttl-serial",
        },
    )
    result = server.identify_instrument()
    assert result["identity"] == "MAYNUO,M8811,<redacted>,V2.6"
