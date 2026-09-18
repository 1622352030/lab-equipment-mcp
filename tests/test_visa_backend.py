import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType, SessionConfig
from lab_equipment_mcp.core.transports.visa import VisaBackend, VisaResource
from lab_equipment_mcp.devices.tektronix.dpo2012b import DPO2012B


def test_dpo_detection_by_identity() -> None:
    backend = VisaBackend()
    backend.list_resources = lambda **kwargs: [
        VisaResource(
            "USB0::x::INSTR",
            "USB0",
            InterfaceType.USBTMC,
            idn="TEKTRONIX,DPO2012B,SERIAL,1.0",
        ),
        VisaResource(
            "USB0::y::INSTR", "USB0", InterfaceType.USBTMC, idn="OTHER,DEVICE,1,1"
        ),
    ]
    matches = DPO2012B(backend).find_resources()
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
                    return "TEKTRONIX,DPO2012B,SERIAL,1.0"

                def close(self) -> None:
                    pass

            return Instrument()

    backend = VisaBackend()
    backend._resource_manager = Manager()
    resources = backend.list_resources(probe=True)
    assert resources[0].idn is not None
    assert resources[0].interface_type is InterfaceType.USBTMC
    assert resources[1].idn is None
    assert resources[1].interface_type is InterfaceType.RS232


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
        DPO2012B(backend).connect("USB0::x::INSTR")


def test_serial_session_config_is_applied() -> None:
    class Instrument:
        timeout = 0
        read_termination = None
        write_termination = None
        query_delay = 0
        baud_rate = 0
        data_bits = 0
        stop_bits = 0
        parity = ""
        flow_control = ""

        def query(self, command: str) -> str:
            return "VENDOR,MODEL,SERIAL,1.0"

    class Manager:
        def open_resource(self, *args, **kwargs):
            return Instrument()

    backend = VisaBackend()
    backend._resource_manager = Manager()
    backend.connect(
        "ASRL3::INSTR",
        session_config=SessionConfig(
            read_termination="\r\n",
            write_termination="\r",
            baud_rate=9600,
            data_bits=8,
            stop_bits=1,
            parity="none",
            flow_control="none",
        ),
    )

    instrument = backend.instrument()
    assert instrument.read_termination == "\r\n"
    assert instrument.write_termination == "\r"
    assert instrument.baud_rate == 9600
    assert instrument.data_bits == 8
    assert int(instrument.stop_bits) == 10
    assert int(instrument.parity) == 0
    assert instrument.flow_control == 0


def test_binary_query_temporarily_disables_text_read_termination() -> None:
    class Instrument:
        read_termination = "\n"

        def write(self, command: str) -> None:
            assert command == "CURVE?"
            assert self.read_termination is None

        def read_raw(self) -> bytes:
            assert self.read_termination is None
            return b"#14\x01\n\x02\x03"

    backend = VisaBackend()
    backend._instrument = Instrument()
    backend._resource_name = "USB0::scope::INSTR"

    assert backend.query_raw("CURVE?") == b"#14\x01\n\x02\x03"
    assert backend.instrument().read_termination == "\n"


def test_binary_query_passes_an_explicit_size_only_when_asked() -> None:
    class Instrument:
        read_termination = "\n"

        def __init__(self) -> None:
            self.sizes: list[int | None] = []

        def write(self, command: str) -> None:
            return None

        def read_raw(self, size=None) -> bytes:
            self.sizes.append(size)
            return b"#14ABCD"

    instrument = Instrument()
    backend = VisaBackend()
    backend._instrument = instrument
    backend._resource_name = "USB0::scope::INSTR"

    backend.query_raw("CURVE?")
    backend.query_raw("CURVE?", size=65536)
    assert instrument.sizes == [None, 65536]


def test_binary_query_reads_a_socket_block_in_small_steps() -> None:
    class Instrument:
        read_termination = "\n"

        def __init__(self) -> None:
            self.sizes: list[int | None] = []

        def write(self, command: str) -> None:
            assert command == "WVDT? USER,lanchk"
            # A raw socket keeps the terminator: it is the only end-of-step signal VISA has.
            assert self.read_termination == "\n"

        def read_raw(self, size=None) -> bytes:
            self.sizes.append(size)
            if len(self.sizes) == 1:
                return b"A" * 4096
            return b"tail\n"

    instrument = Instrument()
    backend = VisaBackend()
    backend._instrument = instrument
    backend._resource_name = "TCPIP0::10.11.9.230::5025::SOCKET"

    payload = backend.query_raw("WVDT? USER,lanchk")
    assert payload == b"A" * 4096 + b"tail\n"
    assert instrument.sizes == [4096, 4096]
    assert backend.instrument().read_termination == "\n"


def test_socket_block_read_honours_the_size_limit() -> None:
    class Instrument:
        read_termination = "\n"

        def write(self, command: str) -> None:
            return None

        def read_raw(self, size=None) -> bytes:
            return b"B" * int(size)

    backend = VisaBackend()
    backend._instrument = Instrument()
    backend._resource_name = "TCPIP0::10.11.9.230::5025::SOCKET"

    assert len(backend.query_raw("X?", size=8192)) == 8192
