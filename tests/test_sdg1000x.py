import re

import pytest

from lab_equipment_mcp.core.errors import ScopeError, UnsafeCommandError
from lab_equipment_mcp.core.interfaces import InterfaceType, detect_interface_type
from lab_equipment_mcp.core.transports.visa import VisaResource
from lab_equipment_mcp.devices.siglent.sdg_1000x import (
    SDG1000X,
    SIGLENT_SDG1000X_PROFILE,
    parse_identity,
    parse_modulation_response,
    parse_parameter_response,
    parse_wvdt_response,
)


class FakeBackend:
    def __init__(self) -> None:
        self.resource_name = None
        self.interface_type = None
        self.connected_session = None
        self.writes: list[str] = []
        self.raw_writes: list[bytes] = []
        self.raw_queries: list[str] = []
        self.responses = {
            "*IDN?": "Siglent Technologies,SDG1062X,SERIAL,1.01.01.30R1",
            "C1:OUTP?": "C1:OUTP OFF,LOAD,HZ,PLRT,NOR",
            "C2:OUTP?": "C2:OUTP OFF,LOAD,HZ,PLRT,NOR",
            "C1:BSWV?": "C1:BSWV WVTP,SINE,FRQ,1000HZ,AMP,2V,OFST,0V,PHSE,0",
            "C2:BSWV?": "C2:BSWV WVTP,SINE,FRQ,1000HZ,AMP,2V,OFST,0V,PHSE,0",
            "C1:MDWV?": "C1:MDWV STATE,OFF",
            "C2:MDWV?": "C2:MDWV STATE,OFF",
            "C1:SWWV?": "C1:SWWV STATE,OFF",
            "C2:SWWV?": "C2:SWWV STATE,OFF",
            "C1:BTWV?": "C1:BTWV STATE,OFF",
            "C2:BTWV?": "C2:BTWV STATE,OFF",
            "C1:ARWV?": "C1:ARWV INDEX,2,NAME,StairUp",
            "C2:ARWV?": "C2:ARWV INDEX,2,NAME,StairUp",
            "C1:SYNC?": "C1:SYNC OFF,TYPE,CH1",
            "C2:SYNC?": "C2:SYNC OFF,TYPE,CH1",
            "WVDT?": (
                b"WVDT POS, /Local, WVNM, lanchk, LENGTH, 8B, TYPE, 6, WAVEDATA,"
                b"\x01\x80\x00\xc0\x00@\xff\x7f\n"
            ),
        }

    def list_resources(self, **kwargs):
        return [
            VisaResource(
                "USB0::0xF4EC::0x1103::REDACTED::INSTR",
                "USB0",
                InterfaceType.USBTMC,
                idn="Siglent Technologies,SDG1062X,REDACTED,1.01.01.30R1",
            )
        ]

    def connect(self, resource, timeout_ms, session):
        self.resource_name = resource
        self.interface_type = detect_interface_type(resource)
        self.connected_session = session
        return self.responses["*IDN?"]

    def disconnect(self):
        self.resource_name = None

    def query(self, command):
        return self.responses[command]

    def query_raw(self, command):
        self.raw_queries.append(command)
        return self.responses["WVDT?"]

    def write_raw(self, data):
        self.raw_writes.append(data)
        return len(data)

    def write(self, command):
        self.writes.append(command)
        channel_match = re.match(r"C([12]):(OUTP|BSWV|MDWV|SWWV|BTWV|ARWV|SYNC)\s+(.+)", command)
        if not channel_match:
            if command.startswith("PACP"):
                self.responses["C2:BSWV?"] = self.responses["C1:BSWV?"].replace(
                    "C1:", "C2:"
                )
            return
        channel, family, payload = channel_match.groups()
        query = f"C{channel}:{family}?"
        if family == "OUTP":
            state_match = re.match(r"(ON|OFF)$", payload)
            if state_match:
                prior = self.responses[query]
                self.responses[query] = re.sub(
                    r"OUTP (ON|OFF)", f"OUTP {state_match.group(1)}", prior
                )
                return
        if family in {"MDWV", "SWWV", "BTWV"}:
            state_match = re.search(r"STATE,(ON|OFF)", payload)
            if state_match:
                self.responses[query] = f"C{channel}:{family} STATE,{state_match.group(1)}"
                return
        if family == "SYNC":
            prior = self.responses[query]
            if payload.startswith("TYPE,"):
                source = payload.split(",", 1)[1]
                self.responses[query] = re.sub(r"TYPE,CH[12]", f"TYPE,{source}", prior)
            elif payload in {"ON", "OFF"}:
                self.responses[query] = re.sub(
                    r"SYNC (ON|OFF)", f"SYNC {payload}", prior
                )
            return
        if family == "ARWV" and payload.startswith("NAME,"):
            payload = f"NAME,{payload.split(',', 1)[1]}.bin"
        params = parse_parameter_response(self.responses[query], family)
        fields = payload.split(",")
        if family == "MDWV" and fields[0] not in {"STATE"}:
            params["TYPE"] = fields.pop(0)
        for index in range(0, len(fields) - 1, 2):
            params[fields[index].upper()] = fields[index + 1]
        if family == "OUTP":
            state = params.pop("STATE", "OFF")
            body = [state]
        elif family == "MDWV" and "TYPE" in params:
            body = [params.pop("TYPE")]
        else:
            body = []
        for key, value in params.items():
            body.extend([key, value])
        self.responses[query] = f"C{channel}:{family} " + ",".join(body)


@pytest.fixture
def connected():
    backend = FakeBackend()
    driver = SDG1000X(backend)
    driver.connect("USB0::0xF4EC::0x1103::REDACTED::INSTR")
    return driver, backend


def test_profile_reserves_usb_lan_vxi11_socket_and_optional_gpib() -> None:
    assert SIGLENT_SDG1000X_PROFILE.interface_types == {
        InterfaceType.USBTMC,
        InterfaceType.LAN_VXI11,
        InterfaceType.LAN_SOCKET,
        InterfaceType.GPIB,
    }
    socket = SIGLENT_SDG1000X_PROFILE.interface_for_resource(
        "TCPIP0::192.168.1.10::5025::SOCKET"
    )
    assert socket is not None
    assert socket.session.write_termination == "\n"


def test_identity_accepts_sdg1062x_and_rejects_other_models() -> None:
    assert parse_identity("Siglent Technologies,SDG1062X,SERIAL,1.0").model == "SDG1062X"
    with pytest.raises(ScopeError, match="Unsupported"):
        parse_identity("Siglent Technologies,SDG2042X,SERIAL,1.0")


def test_parser_accepts_compact_enabled_modulation_response() -> None:
    parsed = parse_modulation_response(
        "C1:MDWVAM,STATE,ON,SRC,INT,FRQ,100HZ,DEPTH,50"
    )
    assert parsed["TYPE"] == "AM"
    assert parsed["STATE"] == "ON"
    assert parsed["DEPTH"] == "50"


def test_parser_accepts_state_then_modulation_type() -> None:
    parsed = parse_modulation_response(
        "C1:MDWV STATE,ON,FSK,SRC,INT,KFRQ,50HZ,HFRQ,5000HZ,CARR,WVTP,SINE"
    )
    assert parsed == {
        "STATE": "ON",
        "TYPE": "FSK",
        "SRC": "INT",
        "KFRQ": "50HZ",
        "HFRQ": "5000HZ",
    }


def test_connect_and_capabilities(connected) -> None:
    driver, _ = connected
    capabilities = driver.capabilities()
    assert capabilities["model"] == "SDG1062X"
    assert capabilities["channel_count"] == 2
    assert capabilities["max_frequency_hz"] == 60_000_000
    assert capabilities["max_arb_points"] == 16_384


def test_output_enable_is_guarded_and_read_back(connected) -> None:
    driver, backend = connected
    with pytest.raises(ValueError, match="confirm_enable"):
        driver.set_output(2, True)
    assert driver.set_output(2, True, confirm_enable=True) is True
    assert "C2:OUTP ON" in backend.writes


def test_dual_channel_waveforms_are_independent_and_read_back(connected) -> None:
    driver, backend = connected
    result = driver.set_waveform(2, "square", 2000, 1.0, 0.0)
    assert result["parameters"]["WVTP"] == "SQUARE"
    assert result["parameters"]["FRQ"] == "2000"
    assert any(command.startswith("C2:BSWV") for command in backend.writes)
    assert not any(command.startswith("C1:BSWV") for command in backend.writes)


def test_output_load_polarity_and_waveform_detail_use_readback(connected) -> None:
    driver, _ = connected
    assert driver.set_output_load(1, 50)["load_ohms"] == 50
    assert driver.set_output_polarity(1, "inverted")["polarity"] == "INVT"
    detail = driver.set_waveform_detail(1, duty_percent=25, phase_degrees=90)
    assert detail["parameters"]["DUTY"] == "25"
    assert detail["parameters"]["PHSE"] == "90"


def test_modulation_sweep_burst_and_sync_are_configurable(connected) -> None:
    driver, backend = connected
    modulation = driver.configure_modulation(1, "AM", amount=50)
    assert modulation["enabled"] is True
    assert backend.writes.index("C1:MDWV STATE,ON") < next(
        index
        for index, command in enumerate(backend.writes)
        if command.startswith("C1:MDWV AM,")
    )
    driver.set_mode_enabled(1, "modulation", False)
    sweep = driver.configure_sweep(1, 1000, 5000, 0.1)
    assert sweep["enabled"] is True
    driver.set_mode_enabled(1, "sweep", False)
    burst = driver.configure_burst(1, cycles=5, period_s=0.01)
    assert burst["enabled"] is True
    assert driver.configure_sync(True, 2)["source_channel"] == 2


def test_keyed_and_dsb_modulation_do_not_claim_unsupported_amount(connected) -> None:
    driver, backend = connected
    for mode in ("ASK", "PSK", "DSBAM"):
        result = driver.configure_modulation(1, mode, amount=123)
        assert result["amount_supported"] is False
    modulation_writes = [command for command in backend.writes if "MDWV ASK," in command]
    assert modulation_writes and "AAMP" not in modulation_writes[-1]
    modulation_writes = [command for command in backend.writes if "MDWV PSK," in command]
    assert modulation_writes and "PHSE" not in modulation_writes[-1]
    modulation_writes = [command for command in backend.writes if "MDWV DSBAM," in command]
    assert modulation_writes and "DEPTH" not in modulation_writes[-1]


def test_copy_channel_requires_disabled_outputs_and_verifies(connected) -> None:
    driver, _ = connected
    result = driver.copy_channel(1, 2)
    assert result["verified_by_readback"] is True
    assert result["target_channel"] == 2


def test_arb_select_and_binary_upload(connected) -> None:
    driver, backend = connected
    selected = driver.select_arbitrary_waveform(1, index=47)
    assert selected["parameters"]["INDEX"] == "47"
    uploaded = driver.upload_arbitrary_waveform(1, "xy_demo", [-1, 0, 1, 0])
    assert uploaded["point_count"] == 4
    assert uploaded["physical_output_verified"] is False
    assert backend.raw_writes[0].startswith(b"C1:WVDT WVNM,xy_demo")


def test_user_arb_accepts_firmware_added_bin_suffix(connected) -> None:
    driver, _ = connected
    selected = driver.select_arbitrary_waveform(1, name="xy_demo")
    assert selected["parameters"]["NAME"] == "xy_demo.bin"


def test_raw_output_copy_and_destructive_commands_are_blocked(connected) -> None:
    driver, _ = connected
    with pytest.raises(ValueError, match="Raw output"):
        driver.write("C1:OUTP ON")
    with pytest.raises(ValueError, match="dual-channel"):
        driver.write("PACP C2,C1")
    with pytest.raises(UnsafeCommandError):
        driver.write("*RST")


def test_query_only_accepts_queries(connected) -> None:
    driver, _ = connected
    assert "SDG1062X" in driver.query("*IDN?")
    with pytest.raises(ValueError, match="must be a query"):
        driver.query("C1:BSWV FRQ,1000")


def test_bare_lan_address_expands_to_vxi11() -> None:
    backend = FakeBackend()
    driver = SDG1000X(backend)
    identity = driver.connect("10.11.9.230")
    assert backend.resource_name == "TCPIP0::10.11.9.230::inst0::INSTR"
    assert backend.interface_type is InterfaceType.LAN_VXI11
    assert "<redacted>" in identity
    assert "SERIAL" not in identity


def test_lan_socket_address_selects_socket_session() -> None:
    backend = FakeBackend()
    driver = SDG1000X(backend)
    driver.connect("10.11.9.230:5025")
    assert backend.resource_name == "TCPIP0::10.11.9.230::5025::SOCKET"
    assert backend.interface_type is InterfaceType.LAN_SOCKET
    assert backend.connected_session is not None
    assert backend.connected_session.read_termination == "\n"
    assert backend.connected_session.write_termination == "\n"


def test_complete_lan_resource_is_used_unchanged() -> None:
    backend = FakeBackend()
    driver = SDG1000X(backend)
    driver.connect("TCPIP0::10.11.9.230::inst0::INSTR")
    assert backend.resource_name == "TCPIP0::10.11.9.230::inst0::INSTR"
    assert backend.interface_type is InterfaceType.LAN_VXI11


def test_identity_redaction_replaces_only_the_serial_field() -> None:
    identity = parse_identity("Siglent Technologies,SDG1062X,PRIVATE-SERIAL,1.01.01.30R1")
    assert identity.redacted() == "Siglent Technologies,SDG1062X,<redacted>,1.01.01.30R1"


def test_wvdt_response_is_split_into_header_and_samples() -> None:
    raw = (
        b"WVDT POS, /Local, WVNM, lanchk, LENGTH, 8B, TYPE, 6, WAVEDATA,"
        b"\x01\x80\x00\xc0\x00@\xff\x7f\n"
    )
    parsed = parse_wvdt_response(raw)
    assert parsed["name"] == "lanchk"
    assert parsed["length_bytes"] == 8
    assert parsed["data_type"] == 6
    assert parsed["sample_count"] == 4
    assert parsed["samples"] == [-32767, -16384, 16384, 32767]


def test_wvdt_response_rejects_malformed_replies() -> None:
    with pytest.raises(ScopeError, match="shorter"):
        parse_wvdt_response(b"WVNM, x, LENGTH, 8B, TYPE, 6, WAVEDATA,\x01\x80")
    with pytest.raises(ScopeError, match="WAVEDATA"):
        parse_wvdt_response(b"WVNM, x, LENGTH, 8B, TYPE, 6")
    with pytest.raises(ScopeError, match="whole number"):
        parse_wvdt_response(b"WVNM, x, LENGTH, 3B, TYPE, 6, WAVEDATA,\x01\x02\x03")


def test_read_arbitrary_waveform_round_trips_the_uploaded_points(connected) -> None:
    driver, backend = connected
    result = driver.read_arbitrary_waveform("lanchk")
    assert backend.raw_queries == ["WVDT? USER,lanchk"]
    assert result["samples"] == [-32767, -16384, 16384, 32767]
    assert result["sample_count"] == 4
    assert result["truncated"] is False


def test_read_arbitrary_waveform_caps_returned_samples(connected) -> None:
    driver, _ = connected
    result = driver.read_arbitrary_waveform("lanchk", max_samples=2)
    assert result["samples"] == [-32767, -16384]
    assert result["sample_count"] == 4
    assert result["truncated"] is True


def test_read_arbitrary_waveform_rejects_unsafe_input(connected) -> None:
    driver, _ = connected
    with pytest.raises(ValueError, match="safe filename"):
        driver.read_arbitrary_waveform("../etc/passwd")
    with pytest.raises(ValueError, match="positive integer"):
        driver.read_arbitrary_waveform("lanchk", max_samples=0)
