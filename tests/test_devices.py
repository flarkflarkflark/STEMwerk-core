from stemwerk_core.devices import get_available_devices, select_device


def test_get_available_devices_cpu_only_safe() -> None:
    devices = get_available_devices()
    assert isinstance(devices, list)
    ids = {device["id"] for device in devices}
    assert "auto" in ids
    assert "cpu" in ids
    for device in devices:
        assert "id" in device
        assert "name" in device
        assert "type" in device


def test_select_device_default() -> None:
    device_id, device_name = select_device("auto")
    assert isinstance(device_id, str)
    assert isinstance(device_name, str)
