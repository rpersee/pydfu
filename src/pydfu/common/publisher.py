import asyncio

from threading import Lock
from pyudev import Context, Monitor, Device, MonitorObserver


class Publisher:
    lock = Lock()
    # subscriptions set is accessed from multiple threads
    subscriptions: set[asyncio.Queue]

    context: Context
    monitor: Monitor
    observer: MonitorObserver

    # noinspection PyPep8Naming
    @staticmethod
    def vendor_is_ST(dev: Device) -> bool:
        return dev.attributes.get("idVendor") == b'0483'

    @staticmethod
    def publish_event(action, device):
        if action in ('bind', 'unbind'):
            return

        if not Publisher.vendor_is_ST(device):
            pass

        with Publisher.lock:
            for queue in Publisher.subscriptions:
                queue.put_nowait(device)

    @classmethod
    async def start(cls):
        with cls.lock:
            cls.subscriptions = set()

        cls.context = Context()

        # https://pyudev.readthedocs.io/en/latest/guide.html#synchronous-monitoring
        cls.monitor = Monitor.from_netlink(cls.context)
        cls.monitor.filter_by('usb')

        cls.observer = MonitorObserver(cls.monitor, cls.publish_event)
        cls.observer.start()

    @classmethod
    async def stop(cls):
        cls.observer.stop()
        del cls.monitor
        del cls.context
        with cls.lock:
            del cls.subscriptions

    @classmethod
    async def subscribe(cls, queue: asyncio.Queue):
        with cls.lock:
            cls.subscriptions.add(queue)

    @classmethod
    async def unsubscribe(cls, queue: asyncio.Queue):
        with cls.lock:
            cls.subscriptions.remove(queue)
