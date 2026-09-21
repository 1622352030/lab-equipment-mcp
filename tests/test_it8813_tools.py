"""MCP handshake and tool-surface tests for the IT8813 electronic load.

`acceptance.md` requires that a standard MCP handshake lists the new tools and that a
diagnostic tool can be called. These tests exercise the real FastMCP registration, not a
stub, so a tool that fails to register or loses its safety annotation is caught here.

Nothing in this file touches hardware: the endpoint tool reads environment variables and
the guarded tools are expected to refuse before any session is opened.
"""

from __future__ import annotations

import asyncio

import pytest

from lab_equipment_mcp import server

EXPECTED_TOOLS = (
    # diagnose / connect
    "it8813_diagnose_setup",
    "it8813_get_endpoint",
    "it8813_connect",
    "it8813_disconnect",
    "it8813_identify",
    # system
    "it8813_get_settings",
    "it8813_get_errors",
    "it8813_clear_errors",
    "it8813_clear_system",
    "it8813_press_key",
    "it8813_reset",
    "it8813_preset",
    "it8813_set_remote",
    "it8813_set_display_text",
    "it8813_set_display_mode",
    "it8813_get_identity_info",
    # function / input
    "it8813_set_function",
    "it8813_get_function",
    "it8813_set_function_mode",
    "it8813_set_input",
    "it8813_get_input",
    "it8813_set_input_short",
    "it8813_clear_protection",
    "it8813_set_input_timer",
    "it8813_set_transient_state",
    # four regulation modes
    "it8813_set_current",
    "it8813_get_current",
    "it8813_set_current_range",
    "it8813_set_current_protection",
    "it8813_get_current_protection",
    "it8813_set_current_slew",
    "it8813_set_current_transient",
    "it8813_set_voltage",
    "it8813_get_voltage",
    "it8813_set_voltage_range",
    "it8813_set_voltage_on",
    "it8813_set_voltage_latch",
    "it8813_set_voltage_transient",
    "it8813_set_resistance",
    "it8813_get_resistance",
    "it8813_set_resistance_range",
    "it8813_set_resistance_transient",
    "it8813_set_resistance_features",
    "it8813_set_power",
    "it8813_get_power",
    "it8813_set_power_range",
    "it8813_set_power_protection",
    "it8813_get_power_protection",
    "it8813_set_power_config",
    "it8813_set_power_transient",
    # measurement
    "it8813_measure_voltage",
    "it8813_measure_current",
    "it8813_measure_power",
    "it8813_measure_all",
    "it8813_fetch_voltage",
    "it8813_fetch_current",
    "it8813_fetch_power",
    "it8813_fetch_voltage_max",
    "it8813_fetch_voltage_min",
    "it8813_fetch_current_max",
    "it8813_fetch_current_min",
    "it8813_get_measurement_info",
    # trigger / trace / list / sense / status
    "it8813_trigger",
    "it8813_set_trigger_source",
    "it8813_set_trigger_timer",
    "it8813_set_trace",
    "it8813_get_trace_settings",
    "it8813_clear_trace",
    "it8813_read_trace",
    "it8813_set_list",
    "it8813_set_list_step",
    "it8813_get_list_settings",
    "it8813_get_list_step",
    "it8813_save_list",
    "it8813_recall_list",
    "it8813_set_sense_average",
    "it8813_get_status_registers",
    "it8813_set_status_enable",
    "it8813_status_preset",
    "it8813_save_state",
    "it8813_recall_state",
    "it8813_self_test",
    # the complete entry point for documented commands with no typed tool
    "it8813_query_scpi",
    "it8813_write_scpi",
)


def _tool_map() -> dict:
    tools = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool for tool in tools}


@pytest.fixture(scope="module")
def tools() -> dict:
    return _tool_map()


def test_handshake_lists_every_it8813_tool(tools: dict) -> None:
    registered = {name for name in tools if name.startswith("it8813_")}
    missing = sorted(set(EXPECTED_TOOLS) - registered)
    assert missing == [], f"these IT8813 tools are not registered: {missing}"


def test_tool_names_are_model_prefixed(tools: dict) -> None:
    """Every IT8813 tool must carry the model prefix (skill step 9)."""
    assert len([n for n in tools if n.startswith("it8813_")]) == len(EXPECTED_TOOLS)


def test_read_only_tools_are_annotated_read_only(tools: dict) -> None:
    for name in (
        "it8813_get_settings",
        "it8813_get_errors",
        "it8813_identify",
        "it8813_measure_voltage",
        "it8813_measure_all",
        "it8813_get_status_registers",
        "it8813_query_scpi",
        "it8813_get_endpoint",
    ):
        annotations = tools[name].annotations
        assert annotations is not None, f"{name} has no annotations"
        assert annotations.readOnlyHint is True, f"{name} should be read-only"


def test_energy_moving_tools_are_annotated_destructive(tools: dict) -> None:
    """Energising the input, the deliberate short, and raw SCPI are flagged."""
    for name in ("it8813_set_input", "it8813_set_input_short", "it8813_write_scpi"):
        annotations = tools[name].annotations
        assert annotations is not None, f"{name} has no annotations"
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is True, f"{name} should be destructive"


def test_state_changing_tools_declare_themselves(tools: dict) -> None:
    for name in (
        "it8813_set_function",
        "it8813_set_current",
        "it8813_set_voltage",
        "it8813_set_power",
        "it8813_connect",
        "it8813_disconnect",
    ):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is False, f"{name} changes state"


# -- a diagnostic tool is callable without hardware -------------------------


def test_endpoint_tool_is_callable_and_reports_the_limits() -> None:
    """The handshake must be able to actually call a tool, not just list it."""
    result = server.it8813_get_endpoint()
    assert result["resource"].upper().startswith("USB") or result["resource"].upper().startswith(
        "ASRL"
    )
    assert result["resource_env"] == "LAB_EQUIPMENT_IT8813_RESOURCE"
    # the test-phase ceilings must be below the instrument ratings
    assert result["current_limit_a"] < 6.0
    assert result["power_limit_w"] < 750.0


def test_endpoint_tool_follows_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("LAB_EQUIPMENT_IT8813_RESOURCE", "ASRL7::INSTR")
    assert server.it8813_get_endpoint()["resource"] == "ASRL7::INSTR"


# -- guards a caller cannot bypass -----------------------------------------


def test_raw_write_tool_refuses_without_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm_unsafe"):
        server.it8813_write_scpi("CURRent 5")


def test_raw_write_tool_refuses_a_query() -> None:
    with pytest.raises(ValueError, match="setting command"):
        server.it8813_write_scpi("CURRent?", confirm_unsafe=True)


def test_query_tool_refuses_a_setting_command() -> None:
    with pytest.raises(ValueError, match="query"):
        server.it8813_query_scpi("CURRent 5")


def test_reset_and_preset_refuse_without_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm"):
        server.it8813_reset()
    with pytest.raises(ValueError, match="confirm"):
        server.it8813_preset()


def test_errors_tool_checks_its_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        server.it8813_get_errors(limit=100)


def test_out_of_scope_trigger_source_is_still_reachable_but_flagged() -> None:
    """The tool accepts the documented EXTernal value and flags it rather than hiding it."""
    doc = server.it8813_set_trigger_source.__doc__ or ""
    assert "out of scope" in doc.lower()


def test_diagnose_does_not_claim_usb_is_missing_when_a_usbtmc_resource_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: `visa_resources` was built as `str(VisaResource(...))`.

    That string does not start with "USB", so the "no USB VISA resource" recommendation
    fired whenever *any* resource had been enumerated. Measured on hardware: the tool
    listed the IT8813's USB resource, probed it successfully, and still advised checking
    the USB Type-B cable.
    """
    from lab_equipment_mcp.core.interfaces import InterfaceType

    class FakeResource:
        resource = "USB0::0x2EC7::0x8800::800835011777320005::INSTR"
        interface = "USB0"
        interface_type = InterfaceType.USBTMC
        idn = "ITECH Ltd., IT8813, 800835011777320005, 1.39-1.42"
        error = None

    class FakeBackend:
        def list_resources(self, **kwargs):  # noqa: ANN003, ANN201
            return [FakeResource()]

        def connect(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
            return FakeResource.idn

        def query(self, command):  # noqa: ANN001, ANN201
            return FakeResource.idn

        def write(self, command):  # noqa: ANN001, ANN201
            pass

        def disconnect(self):  # noqa: ANN201
            pass

    monkeypatch.setattr(server, "VisaBackend", FakeBackend)
    result = server.it8813_diagnose_setup(probe=True)

    assert result["visa_resources"] == [FakeResource.resource]
    assert result["visa_resource_details"] == [
        {
            "resource": FakeResource.resource,
            "interface": "USB0",
            "interface_type": "usbtmc",
            "idn": FakeResource.idn,
            "error": None,
        }
    ]
    assert result["probe"]["reachable"] is True
    assert not any("No USB VISA resource" in item for item in result["recommendations"])
