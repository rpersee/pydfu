"""
A wrapper around dfu-util cli tool with a fluent interface.

See http://dfu-util.sourceforge.net/dfu-util.1.html for documentation.
"""

from __future__ import annotations

import re
import subprocess
from abc import ABCMeta, abstractmethod
from collections.abc import Generator


class AbstractRequest(metaclass=ABCMeta):
    @property
    @abstractmethod
    def command(self) -> list:
        return NotImplemented

    @staticmethod
    def run(command: list[str]) -> Generator[str]:
        with subprocess.Popen(command,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              encoding="utf-8",
                              bufsize=1) as process:
            for line in process.stdout:
                yield line

            return_code = process.poll()

            # stderr = process.stderr.read()
            # if stderr:  # dfu-util returns a zero exit status even when stderr is not empty
            #     raise subprocess.CalledProcessError(return_code, process.args, process.stdout, process.stderr)

    @staticmethod
    def parse(output: Generator[str]) -> Generator:
        skip = 7
        for line in output:
            if skip > 0:
                skip -= 1
                continue

            yield line

    def exec(self) -> Generator:
        output = self.run(self.command)
        yield from self.parse(output)


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
        self._command.extend(("-i", str(intf)))
        return self

    def alt_setting(self, alt: str | int) -> Request:
        self._command.extend(("-a", str(alt)))
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
        self._command.extend(("-t", str(size)))
        return self

    def upload_size(self, size: int) -> FileRequest:
        self._command.extend(("-Z", str(size)))
        return self

    def dfuse_address(self, address, length=None, modifiers=None) -> FileRequest:
        dfuse = [address, ]

        if length is not None:
            assert re.match("0x[0-9a-f]", length, re.IGNORECASE)
            dfuse.append(length)

        if modifiers is not None:
            options = {
                'force',  # You really know what you are doing!
                'leave',  # Leave DFU mode (jump to application)
                'mass-erase',  # Erase the whole device (requires "force")
                'unprotect',  # Erase read protected device (requires "force")
                'will-reset'  # Expect device to reset (e.g. option bytes write)
            }
            assert all(mod in options for mod in modifiers)
            dfuse.extend(modifiers)

        self._command.extend(("-s", ':'.join(dfuse)))
        return self


class EnumRequest(Request):
    @staticmethod
    def parse_mapping(descriptor: str) -> dict:
        """Parse alternate setting memory mapping descriptor.
        See: [UM0290 page 31](https://www.st.com/content/ccc/resource/technical/document/user_manual/cc/6d/c3/43/ea/29/4b/eb/CD00135281.pdf/files/CD00135281.pdf/jcr:content/translations/en.CD00135281.pdf)

        :param descriptor: string descriptor
        :return: the parsed descriptor
        """

        name, *desc = descriptor.split('/')
        parsed = {"name": name[1:].strip(), "sectors": list()}

        for address, sectors in zip(desc[0::2], desc[1::2]):
            memory = {"address": address, "mapping": list()}

            for sector in sectors.split(','):
                number, specs = sector.split('*')

                number = int(number)  # number of sectors
                size = int(specs[:-2])

                multiplier = specs[-2]
                assert multiplier in (' ', 'B', 'K', 'M')

                permissions = specs[-1]
                assert permissions in (
                    'a',  # readable
                    'b',  # erasable
                    'c',  # readable & erasable
                    'd',  # writable
                    'e',  # readable & writable
                    'f',  # erasable & writable
                    'g',  # readable, erasable & writable
                )

                memory["mapping"].append(
                    {"number": number, "size": size, "multiplier": multiplier, "permissions": permissions}
                )

            parsed["sectors"].append(memory)

        return parsed

    @staticmethod
    def parser(output: Generator[str]) -> Generator[dict]:
        pattern = re.compile(r"(?P<msg>.*?): \[(?P<vid>.*):(?P<pid>.*)\] (?P<prop>.*)")
        for line in output:
            match = pattern.match(line)
            if not match:
                continue

            # generic parsing
            parsed = match.groupdict()
            for group in parsed.pop('prop').split(', '):
                key, value = group.split('=')
                parsed[key] = value.strip('"') if '"' in value else int(value)

            # parsing memory mapping descriptor
            alt_setting = EnumRequest.parse_mapping(parsed.pop("name"))
            alt_setting["id"] = parsed.pop("alt")
            parsed["alt"] = alt_setting

            yield parsed

    @staticmethod
    def parse(output: Generator[str]) -> Generator[dict]:
        devices = dict()

        # grouping by serial number
        for parsed in EnumRequest.parser(output):
            serial = parsed["serial"]
            if serial not in devices:
                devices[serial] = parsed
                devices[serial]["alt"] = [parsed["alt"], ]
            else:
                for key in ("vid", "pid", "ver", "devnum", "cfg", "intf", "path"):
                    assert parsed[key] == devices[serial][key]
                devices[serial]["alt"].append(parsed["alt"])

        for device in devices.values():
            # sorting on alternate setting id
            device["alt"].sort(key=lambda dev: dev["id"])
            yield device


def upload(file: str) -> FileRequest:
    """Read device memory into a file.

    :param file: Target file to write into.
    """

    return FileRequest("-U", file)


def download(file: str) -> FileRequest:
    """Flash a file to the device memory.

    :param file: A .dfu (special DfuSe format) or .bin (binary) file to flash.
    """

    return FileRequest("-D", file)


def enum() -> Request:
    """Enumerates the currently attached DFU-capable USB devices."""

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
Test Layout: [0123:abcd] ver=1800, devnum=32, cfg=2, intf=1, alt=3, name="@Not contiguous layout/0xF000/1*4Ka/0xE000/1*4Kg/0x8000/2*24Kg", serial="3262355B3231"
'''
    print(list(r.exec()))

    for i, line in enumerate(
            download("/home/synchrotron-soleil.fr/persee/Downloads/binaries/blink_rate.NUCLEO_F401RE.bin")
            .alt_setting("0")
            .dfuse_address("0x08000000")
            .exec()
    ):
        print(i, line)
