import logging

from odsod_daemon.components.shortcuts import contract, keys
from odsod_daemon.components.shortcuts.contract import Shortcut
from odsod_daemon.components.shortcuts.kglobalaccel import (
    FakeKGlobalAccel,
    configure,
    stale_names,
)


def shortcut(name: str, key: str, kind: str = "command") -> Shortcut:
    return Shortcut.model_validate(
        {"actionId": ["kwin", name, "KWin", ""], "key": key, "kind": kind}
    )


def test_stale_names_keep_listed_and_foreign_actions():
    current = ["[odsod] old", "[odsod] terminal", "odsod-legacy", "Window Close"]
    assert stale_names(current, ["[odsod] terminal", "Window Close"]) == [
        "[odsod] old",
        "odsod-legacy",
    ]


async def test_configure_binds_each_chord_and_clears_a_kde_default():
    default = ("kwin", "Show Desktop", "KWin", "Peek at Desktop")
    fake = FakeKGlobalAccel(bindings={default: [keys.parse("Meta+D")]})
    shortcuts = contract.load().shortcuts

    summary = await configure(fake, shortcuts)

    assert summary.bound == len(shortcuts)
    assert summary.conflicts == 1
    assert fake.bindings[default] == []
    for item in shortcuts:
        assert fake.bindings[tuple(item.action_id)] == [keys.parse(item.key)]
        owners = [
            a for a, codes in fake.bindings.items() if keys.parse(item.key) in codes
        ]
        assert owners == [tuple(item.action_id)]


async def test_configure_unregisters_an_action_missing_from_the_list():
    old = ("kwin", "[odsod] recorder-note", "KWin", "")
    fake = FakeKGlobalAccel(bindings={old: [keys.parse("Meta+W")]})

    summary = await configure(fake, [shortcut("[odsod] note", "Meta+W")])

    assert summary.removed == 1
    assert ("unregister", "kwin", "[odsod] recorder-note") in fake.calls
    assert old not in fake.bindings


async def test_configure_rebinds_the_same_action_with_no_conflict():
    item = shortcut("[odsod] run", "Meta+R")
    fake = FakeKGlobalAccel(bindings={tuple(item.action_id): [keys.parse("Meta+R")]})

    summary = await configure(fake, [item])

    assert (summary.bound, summary.conflicts, summary.removed) == (1, 0, 0)


async def test_configure_logs_a_failed_bind_and_goes_on(caplog):
    fake = FakeKGlobalAccel(fail_on={"[odsod] a"})
    items = [shortcut("[odsod] a", "Meta+A"), shortcut("[odsod] b", "Meta+B")]

    with caplog.at_level(logging.INFO):
        summary = await configure(fake, items)

    assert (summary.bound, summary.failed) == (1, 1)
    assert ("kwin", "[odsod] b", "KWin", "") in fake.bindings
    assert any(
        "[odsod] a" in r.message and "NoSuchAction" in r.message for r in caplog.records
    )
    assert "bound 1, removed 0, conflicts cleared 0, failed 1" in caplog.text
