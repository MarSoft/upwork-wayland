#!/usr/bin/env python
# Bridge script between Gnome Screenshot API and wlroots-based Wayland composer
# Usage:
# Run this script in the background.
# Make sure it will connect to the same DBus session daemon as Upwork does,
# i.e. they should get the same value in DBUS_SESSION_BUS_ADDRESS env var.
#
# Dependencies:
# - python 3.5+
# - dbus-next python package (pip install dbus-next)
# - grim (https://github.com/emersion/grim)

import asyncio
import datetime as dt
import subprocess

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next import Variant, BusType, DBusError


class ScreenshotInterface(ServiceInterface):
    def __init__(self):
        super().__init__('org.gnome.Shell.Screenshot')

    @method()
    def Screenshot(self, include_cursor: 'b', flash: 'b', filename: 's') -> 'bs':
        print('Got Screenshot call', include_cursor, flash, filename)
        subprocess.run(['grim', *(['-c'] if include_cursor else []), filename])
        return [True, filename]

    @method()
    def ScreenshotWindow(self, include_frame: 'b', include_cursor: 'b', flash: 'b', filename: 's') -> 'bs':
        print('Got Window call', include_frame, include_cursor, flash, filename)
        # TODO capture current window somehow
        subprocess.run(['grim', *(['-c'] if include_cursor else []), filename])
        return [True, filename]

    @method()
    def ScreenshotArea(self, x: 'i', y: 'y', width: 'i', height: 'i', flash: 'b', filename: 's') -> 'bs':
        print('Got Area call', (x, y, width, height), flash, filename)
        subprocess.run(['grim', '-g', f'{x},{y} {width}x{height}', filename])
        return [True, filename]


class IdleTime(ServiceInterface):
    def __init__(self):
        super().__init__('org.gnome.Mutter.IdleMonitor')
        self.last_active = dt.datetime.utcnow()

    async def start(self):
        self.monitor = await asyncio.create_subprocess_exec(
            'swayidle',
            '-w', 'timeout', '1', 'echo timeout', 'resume', 'echo resume',
            stdout=subprocess.PIPE,
        )
        self.worker = asyncio.create_task(self.run())

    async def run(self):
        async for line in self.monitor.stdout:
            line = line.decode().strip()
            if line == 'timeout':
                pass  # do nothing
            elif line == 'resume':
                self.last_active = dt.datetime.utcnow()
            else:
                print('Got unknown line', line)

    @method()
    def GetIdletime(self) -> 't':
        # What unit do we want?
        delta = dt.datetime.utcnow() - self.last_active
        print('Asked idletime. It is', delta)
        return round(delta.total_seconds())


async def main():
    bus = MessageBus() #bus_type=BusType.SYSTEM)
    await bus.connect()
    bus.export('/org/gnome/Shell/Screenshot', ScreenshotInterface())
    idle = IdleTime()
    await idle.start()
    bus.export('/org/gnome/Mutter/IdleMonitor/Core', idle)
    # Now we are ready to handle messages!
    await bus.request_name('org.gnome.Shell.Screenshot')
    await bus.request_name('org.gnome.Mutter.IdleMonitor')

    print('Started!')

    # run forever (FIXME is it a good way?)
    #await asyncio.get_event_loop().create_future()
    await idle.worker


if __name__ == '__main__':
    asyncio.run(main())
