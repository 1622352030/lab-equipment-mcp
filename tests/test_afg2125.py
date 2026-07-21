import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.core.transports.visa import VisaBackend, VisaResource
from lab_equipment_mcp.devices.gw_instek.afg_2125 import (
    AFG2125,
    AFG2125_PROFILE,
    square_duty_limits,
)


class FakeBackend:
    resource_name = "ASRL5::INSTR"

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.responses = {
            "SOURCE1:FUNCTION?": "SQU",
            "SOURCE1:FREQUENCY?": "+1.00000000E+03",
            "SOURCE1:AMPLITUDE?": "+2.500E+00",
            "SOURCE1:VOLTAGE:UNIT?": "VPP",
            "SOURCE1:DCOFFSET?": "+1.25E+00",
            "SOURCE1:APPLY?": '"SQU +1.00000000E+03,+2.500E+00,+1.25E+00"',
            "SOURCE1:OUTPUT?": "0",
            "SOURCE1:SQUARE:DCYCLE?": "+8.00E+01",
            "SOURCE1:AM:STATE?": "0",
            "SOURCE1:FM:STATE?": "0",
            "SOURCE1:FSKEY:STATE?": "0",
            "SOURCE1:SWEEP:STATE?": "0",
            "SOURCE1:AM:SOURCE?": "INT",
            "SOURCE1:AM:INTERNAL:FUNCTION?": "SIN",
            "SOURCE1:AM:INTERNAL:FREQUENCY?": "100",
            "SOURCE1:AM:DEPTH?": "50",
            "SOURCE1:FM:SOURCE?": "INT",
            "SOURCE1:FM:INTERNAL:FUNCTION?": "SIN",
            "SOURCE1:FM:INTERNAL:FREQUENCY?": "10",
            "SOURCE1:FM:DEVIATION?": "100",
            "SOURCE1:FSKEY:SOURCE?": "INT",
            "SOURCE1:FSKEY:FREQUENCY?": "1000",
            "SOURCE1:FSKEY:INTERNAL:RATE?": "10",
            "SOURCE1:FREQUENCY:START?": "100",
            "SOURCE1:FREQUENCY:STOP?": "1000",
            "SOURCE1:SWEEP:SPACING?": "LIN",
            "SOURCE1:SWEEP:SOURCE?": "INT",
        }

    def query(self, command: str) -> str:
        return self.responses[command.upper()]

    def write(self, command: str) -> None:
        self.writes.append(command)
        upper = command.upper()
        if upper.startswith("SOURCE1:OUTPUT "):
            self.responses["SOURCE1:OUTPUT?"] = "1" if upper.endswith(" ON") else "0"
        for mode in ("AM", "FM", "FSKEY", "SWEEP"):
            prefix = f"SOURCE1:{mode}:STATE "
            if upper.startswith(prefix):
                self.responses[f"SOURCE1:{mode}:STATE?"] = (
                    "1" if upper.endswith(" ON") else "0"
                )


def connected_driver(backend: FakeBackend) -> AFG2125:
    driver = AFG2125(backend)
    driver._connected_resource = backend.resource_name
    driver._identity = "GW INSTEK,AFG-2125,SN:REDACTED,V1.11"
    return driver


def test_profile_declares_usb_cdc_as_serial() -> None:
    interface = AFG2125_PROFILE.interfaces[0]
    assert interface.interface_type is InterfaceType.RS232
    assert interface.session.baud_rate == 19200
    assert interface.session.data_bits == 8
    assert interface.session.stop_bits == 1
    assert interface.session.parity == "none"
    assert interface.session.flow_control == "none"
    assert "USB CDC" in interface.connection_notes


def test_discovery_only_selects_pnp_filtered_serial_port() -> None:
    backend = VisaBackend()
    backend.list_resources = lambda **kwargs: [
        VisaResource("ASRL4::INSTR", "ASRL4", InterfaceType.RS232),
        VisaResource("ASRL5::INSTR", "ASRL5", InterfaceType.RS232),
    ]
    matches = AFG2125(backend, port_discovery=lambda: {"COM5"}).find_resources()
    assert [match.resource for match in matches] == ["ASRL5::INSTR"]


def test_connect_applies_session_and_accepts_identity() -> None:
    class Backend:
        resource_name = None
        connected = None

        def connect(self, resource, timeout_ms, session):
            self.connected = (resource, timeout_ms, session)
            self.resource_name = resource
            return "GW INSTEK,AFG-2125,SN:REDACTED,V1.11"

        def disconnect(self):
            self.resource_name = None

    backend = Backend()
    identity = AFG2125(backend).connect("ASRL5::INSTR")
    assert "AFG-2125" in identity
    assert backend.connected[2].baud_rate == 19200


def test_connect_rejects_wrong_identity() -> None:
    class Backend:
        def connect(self, *args):
            return "OTHER,DEVICE,REDACTED,1.0"

        def disconnect(self):
            self.disconnected = True

    with pytest.raises(ScopeError, match="not a GW Instek AFG-2125"):
        AFG2125(Backend()).connect("ASRL5::INSTR")


def test_get_settings_uses_source_prefixed_output_query() -> None:
    backend = FakeBackend()
    settings = connected_driver(backend).get_settings()
    assert settings["frequency_hz"] == 1000
    assert settings["amplitude"] == 2.5
    assert settings["offset_volts"] == 1.25
    assert settings["output_enabled"] is False
    assert settings["output_state_raw"] == "0"
    assert settings["sync_cold_start_risk"] is True
    assert "complementary duty cycle" in settings["sync_cold_start_warning"]


def test_get_settings_clears_cold_start_warning_after_main_is_enabled() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:OUTPUT?"] = "1"
    settings = connected_driver(backend).get_settings()
    assert settings["sync_cold_start_risk"] is False
    assert settings["sync_cold_start_warning"] is None


def test_get_settings_limits_cold_start_warning_to_v111_square_mode() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    driver._identity = "GW INSTEK,AFG-2125,SN:REDACTED,V2.07"
    assert driver.get_settings()["sync_cold_start_risk"] is False

    driver._identity = "GW INSTEK,AFG-2125,SN:REDACTED,V1.11"
    backend.responses["SOURCE1:FUNCTION?"] = "SIN"
    assert driver.get_settings()["sync_cold_start_risk"] is False


@pytest.mark.parametrize(
    ("frequency", "limits"),
    [
        (99_999, (1.0, 99.0)),
        (100_000, (20.0, 80.0)),
        (5_000_000, (40.0, 60.0)),
        (10_000_000, (50.0, 50.0)),
    ],
)
def test_square_duty_limits(frequency, limits) -> None:
    assert square_duty_limits(frequency) == limits


def test_square_duty_is_sent_directly_and_verified_by_readback() -> None:
    backend = FakeBackend()
    actual = connected_driver(backend).set_square_duty(80)
    assert backend.writes[-1] == "SOURce1:SQUare:DCYCle 80"
    assert actual == 80


def test_square_duty_rejects_readback_mismatch() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:SQUARE:DCYCLE?"] = "20"
    with pytest.raises(ScopeError, match="read-back mismatch"):
        connected_driver(backend).set_square_duty(80)


def test_mode_settings_parse_all_mutually_exclusive_states() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:FM:STATE?"] = "1"
    assert connected_driver(backend).get_mode_settings() == {
        "am_enabled": False,
        "fm_enabled": True,
        "fsk_enabled": False,
        "sweep_enabled": False,
    }


def test_mode_state_change_requires_matching_readback() -> None:
    backend = FakeBackend()
    backend.write = lambda command: backend.writes.append(command)
    with pytest.raises(ScopeError, match="mode-state read-back mismatch"):
        connected_driver(backend).set_am_enabled(True)


def test_configure_internal_am_uses_manual_order_and_readback() -> None:
    backend = FakeBackend()
    result = connected_driver(backend).configure_am(
        modulation_function="sine", modulation_frequency_hz=100, depth_percent=50
    )
    assert result["enabled"] is True
    assert result["depth_percent"] == 50
    assert backend.writes == [
        "SOURce1:AM:STATe ON",
        "SOURce1:AM:SOURce INTernal",
        "SOURce1:AM:INTernal:FUNCtion SINusoid",
        "SOURce1:AM:INTernal:FREQuency 100",
        "SOURce1:AM:DEPTh 50",
    ]


def test_configure_external_am_ignores_internal_only_parameters() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:AM:SOURCE?"] = "EXT"
    result = connected_driver(backend).configure_am(
        source="external",
        modulation_function="not-used",
        modulation_frequency_hz=-1,
        depth_percent=-1,
    )
    assert result == {"enabled": True, "source": "EXT"}


def test_configure_fm_checks_carrier_deviation_and_writes_parameters() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    result = driver.configure_fm(deviation_hz=100, modulation_frequency_hz=10)
    assert result["deviation_hz"] == 100
    assert backend.writes[0] == "SOURce1:FM:STATe ON"
    with pytest.raises(ValueError, match="carrier/function limits"):
        driver.configure_fm(deviation_hz=1001)


def test_configure_fsk_validates_rate_and_hop_frequency() -> None:
    backend = FakeBackend()
    result = connected_driver(backend).configure_fsk(
        hop_frequency_hz=1000, rate_hz=10
    )
    assert result["hop_frequency_hz"] == 1000
    assert result["rate_hz"] == 10
    with pytest.raises(ValueError, match="rate_hz"):
        connected_driver(backend).configure_fsk(rate_hz=100_001)


def test_configure_sweep_supports_direction_spacing_time_and_source() -> None:
    backend = FakeBackend()
    result = connected_driver(backend).configure_sweep(
        start_frequency_hz=100,
        stop_frequency_hz=1000,
        sweep_time_s=1,
        spacing="linear",
        source="immediate",
    )
    assert result["start_frequency_hz"] == 100
    assert result["stop_frequency_hz"] == 1000
    assert result["spacing"] == "LIN"
    assert result["sweep_time_s_requested"] == 1
    assert "time out" in result["sweep_time_verification"]
    assert result["source"] == "INT"
    assert backend.writes[0] == "SOURce1:SWEep:STATe ON"
    assert "SOURce1:SWEep:TIME 1" in backend.writes


def test_configure_arbitrary_waveform_enforces_rate_and_verifies_selection() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:FUNCTION?"] = "ARB"
    backend.responses["SOURCE1:FREQUENCY?"] = "1000"
    result = connected_driver(backend).configure_arbitrary_waveform(
        [-511, 0, 511, 0], frequency_hz=1000
    )
    assert result["function"] == "ARB"
    assert result["waveform_rate_hz"] == 4000
    assert backend.writes == [
        "DATA:DAC VOLATILE,0,-511,0,511,0",
        "SOURce1:FUNCtion USER",
        "SOURce1:FREQuency 1000",
    ]
    with pytest.raises(ValueError, match="20 MHz ARB rate"):
        connected_driver(FakeBackend()).configure_arbitrary_waveform(
            [0] * 4096, frequency_hz=10_000
        )


def test_frequency_limits_follow_function() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    driver.set_frequency(25_000_000, "sine")
    assert backend.writes[-1] == "SOURce1:FREQuency 25000000"
    with pytest.raises(ValueError, match="1000000 Hz"):
        driver.set_frequency(1_000_001, "ramp")


def test_amplitude_and_offset_headroom_is_validated() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    driver.set_amplitude(2.0)
    driver.set_offset(1.0)
    assert backend.writes == [
        "SOURce1:VOLTage:UNIT VPP",
        "SOURce1:AMPlitude 2VPP",
        "SOURce1:DCOffset 1",
    ]
    backend.responses["SOURCE1:DCOFFSET?"] = "4.9"
    with pytest.raises(ValueError, match="output limit"):
        driver.set_amplitude(1.0)


def test_offset_rejects_non_vpp_unit_for_safe_headroom_check() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:VOLTAGE:UNIT?"] = "VRMS"
    with pytest.raises(ValueError, match="requires VPP"):
        connected_driver(backend).set_offset(0.0)


def test_arbitrary_waveform_validation_and_command() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    result = driver.upload_arbitrary_waveform([511, 0, -511], start=10)
    assert result == {"start": 10, "point_count": 3, "end": 12}
    assert backend.writes[-1] == "DATA:DAC VOLATILE,10,511,0,-511"
    with pytest.raises(ValueError, match="between -511 and 511"):
        driver.upload_arbitrary_waveform([0, 512])
    with pytest.raises(ValueError, match="between 2 and 4096"):
        driver.upload_arbitrary_waveform([0])


def test_arbitrary_waveform_upload_requires_output_disabled() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:OUTPUT?"] = "1"
    with pytest.raises(ValueError, match="output is enabled"):
        connected_driver(backend).upload_arbitrary_waveform([0, 1])


def test_output_enable_requires_explicit_confirmation() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    with pytest.raises(ValueError, match="confirm_enable=true"):
        driver.set_output(True)
    driver.set_output(False)
    driver.set_output(True, confirm_enable=True)
    assert backend.writes == ["SOURce1:OUTPut OFF", "SOURce1:OUTPut ON"]


def test_settings_require_output_to_be_disabled() -> None:
    backend = FakeBackend()
    backend.responses["SOURCE1:OUTPUT?"] = "1"
    with pytest.raises(ValueError, match="output is enabled"):
        connected_driver(backend).set_function("sine")
    assert backend.writes == []


def test_raw_apply_and_output_commands_are_blocked() -> None:
    driver = connected_driver(FakeBackend())
    with pytest.raises(ValueError, match="guarded model tools"):
        driver.write("SOURce1:APPLy:SINusoid 1000,1,0")
    with pytest.raises(ValueError, match="guarded model tools"):
        driver.write("OUTPut ON")


def test_model_tools_reject_a_different_active_instrument() -> None:
    backend = FakeBackend()
    driver = connected_driver(backend)
    backend.resource_name = "USB0::SCOPE::INSTR"
    with pytest.raises(ScopeError, match="No verified AFG-2125"):
        driver.get_settings()
