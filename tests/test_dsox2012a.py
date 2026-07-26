import base64

import pytest

from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.devices.agilent.dsox2012a import (
    DSOX2012A_PROFILE,
    AgilentDSOX2012A,
    normalize_channel,
    normalize_measurement,
)


class FakeBackend:
    resource_name = "USB0::0x0957::0x1799::SERIAL::INSTR"

    def __init__(self) -> None:
        self.writes = []

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        responses = {
            ":WAVEFORM:PREAMBLE?": "2,0,3,0,0.001,0,0,0.5,0,0",
            ":MEASURE:FREQUENCY?": "1000",
        }
        return responses[command.upper()]

    def query_ascii_values(self, command):
        return [1.0, 3.0, -1.0]

    def query_raw(self, command):
        return b"#210hello\n"

    def write_raw(self, data):
        self.writes.append(data)
        return len(data)


def test_profile_and_normalizers():
    assert DSOX2012A_PROFILE.interface_types == {
        InterfaceType.USBTMC,
        InterfaceType.LAN_VXI11,
        InterfaceType.GPIB,
    }
    assert normalize_channel("channel2") == "CHAN2"
    assert normalize_measurement("frequency") == "FREQuency"
    with pytest.raises(ValueError):
        normalize_channel("CH3")


def test_measurement_and_waveform_scaling():
    scope = AgilentDSOX2012A(FakeBackend())
    assert scope.measure("CH1", "frequency")["value"] == 1000
    result = scope.acquire_waveform("CH1")
    assert result["values"] == [0.5, 1.5, -0.5]
    assert result["times"] == [0.0, 0.001, 0.002]
    assert ":MEASure:SOURce CHAN1" in scope.backend.writes
    assert ":DIGitize CHAN1" in scope.backend.writes


def test_complete_scpi_entrypoint_rejects_query_write_mismatch():
    scope = AgilentDSOX2012A(FakeBackend())
    with pytest.raises(ValueError, match="query=true"):
        scope.command(":CHANnel1:SCALe 1", query=True)
    with pytest.raises(ValueError, match="query=false"):
        scope.command(":CHANnel1:SCALe?", query=False)


def test_binary_queries_and_writes_use_base64_and_ieee_block():
    backend = FakeBackend()
    scope = AgilentDSOX2012A(backend)
    result = scope.query_binary(":DISPlay:DATA? PNG")
    assert result["data"] == base64.b64encode(b"#210hello\n").decode("ascii")
    scope.write_binary(":DISPlay:LABList", base64.b64encode(b"CH1\n").decode("ascii"))
    assert backend.writes[-1].startswith(b":DISPlay:LABList #14")
