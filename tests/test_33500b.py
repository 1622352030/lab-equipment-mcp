import pytest

from lab_equipment_mcp.core.errors import ScopeError, UnsafeCommandError
from lab_equipment_mcp.core.interfaces import InterfaceType, detect_interface_type
from lab_equipment_mcp.core.transports.visa import VisaResource
from lab_equipment_mcp.devices.agilent.series_33500b import (
    AGILENT_33500B_PROFILE,
    Agilent33500B,
    parse_identity,
)


class FakeBackend:
    def __init__(self) -> None:
        self.resource_name = None
        self.interface_type = None
        self.writes: list[str] = []
        self.connected_session = None
        self.responses = {
            "*IDN?": "Agilent Technologies,33509B,SERIAL,2.09",
            "*OPT?": '"0,0,0,0,0"',
            "SYSTem:VERSion?": "1994.0",
            "OUTPut1?": "0",
            "SOURce1:FUNCtion?": "SIN",
            "SOURce1:FREQuency?": "1000",
            "SOURce1:VOLTage?": "0.1",
            "SOURce1:VOLTage:UNIT?": "VPP",
            "SOURce1:VOLTage:OFFSet?": "0",
            "OUTPut1:LOAD?": "50",
            "SOURce1:PHASe?": "0",
            "OUTPut1:POLarity?": "NORM",
            "OUTPut:SYNC?": "1",
            "OUTPut1:SYNC:MODE?": "NORM",
            "OUTPut1:SYNC:POLarity?": "NORM",
            "SOURce1:SWEep:STATe?": "0",
            "SOURce1:BURSt:STATe?": "0",
            "SOURce1:AM:STATe?": "0",
            "SOURce1:FM:STATe?": "0",
            "SOURce1:PM:STATe?": "0",
            "SOURce1:PWM:STATe?": "0",
            "SOURce1:FSKey:STATe?": "0",
            "SOURce1:BPSK:STATe?": "0",
            "SOURce1:SUM:STATe?": "0",
            "SOURce1:FUNCtion:PULSe:PERiod?": "0.001",
            "SOURce1:FUNCtion:PULSe:WIDTh?": "0.0005",
        }

    def list_resources(self, **kwargs):
        return [
            VisaResource(
                "USB0::0x0957::0x2507::SERIAL::INSTR",
                "USB0",
                InterfaceType.USBTMC,
                idn="Agilent Technologies,33509B,SERIAL,2.09",
            )
        ]

    def connect(self, resource, timeout_ms, session):
        self.resource_name = resource
        self.interface_type = detect_interface_type(resource)
        self.connected_session = session
        return "Agilent Technologies,33509B,SERIAL,2.09-1.19-2.00-52-00"

    def disconnect(self):
        self.resource_name = None

    def query(self, command):
        return self.responses[command]

    def write(self, command):
        self.writes.append(command)
        parts = command.split(maxsplit=1)
        if len(parts) != 2:
            return
        header, value = parts
        query = header + "?"
        token = value.strip()
        if header == "OUTPut1":
            self.responses["OUTPut1?"] = "1" if token.upper() == "ON" else "0"
        elif header.endswith(":STATe"):
            self.responses[query] = "1" if token.upper() == "ON" else "0"
        elif token.upper() == "INFINITY":
            self.responses[query] = "9.9E37"
        elif token.upper() in {"ON", "OFF"}:
            self.responses[query] = "1" if token.upper() == "ON" else "0"
        else:
            aliases = {
                "SINUSOID": "SIN",
                "SQUARE": "SQU",
                "NORMAL": "NORM",
                "INVERTED": "INV",
                "INTERNAL": "INT",
                "EXTERNAL": "EXT",
                "LINEAR": "LIN",
                "LOGARITHMIC": "LOG",
                "IMMEDIATE": "IMM",
                "TRIGGERED": "TRIG",
                "GATED": "GAT",
                "CARRIER": "CARR",
                "MARKER": "MARK",
            }
            normalized = token.upper()
            self.responses[query] = aliases.get(normalized, token)


@pytest.fixture
def connected():
    backend = FakeBackend()
    driver = Agilent33500B(backend)
    driver.connect("USB0::0x0957::0x2507::SERIAL::INSTR")
    return driver, backend


def test_profile_reserves_usb_lan_socket_vxi11_and_gpib() -> None:
    assert AGILENT_33500B_PROFILE.interface_types == {
        InterfaceType.USBTMC,
        InterfaceType.LAN_VXI11,
        InterfaceType.LAN_SOCKET,
        InterfaceType.GPIB,
    }
    socket = AGILENT_33500B_PROFILE.interface_for_resource(
        "TCPIP0::192.168.1.10::5025::SOCKET"
    )
    assert socket is not None
    assert socket.session.write_termination == "\n"


def test_identity_accepts_agilent_and_keysight() -> None:
    assert parse_identity("Agilent Technologies,33509B,SERIAL,2.09").model == "33509B"
    assert parse_identity("Keysight Technologies,33522B,SERIAL,5.00").model == "33522B"


def test_identity_rejects_wrong_model() -> None:
    with pytest.raises(ScopeError, match="Unsupported"):
        parse_identity("Agilent Technologies,33220A,SERIAL,1.00")


def test_connect_reads_options_and_capabilities(connected) -> None:
    driver, _ = connected
    capabilities = driver.capabilities()
    assert capabilities["model"] == "33509B"
    assert capabilities["channel_count"] == 1
    assert capabilities["bandwidth_hz"] == 20_000_000
    assert capabilities["arbitrary_waveforms"] is False


def test_explicit_lan_socket_connect_uses_socket_session() -> None:
    backend = FakeBackend()
    driver = Agilent33500B(backend)
    driver.connect("TCPIP0::192.168.1.50::5025::SOCKET")
    assert backend.interface_type is InterfaceType.LAN_SOCKET
    assert backend.connected_session.read_termination == "\n"
    assert backend.connected_session.write_termination == "\n"


def test_unlicensed_33509b_rejects_arb(connected) -> None:
    driver, _ = connected
    with pytest.raises(ValueError, match="arbitrary-waveform"):
        driver.set_waveform("ARB")


def test_waveform_requires_output_disabled(connected) -> None:
    driver, backend = connected
    backend.responses["OUTPut1?"] = "1"
    with pytest.raises(ValueError, match="output is enabled"):
        driver.set_waveform("sine", 1000)


def test_output_enable_requires_confirmation(connected) -> None:
    driver, backend = connected
    with pytest.raises(ValueError, match="confirm_enable"):
        driver.set_output(True)
    assert driver.set_output(True, confirm_enable=True) is True
    assert "OUTPut1 ON" in backend.writes


def test_waveform_and_detail_use_readback(connected) -> None:
    driver, backend = connected
    result = driver.set_waveform("square", 2000, 1.0, 0.0)
    detail = driver.set_waveform_detail(square_duty_percent=20, polarity="inverted")
    assert result["function"] == "SQU"
    assert result["frequency_hz"] == 2000
    assert detail["square_duty_percent"] == 20
    assert detail["polarity"] == "INV"
    assert "SOURce1:VOLTage:UNIT VPP" in backend.writes


def test_pulse_manual_limits_are_validated(connected) -> None:
    driver, backend = connected
    original_writes = list(backend.writes)
    with pytest.raises(ValueError, match="16 ns"):
        driver.configure_pulse(width_s=10e-9)
    with pytest.raises(ValueError, match="8.4 ns"):
        driver.configure_pulse(leading_s=2e-9)
    assert backend.writes == original_writes


def test_modulation_disables_other_modes_before_enable(connected) -> None:
    driver, backend = connected
    result = driver.configure_modulation(
        "FM", internal_frequency_hz=100, amount=1000, enabled=True
    )
    assert result["enabled"] is True
    assert backend.writes.index("SOURce1:AM:STATe OFF") < backend.writes.index(
        "SOURce1:FM:STATe ON"
    )


def test_sweep_and_burst_are_configurable(connected) -> None:
    driver, _ = connected
    sweep = driver.configure_sweep(1000, 5000, 0.1, marker_frequency_hz=3000)
    assert sweep["enabled"] is True
    burst = driver.configure_burst(cycles=5, period_s=0.01)
    assert burst["enabled"] is True


def test_modulation_ranges_are_validated_before_writes(connected) -> None:
    driver, backend = connected
    original_writes = list(backend.writes)
    with pytest.raises(ValueError, match="AM amount"):
        driver.configure_modulation("AM", amount=121)
    with pytest.raises(ValueError, match="FM deviation"):
        driver.configure_modulation("FM", amount=2000)
    with pytest.raises(ValueError, match="PWM requires"):
        driver.configure_modulation("PWM", amount=1e-5)
    assert backend.writes == original_writes


def test_sweep_and_burst_relationships_are_validated(connected) -> None:
    driver, backend = connected
    original_writes = list(backend.writes)
    with pytest.raises(ValueError, match="marker_frequency"):
        driver.configure_sweep(1000, 5000, marker_frequency_hz=6000)
    with pytest.raises(ValueError, match="cycles/frequency"):
        driver.configure_burst(cycles=5, period_s=0.001)
    assert backend.writes == original_writes


def test_raw_output_apply_and_destructive_commands_are_blocked(connected) -> None:
    driver, _ = connected
    with pytest.raises(ValueError, match="Raw APPLy"):
        driver.write("APPL:SIN 1000,1")
    with pytest.raises(ValueError, match="Raw APPLy"):
        driver.write("OUTP ON")
    with pytest.raises(ValueError, match="Raw APPLy"):
        driver.write("OUTP1:STATE ON")
    with pytest.raises(UnsafeCommandError):
        driver.write("SYST:SEC:IMM")


def test_query_only_accepts_queries(connected) -> None:
    driver, _ = connected
    assert driver.query("*IDN?") == "Agilent Technologies,33509B,SERIAL,2.09"
    with pytest.raises(ValueError, match="must be a query"):
        driver.query("FREQ 1000")
