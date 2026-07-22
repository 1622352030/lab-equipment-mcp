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
    assert "SDG1062X" in devices[3]["model"]
    assert {item["interface_type"] for item in devices[3]["interfaces"]} == {
        "usbtmc",
        "lan-vxi11",
        "lan-socket",
        "gpib",
    }
