from odsod_daemon.components.shortcuts import contract, keys


def test_list_validates_with_unique_names():
    shortcuts = contract.load().shortcuts
    names = [shortcut.name for shortcut in shortcuts]
    assert len(names) == len(set(names))
    assert len({shortcut.key.lower() for shortcut in shortcuts}) == len(shortcuts)


def test_every_key_parses():
    codes = [keys.parse(shortcut.key) for shortcut in contract.load().shortcuts]
    assert len(set(codes)) == len(codes)


def test_own_actions_are_prefixed_and_builtins_are_not():
    for shortcut in contract.load().shortcuts:
        assert shortcut.action_id[0] == "kwin"
        assert shortcut.action_id[2] == "KWin"
        own = shortcut.name.startswith("[odsod] ")
        assert own == (shortcut.kind != "builtin"), shortcut.name


def test_apps_have_a_window_match_and_commands_have_argv():
    for shortcut in contract.load().shortcuts:
        if shortcut.kind in ("app", "command"):
            assert shortcut.command, shortcut.name
        if shortcut.kind == "app":
            assert (
                shortcut.resource_class
                or shortcut.resource_class_includes
                or shortcut.resource_name
            ), shortcut.name


def test_list_calls_no_old_recorder():
    for shortcut in contract.load().shortcuts:
        assert not any("recorder-note" in arg for arg in shortcut.command)
