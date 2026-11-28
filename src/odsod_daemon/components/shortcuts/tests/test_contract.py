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


def _run_note(tmp_path, kdialog_script):
    import os
    import subprocess

    note = next(s for s in contract.load().shortcuts if s.name == "[odsod] note")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "kdialog").write_text("#!/bin/sh\n" + kdialog_script)
    (bin_dir / "odsodctl").write_text(f'#!/bin/sh\ncat > "{tmp_path}/note.txt"\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    result = subprocess.run(note.command, env=env, check=False)
    sent = tmp_path / "note.txt"
    return result.returncode, sent.read_text() if sent.exists() else None


def test_note_cancel_is_not_a_failure(tmp_path):
    assert _run_note(tmp_path, "exit 1\n") == (0, None)


def test_note_empty_is_not_a_failure(tmp_path):
    assert _run_note(tmp_path, "echo\n") == (0, None)


def test_note_sends_the_text(tmp_path):
    assert _run_note(tmp_path, "echo hello\n") == (0, "hello")
