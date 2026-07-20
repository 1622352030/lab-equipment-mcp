import pytest

from dpo2012b_mcp.errors import ScopeError
from dpo2012b_mcp.visa_backend import VisaBackend, VisaResource


def test_dpo_detection_by_identity() -> None:
    backend = VisaBackend()
    backend.list_resources = lambda probe=True: [
        VisaResource("USB0::x::INSTR", "USB0", "TEKTRONIX,DPO2012B,C010423,1.0"),
        VisaResource("USB0::y::INSTR", "USB0", "OTHER,DEVICE,1,1"),
    ]
    matches = backend.find_dpo2012b()
    assert len(matches) == 1
    assert "DPO2012B" in (matches[0].idn or "")


def test_serial_resources_are_not_probed() -> None:
    class Manager:
        def list_resources(self):
            return ("USB0::scope::INSTR", "ASRL3::INSTR")

        def open_resource(self, name: str, **kwargs):
            assert name == "USB0::scope::INSTR"

            class Instrument:
                timeout = 0
                read_termination = None
                write_termination = None

                def query(self, command: str) -> str:
                    return "TEKTRONIX,DPO2012B,C010423,1.0"

                def close(self) -> None:
                    pass

            return Instrument()

    backend = VisaBackend()
    backend._resource_manager = Manager()
    resources = backend.list_resources(probe=True)
    assert resources[0].idn is not None
    assert resources[1].idn is None


def test_connect_rejects_non_dpo() -> None:
    class Instrument:
        timeout = 0
        read_termination = None
        write_termination = None
        query_delay = 0

        def query(self, command: str) -> str:
            return "OTHER,DEVICE,1,1"

        def close(self) -> None:
            pass

    class Manager:
        def open_resource(self, *args, **kwargs):
            return Instrument()

    backend = VisaBackend()
    backend._resource_manager = Manager()
    with pytest.raises(ScopeError, match="not a Tektronix DPO2012B"):
        backend.connect("USB0::x::INSTR")
