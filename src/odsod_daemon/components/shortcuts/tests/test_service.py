import asyncio
import logging
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Annotated

import pytest
from dbus_fast import DBusError, Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import DBusSignature
from dbus_fast.service import ServiceInterface, dbus_method

from odsod_daemon.components.shortcuts import contract, keys
from odsod_daemon.components.shortcuts.contract import Shortcut
from odsod_daemon.components.shortcuts.kglobalaccel import (
    DBusKGlobalAccel,
    FakeKGlobalAccel,
)
from odsod_daemon.components.shortcuts.service import UNKNOWN, Shortcuts


class Launches:
    def __init__(self) -> None:
        self.names: list[str] = []

    async def __call__(self, shortcut: Shortcut) -> None:
        self.names.append(shortcut.name)


def service(accel=None) -> tuple[Shortcuts, FakeKGlobalAccel, Launches]:
    accel = accel or FakeKGlobalAccel()
    launches = Launches()
    return Shortcuts(contract.load().shortcuts, accel, launches), accel, launches


async def test_run_launches_the_listed_shortcut():
    shortcuts, _, launches = service()
    shortcuts.Run("[odsod] terminal")
    await asyncio.sleep(0)
    assert launches.names == ["[odsod] terminal"]


@pytest.mark.parametrize("name", ["[odsod] nope", "Window Close", "[odsod] debug"])
async def test_run_refuses_a_name_that_is_not_a_listed_command(name, caplog):
    shortcuts, _, launches = service()
    with pytest.raises(DBusError) as error:
        shortcuts.Run(name)
    assert error.value.type == UNKNOWN
    await asyncio.sleep(0)
    assert launches.names == []
    assert any("refused" in r.getMessage() for r in caplog.records)


def test_log_joins_the_script_values(caplog):
    shortcuts, _, _ = service()
    with caplog.at_level(logging.INFO):
        shortcuts.Log('["handling shortcut", "[odsod] meet"]')
        shortcuts.Log("not json")
    assert "script: handling shortcut [odsod] meet" in caplog.text
    assert "script: not json" in caplog.text


# A private bus: no service dirs, so nothing is activated, and the live
# session bus is never used.
BUS_CONFIG = """<busconfig>
  <type>session</type>
  <listen>unix:dir={dir}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*"/>
    <allow own="*"/>
    <allow receive_sender="*"/>
  </policy>
</busconfig>
"""


@pytest.fixture
def private_bus(tmp_path: Path) -> Iterator[str]:
    daemon = shutil.which("dbus-daemon")
    if daemon is None:
        pytest.skip("dbus-daemon not installed")
    config = tmp_path / "bus.conf"
    config.write_text(BUS_CONFIG.format(dir=tmp_path))
    process = subprocess.Popen(
        [daemon, f"--config-file={config}", "--nofork", "--print-address"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    address = process.stdout.readline().strip()
    yield address
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture
async def buses(private_bus: str) -> AsyncIterator[tuple[MessageBus, MessageBus]]:
    server = await MessageBus(bus_address=private_bus).connect()
    client = await MessageBus(bus_address=private_bus).connect()
    yield server, client
    server.disconnect()
    client.disconnect()


async def call(bus: MessageBus, member: str, signature: str = "", body=None):
    return await bus.call(
        Message(
            destination=contract.BUS_NAME,
            path=contract.OBJECT_PATH,
            interface=contract.INTERFACE,
            member=member,
            signature=signature,
            body=body or [],
        )
    )


@pytest.mark.looptime(False)
async def test_interface_on_a_private_bus(buses):
    server, client = buses
    shortcuts, accel, launches = service()
    server.export(contract.OBJECT_PATH, shortcuts)
    await server.request_name(contract.BUS_NAME)

    reply = await call(client, "Run", "s", ["[odsod] meet"])
    assert reply is not None and reply.message_type == MessageType.METHOD_RETURN
    refused = await call(client, "Run", "s", ["rm -rf"])
    assert refused is not None and refused.error_name == UNKNOWN
    configured = await call(client, "Configure")
    assert configured is not None
    assert configured.message_type == MessageType.METHOD_RETURN

    await asyncio.sleep(0)
    assert launches.names == ["[odsod] meet"]
    assert len(accel.bindings) == len(contract.load().shortcuts)


@pytest.mark.looptime(False)
async def test_dbus_kglobalaccel_client_signatures(buses):
    """The client talks to a fake org.kde.kglobalaccel on the private bus."""

    fake = FakeKGlobalAccel(
        bindings={("kwin", "[odsod] old", "KWin", ""): [keys.parse("Meta+Z")]}
    )

    class Accel(ServiceInterface):
        def __init__(self) -> None:
            super().__init__("org.kde.KGlobalAccel")

        @dbus_method()
        async def action(
            self, code: Annotated[int, DBusSignature("i")]
        ) -> Annotated[list[str], DBusSignature("as")]:
            return await fake.action(code)

        @dbus_method()
        async def setForeignShortcut(
            self,
            action_id: Annotated[list[str], DBusSignature("as")],
            codes: Annotated[list[int], DBusSignature("ai")],
        ):
            await fake.set_foreign_shortcut(action_id, codes)

        @dbus_method()
        async def unregister(
            self,
            component: Annotated[str, DBusSignature("s")],
            name: Annotated[str, DBusSignature("s")],
        ) -> Annotated[bool, DBusSignature("b")]:
            await fake.unregister(component, name)
            return True

    class Component(ServiceInterface):
        def __init__(self) -> None:
            super().__init__("org.kde.kglobalaccel.Component")

        @dbus_method()
        async def shortcutNames(self) -> Annotated[list[str], DBusSignature("as")]:
            return await fake.shortcut_names()

    server, client = buses
    server.export("/kglobalaccel", Accel())
    server.export("/component/kwin", Component())
    await server.request_name("org.kde.kglobalaccel")

    real = DBusKGlobalAccel(client)
    assert await real.shortcut_names() == ["[odsod] old"]
    await real.set_foreign_shortcut(["kwin", "[odsod] a", "KWin", ""], [1, 2])
    assert await real.action(1) == ["kwin", "[odsod] a", "KWin", ""]
    await real.unregister("kwin", "[odsod] old")
    assert ("kwin", "[odsod] old", "KWin", "") not in fake.bindings


@pytest.mark.looptime(False)
async def test_run_once_serves_on_the_session_bus_and_installs(
    private_bus, monkeypatch, caplog
):
    from odsod_daemon.components import shortcuts as component
    from odsod_daemon.components.shortcuts import kwin_install

    client = await MessageBus(bus_address=private_bus).connect()
    replies: list[MessageType] = []

    async def ensure(*, reload) -> bool:
        # The interface is up before the script loads and calls it.
        reply = await call(client, "Log", "s", ['["script up"]'])
        assert reply is not None
        replies.append(reply.message_type)
        return True

    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", private_bus)
    monkeypatch.setattr(kwin_install, "ensure", ensure)
    with caplog.at_level(logging.INFO):
        await component.run(None, once=True)
    client.disconnect()

    assert replies == [MessageType.METHOD_RETURN]
    assert "script: script up" in caplog.text
