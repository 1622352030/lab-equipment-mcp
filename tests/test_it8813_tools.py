"""MCP handshake and tool-surface tests for the IT8813 electronic load.

`acceptance.md` requires that a standard MCP handshake lists the new tools and that a
diagnostic tool can be called. These tests exercise the real FastMCP registration, not a
stub, so a tool that fails to register or loses its safety annotation is caught here.

Nothing in this file touches hardware: the endpoint tool reads environment variables and
the guarded tools are expected to refuse before any session is opened.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

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
    "it8813_get_power_on_setup",
    "it8813_set_remote",
    "it8813_set_display_text",
    "it8813_set_display_mode",
    "it8813_get_display_mode",
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
    "it8813_get_input_timer",
    "it8813_set_transient_state",
    # four regulation modes
    "it8813_set_current",
    "it8813_get_current",
    "it8813_set_current_range",
    "it8813_get_current_range_bounds",
    "it8813_set_current_protection",
    "it8813_get_current_protection",
    "it8813_set_current_slew",
    "it8813_get_current_slew",
    "it8813_set_current_transient",
    "it8813_get_current_transient",
    "it8813_set_voltage",
    "it8813_get_voltage",
    "it8813_set_voltage_range",
    "it8813_get_voltage_range_auto",
    "it8813_get_voltage_range_bounds",
    "it8813_set_voltage_on",
    "it8813_get_voltage_on",
    "it8813_set_voltage_latch",
    "it8813_get_voltage_latch",
    "it8813_set_voltage_transient",
    "it8813_get_voltage_transient",
    "it8813_set_resistance",
    "it8813_get_resistance",
    "it8813_set_resistance_range",
    "it8813_get_resistance_range_bounds",
    "it8813_set_resistance_transient",
    "it8813_get_resistance_transient",
    "it8813_set_resistance_features",
    "it8813_get_resistance_features",
    "it8813_set_power",
    "it8813_get_power",
    "it8813_set_power_range",
    "it8813_get_power_range_bounds",
    "it8813_set_power_protection",
    "it8813_get_power_protection",
    "it8813_set_power_config",
    "it8813_get_power_config",
    "it8813_set_power_transient",
    "it8813_get_power_transient",
    # measurement
    "it8813_measure_voltage",
    "it8813_measure_current",
    "it8813_measure_power",
    "it8813_measure_all",
    "it8813_measure_voltage_max",
    "it8813_measure_voltage_min",
    "it8813_measure_current_max",
    "it8813_measure_current_min",
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
    "it8813_get_trigger_timer",
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
    "it8813_get_sense_average",
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


# -- the tool surface must not be able to hide a read-back -------------------


def _audit_readbacks() -> tuple[set[str], set[str]]:
    """Return (public driver read-backs, the ones no it8813 tool can reach).

    A read-back is a public driver method that reads something through `self._query` and
    is not a `set_*`. Reachability follows the driver's own call graph (`self.<name>`), so
    a query used inside another driver method is not counted as missing.
    """
    driver_path = Path(server.__file__).parent / "devices" / "itech" / "it8813.py"
    driver_tree = ast.parse(driver_path.read_text(encoding="utf-8"))
    classes = [n for n in driver_tree.body if isinstance(n, ast.ClassDef)]
    driver_cls = max(classes, key=lambda c: sum(isinstance(n, ast.FunctionDef) for n in c.body))
    methods = {n.name: n for n in driver_cls.body if isinstance(n, ast.FunctionDef)}

    reachable: set[str] = set()
    server_tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(server_tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        tool_name = None
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr != "tool":
                continue
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    tool_name = str(kw.value.value)
        if tool_name is None or not tool_name.startswith("it8813_"):
            continue
        reachable.update(inner.attr for inner in ast.walk(node) if isinstance(inner, ast.Attribute))

    frontier = {name for name in reachable if name in methods}
    while frontier:
        nxt: set[str] = set()
        for name in frontier:
            for inner in ast.walk(methods[name]):
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == "self"
                    and inner.attr in methods
                    and inner.attr not in reachable
                ):
                    reachable.add(inner.attr)
                    nxt.add(inner.attr)
        frontier = nxt

    readbacks = {
        name
        for name, node in methods.items()
        if not name.startswith("_")
        and not name.startswith("set_")
        and any(
            isinstance(inner, ast.Attribute)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "self"
            and inner.attr in {"_query", "_mode_query", "_text_query"}
            for inner in ast.walk(node)
        )
    }
    return readbacks, readbacks - reachable


# Read-backs that deliberately have no tool, each registered with its reason instead of
# being left as a hole in the rule. `*OPC?` is a synchronisation handshake, not instrument
# state: its answer is 1 once the pending operations drain, and every typed write already
# issues it through the driver's `_sync`, so a tool would add a blocking call and no
# information.
INTERNAL_READBACKS = {"operation_complete"}


def test_every_driver_readback_is_reachable_from_a_tool() -> None:
    """Regression: a value the driver can read and no MCP tool can report.

    The command-coverage audits in `test_it8813.py` are keyed on *manual commands*, so a
    driver method that already issues the documented command counts as covered even when
    no tool ever calls it. Measured on hardware: `POWer:CONFig` (the hardware power clamp)
    and `VOLTage:ON` (the level the input switches on at) could both be **written through
    MCP and read through nothing**, and a demonstration ran behind a 5 W clamp that no
    read-only tool disclosed.
    """
    readbacks, unreachable = _audit_readbacks()
    # a wrong path would leave both sets empty and this test would pass vacuously
    assert len(readbacks) > 50, f"the audit found only {len(readbacks)} read-backs"
    assert "voltage_on_query" in readbacks
    # the exemption list must not rot: every name in it must still be a real read-back
    stale = INTERNAL_READBACKS - readbacks
    assert stale == set(), f"the exemption list is stale: {sorted(stale)}"
    missing = unreachable - INTERNAL_READBACKS
    assert missing == set(), f"no tool reaches these driver read-backs: {sorted(missing)}"


WRITE_THEN_READ = {
    "it8813_set_display_mode": "it8813_get_display_mode",
    "it8813_set_input_timer": "it8813_get_input_timer",
    "it8813_set_current_slew": "it8813_get_current_slew",
    "it8813_set_current_transient": "it8813_get_current_transient",
    "it8813_set_voltage_range": "it8813_get_voltage_range_auto",
    "it8813_set_voltage_on": "it8813_get_voltage_on",
    "it8813_set_voltage_latch": "it8813_get_voltage_latch",
    "it8813_set_voltage_transient": "it8813_get_voltage_transient",
    "it8813_set_resistance_transient": "it8813_get_resistance_transient",
    "it8813_set_resistance_features": "it8813_get_resistance_features",
    "it8813_set_power_config": "it8813_get_power_config",
    "it8813_set_power_transient": "it8813_get_power_transient",
    "it8813_set_trigger_timer": "it8813_get_trigger_timer",
    "it8813_set_sense_average": "it8813_get_sense_average",
}


def test_every_setting_that_can_be_written_can_also_be_read(tools: dict) -> None:
    """Every setting writable through a tool has a tool that reads it back."""
    for writer, reader in WRITE_THEN_READ.items():
        assert writer in tools, f"{writer} is not registered"
        assert reader in tools, f"{writer} has no read-back tool ({reader})"
        annotations = tools[reader].annotations
        assert annotations is not None, f"{reader} has no annotations"
        assert annotations.readOnlyHint is True, f"{reader} should be read-only"


def test_get_settings_reports_the_settings_that_silently_gate_an_experiment() -> None:
    """The aggregate read-back omitted the power clamp and the switch-on level."""
    source = inspect.getsource(server.it8813_get_settings)
    for method in ("voltage_on_query", "power_config_query", "input_timer_query"):
        assert method in source, f"it8813_get_settings does not report {method}"


def test_get_and_measure_tools_are_annotated_read_only(tools: dict) -> None:
    """Generic guard, so a new read-back tool cannot forget its annotation."""
    checked = 0
    for name, tool in tools.items():
        if not name.startswith(("it8813_get_", "it8813_measure_", "it8813_fetch_")):
            continue
        checked += 1
        annotations = tool.annotations
        assert annotations is not None, f"{name} has no annotations"
        assert annotations.readOnlyHint is True, f"{name} should be read-only"
    assert checked > 40, f"only {checked} read-back tools were checked"
