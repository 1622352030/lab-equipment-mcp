import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.devices.maynuo.m8811 import (
    M8811,
    M8811_PROFILE,
    parse_identity,
    parse_vcm,
)


class FakeBackend:
    resource_name = "ASRL7::INSTR"

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.responses = {
            "OUTP?": "0",
            "MODE?": "FIX",
            "VOLT?": "5.0000",
            "CURR?": "0.10000",
            "VOLT:PROT?": "30.0000",
            "MEAS:VCM?": "4.9999, 0.09999, 0.0001",
            "MEAS:VOLT?": "4.9999",
            "MEAS:CURR?": "0.09999",
            "MEAS:DVM?": "0.0001",
            "MEAS:AHRD?": "0.12500",
            "MEAS:DRM?": "12.50",
            "LIST:AREA?": "1",
            "LIST:COUN?": "20",
            "LIST:MODE?": "CONT",
            "LIST:VOLT? 1": "5.0000",
            "LIST:CURR? 1": "0.10000",
            "LIST:WIDT? 1": "2000",
        }

    def query(self, command: str) -> str:
        normalized = M8811._canonical_path(command.upper().rstrip("?"))
        suffix = "?" if "?" in command else ""
        parameters = command.split(None, 1)[1].upper() if " " in command else ""
        key = normalized + suffix + (f" {parameters}" if parameters else "")
        return self.responses[key]

    def write(self, command: str) -> None:
        self.writes.append(command)
        upper = command.upper()
        if upper.startswith("OUTP "):
            self.responses["OUTP?"] = "1" if upper.endswith((" 1", " ON")) else "0"
        if upper.startswith("VOLT "):
            self.responses["VOLT?"] = upper.split(None, 1)[1]
        if upper.startswith("CURR "):
            self.responses["CURR?"] = upper.split(None, 1)[1]
        if upper.startswith("VOLT:PROT "):
            self.responses["VOLT:PROT?"] = upper.split(None, 1)[1]
        if upper.startswith("MODE "):
            self.responses["MODE?"] = upper.split(None, 1)[1]


def connected_driver(backend: FakeBackend | None = None) -> M8811:
    backend = backend or FakeBackend()
    driver = M8811(backend)
    driver._resource = backend.resource_name
    driver._identity = parse_identity("MAYNUO,M8811,REDACTED,V2.6")
    driver._connection_type = InterfaceType.TTL_SERIAL
    return driver


def test_profile_declares_three_electrically_distinct_serial_paths() -> None:
    assert [item.interface_type for item in M8811_PROFILE.interfaces] == [
        InterfaceType.TTL_SERIAL,
        InterfaceType.RS232,
        InterfaceType.RS485,
    ]
    for interface in M8811_PROFILE.interfaces:
        assert interface.session.baud_rate == 9600
        assert interface.session.data_bits == 8
        assert interface.session.stop_bits == 1
        assert interface.session.parity == "none"
        assert interface.session.write_termination == "\n"


def test_identity_and_vcm_parsing_redact_serial() -> None:
    identity = parse_identity("MAYNUO,M8811,PRIVATE-SERIAL,V2.6")
    assert identity.redacted() == "MAYNUO,M8811,<redacted>,V2.6"
    assert parse_vcm("5.0000, 0.10000, 1.2500") == {
        "voltage_v": 5.0,
        "current_a": 0.1,
        "dvm_voltage_v": 1.25,
    }


@pytest.mark.parametrize("response", ["OTHER,M8811,SERIAL,V2.6", "MAYNUO,M8800,SERIAL,V2.6"])
def test_identity_rejects_other_devices(response: str) -> None:
    with pytest.raises(ScopeError, match="not a Maynuo M8811"):
        parse_identity(response)


def test_connect_requires_explicit_serial_resource_and_redacts_identity() -> None:
    class Backend:
        resource_name = None

        def connect(self, resource, timeout_ms, session, identity_command="*IDN?"):
            self.resource_name = resource
            self.args = resource, timeout_ms, session, identity_command
            return "MAYNUO,M8811,PRIVATE-SERIAL,V2.6"

        def disconnect(self):
            self.resource_name = None

    backend = Backend()
    driver = M8811(backend)
    assert driver.connect("ASRL7::INSTR") == "MAYNUO,M8811,<redacted>,V2.6"
    assert backend.args[2].flow_control == "none"
    with pytest.raises(ScopeError, match="VISA serial resource"):
        M8811(backend).connect("USB0::1::INSTR")


def test_rs485_connect_uses_addressed_identity_query() -> None:
    class Backend:
        resource_name = None

        def connect(self, resource, timeout_ms, session, identity_command="*IDN?"):
            self.resource_name = resource
            self.identity_command = identity_command
            return "MAYNUO,M8811,REDACTED,V2.6"

        def disconnect(self):
            pass

    backend = Backend()
    M8811(backend).connect("ASRL7::INSTR", connection="rs485", address=13)
    assert backend.identity_command == "$013*IDN?"


def test_non_ttl_auto_discovery_requires_explicit_resource() -> None:
    with pytest.raises(ScopeError, match="Automatic discovery is limited"):
        M8811(FakeBackend()).connect(connection="rs485", address=13)


def test_ttl_auto_discovery_uses_unique_ch340_resource(monkeypatch) -> None:
    class Backend:
        resource_name = None

        def connect(self, resource, timeout_ms, session, identity_command="*IDN?"):
            self.resource_name = resource
            self.resource = resource
            return "MAYNUO,M8811,REDACTED,V2.6"

        def disconnect(self):
            pass

    monkeypatch.setattr(
        "lab_equipment_mcp.devices.maynuo.m8811.discover_ch340_resources",
        lambda: ["ASRL7::INSTR"],
    )
    backend = Backend()
    M8811(backend).connect()
    assert backend.resource == "ASRL7::INSTR"


def test_measure_and_settings_parse_values() -> None:
    driver = connected_driver()
    assert driver.measure() == {
        "voltage_v": 4.9999,
        "current_a": 0.09999,
        "dvm_voltage_v": 0.0001,
    }
    settings = driver.get_settings()
    assert settings["output_enabled"] is False
    assert settings["rated_limits"] == {"voltage_v": 30.0, "current_a": 5.0, "power_w": 150.0}


@pytest.mark.parametrize("value", [-0.1, 30.0001, float("inf"), float("nan")])
def test_voltage_bounds(value: float) -> None:
    with pytest.raises(ValueError, match="voltage_v must be between 0 and 30"):
        connected_driver().set_voltage(value)


@pytest.mark.parametrize("value", [-0.1, 5.0001, float("inf"), float("nan")])
def test_current_bounds(value: float) -> None:
    with pytest.raises(ValueError, match="current_a must be between 0 and 5"):
        connected_driver().set_current(value)


def test_settings_require_output_off_and_verify_readback() -> None:
    backend = FakeBackend()
    assert connected_driver(backend).set_voltage(12.5) == 12.5
    assert backend.writes[-1] == "VOLT 12.5"
    backend.responses["OUTP?"] = "1"
    with pytest.raises(ValueError, match="output must be disabled"):
        connected_driver(backend).set_current(1.0)


def test_output_enable_requires_confirmation_and_is_read_back() -> None:
    driver = connected_driver()
    with pytest.raises(ValueError, match="confirm_enable=true"):
        driver.set_output(True)
    assert driver.set_output(True, confirm_enable=True) is True
    assert driver.set_output(False) is False


def test_drm_requires_confirmation() -> None:
    driver = connected_driver()
    with pytest.raises(ValueError, match="confirm_drm=true"):
        driver.set_mode("DRM0")
    assert driver.set_mode("DRM0", confirm_drm=True) == "DRM0"


def test_list_bounds_and_readback() -> None:
    driver = connected_driver()
    assert driver.configure_list(area=1, count=20, mode="continuous") == {
        "area": 1,
        "count": 20,
        "mode": "CONT",
    }
    assert driver.set_list_step(1, voltage_v=5, current_a=0.1, width_ms=2000) == {
        "step": 1,
        "voltage_v": 5.0,
        "current_a": 0.1,
        "width_ms": 2000.0,
    }
    with pytest.raises(ValueError, match="step must be between 1 and 200"):
        driver.set_list_step(201, voltage_v=1)


def test_raw_scpi_accepts_documented_long_forms_and_blocks_unsafe_writes() -> None:
    driver = connected_driver()
    assert driver.query("MEASure:VCM?") == "4.9999, 0.09999, 0.0001"
    assert driver.query("*IDN?") == "MAYNUO,M8811,<redacted>,V2.6"
    with pytest.raises(ValueError, match="not documented"):
        driver.query("DISPLAY?")
    with pytest.raises(ValueError, match="serial is redacted"):
        driver.query("*IDN?;SYST:ERR?")
    with pytest.raises(ValueError, match="guarded typed"):
        driver.write("OUTP 1")
    with pytest.raises(ValueError, match="does not accept queries"):
        driver.write("VOLT?")
    with pytest.raises(ValueError, match="Compound writes"):
        driver.write("VOLT 5;CURR 0.1")
    with pytest.raises(ValueError, match="30 V nameplate"):
        driver.write("VOLT MAX")
    with pytest.raises(ValueError, match="typed M8811 LIST"):
        driver.write("LIST:VOLT 1,31")
