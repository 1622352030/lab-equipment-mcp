import pytest

from lab_equipment_mcp.core.errors import UnsafeCommandError
from lab_equipment_mcp.core.safety import validate_scpi


@pytest.mark.parametrize(
    "command",
    [
        "*RST",
        "*RCL 1",
        "*SAV 1",
        "*TST?",
        "CALIBRATE:START",
        'FILESYSTEM:DELETE "a"',
        'MMEMORY:DELETE "a"',
        'MMEM:DEL "a"',
        "MEMORY:STATE:DELETE 1",
        'SYSTEM:LICENSE:INSTALL "a"',
        "SYSTEM:SECURITY:IMMEDIATE",
    ],
)
def test_blocks_unsafe_commands(command: str) -> None:
    with pytest.raises(UnsafeCommandError):
        validate_scpi(command)


def test_allows_normal_queries_and_settings() -> None:
    assert validate_scpi("*IDN?") == "*IDN?"
    assert validate_scpi("CH1:SCALE 1.0") == "CH1:SCALE 1.0"


def test_explicit_override_allows_unsafe_command() -> None:
    assert validate_scpi("*RST", allow_unsafe=True) == "*RST"
