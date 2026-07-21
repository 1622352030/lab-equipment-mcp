import re

from .errors import UnsafeCommandError

_BLOCKED_PATTERNS = (
    r"(^|:)CAL(?:IBRATE)?(?:\s|:|$)",
    r"(^|:)FAC(?:TORY)?(?:\s|:|$)",
    r"(^|:)FILESystem:(?:DELete|REName|FORMat)",
    r"(^|:)MEMory:(?:DELete|INITialize)",
    r"(^|:)MEM(?:ORY)?:STAT(?:E)?:DEL(?:ETE)?(?:\s|;|$)",
    r"(^|:)MMEM(?:ORY)?:(?:DEL(?:ETE)?|MOVE|COPY)",
    r"(^|:)SYSTem:LICense:(?:INSTall|DELete)",
    r"(^|:)SYSTem:SECurity:IMMediate(?:\s|;|$)",
    r"(^|:)SYST(?:EM)?:LIC(?:ENSE)?:(?:INST(?:ALL)?|DEL(?:ETE)?)",
    r"(^|:)SYST(?:EM)?:SEC(?:URITY)?:IMM(?:EDIATE)?(?:\s|;|$)",
    r"(^|:)SECure(?:\s|:|$)",
    r"(^|:)FIRMware(?:\s|:|$)",
    r"(^|:)UPDate(?:\s|:|$)",
    r"\*RST(?:\s|;|$)",
    r"\*RCL(?:\s|;|$)",
    r"\*SAV(?:\s|;|$)",
    r"\*TST\?(?:\s|;|$)",
)


def validate_scpi(command: str, *, allow_unsafe: bool = False) -> str:
    command = command.strip()
    if not command:
        raise ValueError("SCPI command cannot be empty")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in command):
        raise ValueError("SCPI command contains unsupported control characters")

    normalized = command.upper()
    if not allow_unsafe:
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                raise UnsafeCommandError(
                    "Blocked potentially destructive command. "
                    "Calibration, reset/recall/save, firmware, and file deletion commands "
                    "are disabled by default."
                )
    return command
