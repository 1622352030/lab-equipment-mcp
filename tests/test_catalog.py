from lab_equipment_mcp.devices.catalog import list_device_profiles


def test_catalog_exposes_device_interfaces() -> None:
    devices = list_device_profiles()
    assert devices[0]["vendor"] == "Tektronix"
    assert devices[0]["model"] == "DPO2012B"
    assert devices[0]["interfaces"][0]["interface_type"] == "usbtmc"
    assert devices[0]["interfaces"][0]["required_drivers"]
    assert devices[1]["vendor"] == "GW Instek"
    assert devices[1]["model"] == "AFG-2125"
    assert devices[1]["interfaces"][0]["interface_type"] == "rs232"
    assert devices[2]["vendor"] == "Agilent/Keysight"
    assert devices[2]["model"] == "33500B Series"
    assert {item["interface_type"] for item in devices[2]["interfaces"]} == {
        "usbtmc",
        "lan-vxi11",
        "lan-socket",
        "gpib",
    }
    assert devices[3]["vendor"] == "Siglent"
    assert devices[4]["vendor"] == "Agilent/Keysight"
    assert devices[4]["model"] == "DSO-X 2012A"
    assert {item["interface_type"] for item in devices[4]["interfaces"]} == {
        "usbtmc",
        "lan-vxi11",
        "gpib",
    }
    assert "SDG1062X" in devices[3]["model"]
    assert {item["interface_type"] for item in devices[3]["interfaces"]} == {
        "usbtmc",
        "lan-vxi11",
        "lan-socket",
        "gpib",
    }
    assert devices[5]["vendor"] == "Maynuo"
    assert devices[5]["model"] == "M8811"
    assert {item["interface_type"] for item in devices[5]["interfaces"]} == {
        "ttl-serial",
        "rs232",
        "rs485",
    }
    assert devices[6]["vendor"] == "Fluke"
    assert devices[6]["model"] == "8808A"
    assert {item["interface_type"] for item in devices[6]["interfaces"]} == {"rs232"}
    assert devices[6]["interfaces"][0]["connection_notes"]
    assert devices[7]["vendor"] == "ITECH"
    assert devices[7]["model"] == "IT7321"
    assert {item["interface_type"] for item in devices[7]["interfaces"]} == {"lan-socket"}
    assert devices[8]["vendor"] == "ITECH"
    assert devices[8]["model"] == "IT8813"
    # USB Type-B is USBTMC on this model, and RS-232 is declared separately with its own
    # front-panel-only session settings rather than being hidden inside the USB entry.
    assert {item["interface_type"] for item in devices[8]["interfaces"]} == {"usbtmc", "rs232"}
    assert devices[8]["interfaces"][0]["connection_notes"]
    assert len(devices) == 9
