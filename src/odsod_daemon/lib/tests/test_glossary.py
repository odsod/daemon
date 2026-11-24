import pytest

from odsod_daemon.lib import glossary, paths


@pytest.fixture
def roots(tmp_path):
    return paths.Roots(state=tmp_path / "s", run=tmp_path / "r", config=tmp_path)


def test_yaml_entries_keep_order_and_extra_keys(roots):
    (roots.config / "glossary.yaml").write_text(
        "- term: Acme\n  note: company\n  heard_as: [Akme]\n  owner: agents\n"
        "- term: Ada\n"
    )
    entries = glossary.load(roots)
    assert glossary.terms(entries) == ["Acme", "Ada"]
    assert entries[0].heard_as == ["Akme"]
    assert entries[0].model_extra == {"owner": "agents"}


def test_no_file_is_empty(roots):
    assert glossary.load(roots) == []


@pytest.mark.parametrize("text", ["term: Acme\n", "- note: no term\n", "- [\n"])
def test_bad_yaml_raises(roots, text):
    (roots.config / "glossary.yaml").write_text(text)
    with pytest.raises(ValueError, match=r"glossary\.yaml"):
        glossary.load(roots)


def test_relevant_matches_terms_and_misheard_forms_as_words():
    entries = [
        glossary.Entry(term="Acme", note="company", heard_as=["Akme"]),
        glossary.Entry(term="Acmebot", note="AI agent made by Acme"),
        glossary.Entry(term="Ada"),
    ]
    found = glossary.relevant(entries, "we told akme about it")
    assert glossary.terms(found) == ["Acme"]
    found = glossary.relevant(entries, "Ask Acmebot.")
    assert glossary.terms(found) == ["Acmebot"]
    assert glossary.relevant(entries, "Adam said so") == []


def test_hints_render_note_and_misheard_forms():
    entries = [
        glossary.Entry(term="Acme", note="company", heard_as=["Akme", "Ackme"]),
        glossary.Entry(term="Ada"),
    ]
    assert glossary.hints(entries) == (
        "- Acme: company (can be misheard as: Akme, Ackme)\n- Ada"
    )
