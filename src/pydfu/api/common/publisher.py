import asyncio
import warnings
from functools import partial

from pyudev import Context, Monitor, Device

from .singleton import SingletonMeta

context = Context()

# https://pyudev.readthedocs.io/en/latest/guide.html#synchronous-monitoring
monitor = Monitor.from_netlink(context)
monitor.filter_by('usb')


# noinspection PyPep8Naming
def vendor_is_ST(dev: Device) -> bool:
    return dev.attributes.get("idVendor") == b'0483'


class Publisher(metaclass=SingletonMeta):
    def __init__(self):
        # self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self.subscriptions: set[asyncio.Queue] = set()

    async def subscribe(self, queue: asyncio.Queue):
        self.subscriptions.add(queue)

    async def unsubscribe(self, queue: asyncio.Queue):
        self.subscriptions.remove(queue)

    async def run(self):
        loop = asyncio.get_event_loop()

        try:
            while True:
                # do not wait indefinitely to allow for shutdown / hot reload
                device = await loop.run_in_executor(executor=None, func=partial(monitor.poll, 3))  # Awaitable[Device]
                if device is None:
                    # go to next iteration if no device was retrieved
                    continue

                if not vendor_is_ST(device):
                    # ignore non ST devices
                    continue

                for queue in self.subscriptions:
                    await queue.put(device)

        except asyncio.CancelledError as e:
            warnings.warn(f"Received cancelled error.")
            raise e


publisher = Publisher()
