import pytest

from lab_equipment_mcp.devices.tektronix.dpo2012b import DPO2012B, normalize_channel


class FakeBackend:
    resource_name = "USB0::0x0699::0x039D::SERIAL::INSTR"

    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        responses = {
            "HORIZONTAL:RECORDLENGTH?": "1000",
            "WFMOUTPRE:XINCR?": "0.001",
            "WFMOUTPRE:XZERO?": "0",
            "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YMULT?": "0.5",
            "WFMOUTPRE:YZERO?": "0",
            "WFMOUTPRE:YOFF?": "1",
            "WFMOUTPRE:XUNIT?": '"s"',
            "WFMOUTPRE:YUNIT?": '"V"',
            "MEASUREMENT:IMMED:VALUE?": "1000",
            "MEASUREMENT:IMMED:UNITS?": '"Hz"',
        }
        return responses[command.upper()]

    def query_ascii_values(self, command: str) -> list[float]:
        assert command == "CURVe?"
        return [1.0, 3.0, -1.0]


def test_channel_normalization() -> None:
    assert normalize_channel("channel1") == "CH1"
    assert normalize_channel("ch2") == "CH2"


def test_waveform_scaling() -> None:
    backend = FakeBackend()
    result = DPO2012B(backend).acquire_waveform("CH1", max_points=10)
    assert result["times"] == [0.0, 0.001, 0.002]
    assert result["values"] == [0.0, 1.0, -1.0]
    assert result["point_count"] == 3
    assert result["source_point_count"] == 3
    assert result["downsampled"] is False
    assert "DATa:SOUrce CH1" in backend.writes


def test_long_waveform_is_downsampled_across_the_requested_span() -> None:
    backend = FakeBackend()
    backend.query_ascii_values = lambda command: list(range(1000))
    result = DPO2012B(backend).acquire_waveform("CH1", max_points=10)
    assert result["point_count"] == 10
    assert result["source_point_count"] == 1000
    assert result["downsampled"] is True
    assert result["times"][0] == 0
    assert result["times"][-1] == pytest.approx(0.999)
    assert "DATa:STOP 1000" in backend.writes


def test_measurement() -> None:
    backend = FakeBackend()
    result = DPO2012B(backend).immediate_measurement("CH2", "frequency")
    assert result["value"] == 1000
    assert result["unit"] == "Hz"
    assert result["valid"] is True


def test_query_rejects_mixed_write_and_query_segments() -> None:
    backend = FakeBackend()
    with pytest.raises(ValueError, match="Every SCPI segment"):
        DPO2012B(backend).query("CH1:SCALE 1;*IDN?")
