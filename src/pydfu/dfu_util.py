"""
A wrapper around dfu-util cli tool with a fluent interface.

See http://dfu-util.sourceforge.net/dfu-util.1.html for documentation.
"""

from __future__ import annotations

import subprocess
from abc import ABCMeta, abstractmethod
import re
from collections.abc import Generator


class AbstractRequest(metaclass=ABCMeta):
    @property
    @abstractmethod
    def command(self) -> list:
        return NotImplemented

    @staticmethod
    def run(command: list[str]) -> str:
        process = subprocess.run(command, capture_output=True)
        if process.stderr:  # dfu-util returns a zero exit status even when stderr is not empty
            raise subprocess.CalledProcessError(process.returncode, process.args, process.stdout, process.stderr)
        return process.stdout.decode()

    @staticmethod
    def parse(output: str) -> Generator:
        for line in output.splitlines()[7:]:
            yield line

    def exec(self) -> list:
        output = self.run(self.command)
        parsed = list(self.parse(output))
        return parsed


class Request(AbstractRequest):
    id_pattern: str = r"([0-9a-f]+)?:([0-9a-f]+)?"

    def __init__(self, *args):
        self._command = ['dfu-util', ]
        self._command.extend(args)

    @property
    def command(self) -> list:
        return self._command

    def verbosity(self, level: int) -> Request:
        self._command.extend((['-v'] * min(level, 3)))
        return self

    def device(self, identifiers: str) -> Request:
        """Specify the device identifiers for run-time and DFU mode.

        :param identifiers: '<run-time IDs>,<DFU mode IDs>' with IDs ~ '<vendor ID>:<product ID>'
        """
        pattern = re.compile(rf"^(\*|-|{self.id_pattern})?(,(\*|-|{self.id_pattern})?)?$",
                             flags=re.IGNORECASE)
        assert (pattern.match(identifiers))

        self._command.extend(("-d", identifiers))
        return self

    def path(self, bus_port: str) -> Request:
        self._command.extend(("-p", bus_port))
        return self

    def config(self, cfg_nr: str) -> Request:
        self._command.extend(("-c", cfg_nr))
        return self

    def interface(self, intf: int) -> Request:
        self._command.extend(("-i", intf))
        return self

    def alt_setting(self, alt: str | int) -> Request:
        self._command.extend(("-a", alt))
        return self

    def serial(self, serial: str) -> Request:
        pattern = re.compile(rf"^{self.id_pattern}?(,{self.id_pattern}?)?",
                             flags=re.IGNORECASE)
        assert (pattern.match(serial))

        self._command.extend(("-S", serial))
        return self


class FileRequest(Request):
    def wait(self) -> FileRequest:
        self._command.append("-w")
        return self

    def reset(self) -> FileRequest:
        self._command.append("-R")
        return self

    def transfer_size(self, size: int) -> FileRequest:
        self._command.extend(("-t", size))
        return self

    def upload_size(self, size: int) -> FileRequest:
        self._command.extend(("-Z", size))
        return self

    def dfuse_address(self, address) -> FileRequest:
        self._command.extend(("-s", address))
        return self


class EnumRequest(Request):
    @staticmethod
    def parse(output: str) -> Generator[dict]:
        pattern = re.compile(r"(?P<msg>.*?): \[(?P<vid>.*):(?P<pid>.*)\] (?P<prop>.*)")
        for match in pattern.finditer(output):
            parsed = match.groupdict()
            for group in parsed.pop('prop').split(', '):
                key, value = group.split('=')
                parsed[key] = value.strip('"') if '"' in value else int(value)
            yield parsed


def upload(file: str) -> FileRequest:
    return FileRequest("-U", file)


def download(file: str) -> FileRequest:
    return FileRequest("-D", file)


def enum() -> Request:
    return EnumRequest("-l")


if __name__ == "__main__":
    assert (
            upload("test")
            .verbosity(2)
            .device("456d:389,*")
            .command[1:]
            == ['-U', 'test', '-v', '-v', '-d', '456d:389,*']
    )

    assert (
            enum()
            .verbosity(1)
            .interface(4)
            .command[1:]
            == ['-l', '-v', '-i', 4]
    )

    assert (
            download("aFile")
            .transfer_size(480)
            .serial(":564f")
            .command[1:]
            == ['-D', 'aFile', '-t', 480, '-S', ':564f']
    )

    # test `dfu-util --list`
    r = EnumRequest()
    r.run = lambda _: '''dfu-util 0.9

Copyright 2005-2009 Weston Schmidt, Harald Welte and OpenMoko Inc.
Copyright 2010-2016 Tormod Volden and Stefan Schmidt
This program is Free Software and has ABSOLUTELY NO WARRANTY
Please report bugs to http://sourceforge.net/p/dfu-util/tickets/

Found DFU: [0483:df11] ver=2200, devnum=7, cfg=1, intf=0, path="1-2", alt=3, name="@Device Feature/0xFFFF0000/01*004 e", serial="319235713237"
Found DFU: [0483:df11] ver=2200, devnum=7, cfg=1, intf=0, path="1-2", alt=2, name="@OTP Memory /0x1FFF7800/01*512 e,01*016 e", serial="319235713237"
Found DFU: [0483:df11] ver=2200, devnum=7, cfg=1, intf=0, path="1-2", alt=1, name="@Option Bytes  /0x1FFFC000/01*016 e", serial="319235713237"
Found DFU: [0483:df11] ver=2200, devnum=7, cfg=1, intf=0, path="1-2", alt=0, name="@Internal Flash  /0x08000000/04*016Kg,01*064Kg,03*128Kg", serial="319235713237"
'''
    print(r.exec())
