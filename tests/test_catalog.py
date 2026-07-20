from lab_equipment_mcp.devices.catalog import list_device_profiles


def test_catalog_exposes_device_interfaces() -> None:
    devices = list_device_profiles()
    assert devices[0]["vendor"] == "Tektronix"
    assert devices[0]["model"] == "DPO2012B"
    assert devices[0]["interfaces"][0]["interface_type"] == "usbtmc"
    assert devices[0]["interfaces"][0]["required_drivers"]
