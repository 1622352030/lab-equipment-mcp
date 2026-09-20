from lab_equipment_mcp.devices.siglent import diagnostics


def test_windows_parser_redacts_serial_and_accepts_usbtmc(monkeypatch) -> None:
    pnp_output = r"""
Instance ID:                USB\VID_F4EC&PID_1103\PRIVATE-SERIAL
Device Description:         USB Test and Measurement Device (IVI)
Class Name:                 USBTestAndMeasurementDevice
Driver Name:                oem124.inf
"""

    class Result:
        stdout = pnp_output

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    devices = diagnostics.windows_sdg_devices()
    assert devices == [
        {
            "name": "Siglent SDG Series USBTMC",
            "usb_id": "VID_F4EC&PID_1103",
            "sdg1062x_product_id": True,
            "driver_name": "oem124.inf",
            "driver_problem": False,
        }
    ]
    assert "PRIVATE-SERIAL" not in str(devices)


def test_windows_parser_ignores_other_vendors(monkeypatch) -> None:
    class Result:
        stdout = "USB\\VID_0699&PID_039D USB Test and Measurement Device"

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    assert diagnostics.windows_sdg_devices() == []


class FakeLanSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = b""
        self._delivered = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, value):
        return None

    def sendall(self, data: bytes) -> None:
        self.sent = data

    def recv(self, size: int) -> bytes:
        if self._delivered:
            return b""
        self._delivered = True
        return self.response


def test_lan_probe_reads_identity_and_redacts_serial(monkeypatch) -> None:
    fake = FakeLanSocket(b"Siglent Technologies,SDG1062X,PRIVATE-SERIAL,1.01.01.30R1\n")
    monkeypatch.setattr(diagnostics.socket, "create_connection", lambda *a, **k: fake)
    result = diagnostics.probe_lan_socket("10.11.9.230")
    assert result["reachable"] is True
    assert result["identity"] == "Siglent Technologies,SDG1062X,<redacted>,1.01.01.30R1"
    assert "PRIVATE-SERIAL" not in str(result)
    assert fake.sent == b"*IDN?\n"


def test_lan_probe_reports_an_unreachable_host(monkeypatch) -> None:
    def unreachable(*args, **kwargs):
        raise OSError("connection timed out")

    monkeypatch.setattr(diagnostics.socket, "create_connection", unreachable)
    # 192.0.2.0/24 is TEST-NET-1 (RFC 5737), reserved for documentation, so this
    # example address can never collide with a real instrument. An earlier
    # revision used a live lab address here and it ended up clashing with the
    # IT7321 installed on the same bench.
    result = diagnostics.probe_lan_socket("192.0.2.10")
    assert result["reachable"] is False
    assert result["identity"] is None
    assert "timed out" in result["error"]


def test_lan_probe_reports_an_empty_response(monkeypatch) -> None:
    fake = FakeLanSocket(b"")
    monkeypatch.setattr(diagnostics.socket, "create_connection", lambda *a, **k: fake)
    result = diagnostics.probe_lan_socket("10.11.9.230")
    assert result["reachable"] is False
    assert "no identity" in result["error"]


def test_identity_redaction_keeps_other_fields() -> None:
    assert (
        diagnostics.redact_identity("Siglent Technologies,SDG1062X,SERIALNUMBER,1.01.01.30R1")
        == "Siglent Technologies,SDG1062X,<redacted>,1.01.01.30R1"
    )
    assert diagnostics.redact_identity("short,response") == "<unexpected identity shape>"


def test_diagnose_reports_lan_readiness_without_usb(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "windows_sdg_devices", lambda: [])
    monkeypatch.setattr(diagnostics, "find_visa_libraries", lambda: ["visa32.dll"])
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        diagnostics,
        "probe_lan_socket",
        lambda host, **kwargs: {
            "host": host,
            "port": 5025,
            "reachable": True,
            "identity": "Siglent Technologies,SDG1062X,<redacted>,1.01.01.30R1",
            "error": None,
        },
    )
    result = diagnostics.diagnose_host(None, lan_hosts=["10.11.9.230"])
    assert result["lan_ready"] is True
    assert result["usb_ready"] is False
    assert result["ready"] is True
    assert result["lan_probes"][0]["host"] == "10.11.9.230"


def test_diagnose_guides_lan_when_nothing_is_found(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "windows_sdg_devices", lambda: [])
    monkeypatch.setattr(diagnostics, "find_visa_libraries", lambda: ["visa32.dll"])
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda name: object())
    result = diagnostics.diagnose_host(None)
    assert result["ready"] is False
    assert any("does not enumerate LAN" in item for item in result["recommendations"])


def test_diagnose_reports_an_unanswered_lan_probe(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "windows_sdg_devices", lambda: [])
    monkeypatch.setattr(diagnostics, "find_visa_libraries", lambda: ["visa32.dll"])
    monkeypatch.setattr(diagnostics.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        diagnostics,
        "probe_lan_socket",
        lambda host, **kwargs: {
            "host": host,
            "port": 5025,
            "reachable": False,
            "identity": None,
            "error": "OSError: timed out",
        },
    )
    result = diagnostics.diagnose_host(None, lan_hosts=["192.0.2.10"])
    assert result["lan_ready"] is False
    assert any("subnet" in item for item in result["recommendations"])
