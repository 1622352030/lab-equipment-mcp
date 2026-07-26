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

    def query_raw(self, command: str) -> bytes:
        assert command == "CURVe?"
        return b"#14\x01\x02\xFE\xFF\n"


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


def test_binary_waveform_scaling() -> None:
    backend = FakeBackend()
    result = DPO2012B(backend).acquire_waveform("CH1", max_points=10, encoding="RIBINARY", width=1)
    assert result["encoding"] == "RIBINARY"
    assert result["values"] == pytest.approx([0.0, 0.5, -1.5, -1.0])


def test_programming_guide_measurement_aliases_are_supported() -> None:
    backend = FakeBackend()
    result = DPO2012B(backend).immediate_measurement("CH1", "PK2PK")
    assert result["measurement"] == "PK2Pk"


def test_binary_query_returns_base64() -> None:
    import base64

    class BinaryBackend(FakeBackend):
        def query_raw(self, command: str) -> bytes:
            assert command == "WFMOutpre?"
            return b"#15hello\n"

    backend = BinaryBackend()
    result = DPO2012B(backend).query_binary("WFMOutpre?")
    assert result["encoding"] == "base64"
    assert base64.b64decode(result["data"]).startswith(b"#")


def test_complete_scpi_entrypoint_rejects_query_write_mismatch() -> None:
    scope = DPO2012B(FakeBackend())
    with pytest.raises(ValueError, match="query=true"):
        scope.command("CH1:SCAle 1", query=True)
    with pytest.raises(ValueError, match="query=false"):
        scope.command("CH1:SCAle?", query=False)


def test_complete_scpi_entrypoint_writes_and_queries() -> None:
    backend = FakeBackend()
    scope = DPO2012B(backend)
    assert scope.command("MEASUrement:IMMed:VALue?", query=True) == "1000"
    assert scope.command("CH1:SCAle 1", query=False) == "Command sent"
    assert backend.writes[-1] == "CH1:SCAle 1"


def test_screenshot_sets_and_restores_format() -> None:
    import base64

    class ScreenshotBackend(FakeBackend):
        def query(self, command: str) -> str:
            if command == "SAVe:IMAGe:FILEFormat?":
                return "BMP"
            return super().query(command)

        def query_raw(self, command: str) -> bytes:
            assert command == "HARDCopy START"
            return b"#17PNGDATA\n"

    backend = ScreenshotBackend()
    result = DPO2012B(backend).capture_screenshot("PNG")
    assert result["format"] == "PNG"
    assert result["byte_count"] == 7
    assert base64.b64decode(result["data"]) == b"PNGDATA"
    assert backend.writes == [
        "SAVe:IMAGe:FILEFormat PNG",
        "SAVe:IMAGe:FILEFormat BMP",
    ]


@pytest.mark.parametrize(
    ("image_format", "payload"),
    [
        ("PNG", b"\x89PNG\r\n\x1a\nDATA"),
        ("BMP", b"BMDATA"),
        ("TIFF", b"MM\x00*DATA"),
    ],
)
def test_screenshot_accepts_raw_image_returned_by_real_firmware(
    image_format: str, payload: bytes
) -> None:
    import base64

    class ScreenshotBackend(FakeBackend):
        def query(self, command: str) -> str:
            if command == "SAVe:IMAGe:FILEFormat?":
                return "PNG"
            return super().query(command)

        def query_raw(self, command: str) -> bytes:
            assert command == "HARDCopy START"
            return payload

    result = DPO2012B(ScreenshotBackend()).capture_screenshot(image_format)
    assert base64.b64decode(result["data"]) == payload


def test_query_rejects_mixed_write_and_query_segments() -> None:
    backend = FakeBackend()
    with pytest.raises(ValueError, match="Every SCPI segment"):
        DPO2012B(backend).query("CH1:SCALE 1;*IDN?")
