import pyudev
from . import dfu_util

context = pyudev.Context()

# https://pyudev.readthedocs.io/en/latest/guide.html#synchronous-monitoring
monitor = pyudev.Monitor.from_netlink(context)
monitor.filter_by('usb')


def vendor_is_ST(dev: pyudev.Device) -> bool:
    return dev.attributes.get("idVendor") == b'0483'


try:
    for device in iter(monitor.poll, None):
        if vendor_is_ST(device):
            print(f"Detected ST device: {device}")
            if device.action == 'bind':
                print(dfu_util.enum().exec())
except KeyboardInterrupt:
    print("bye...")
