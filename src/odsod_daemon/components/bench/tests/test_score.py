from odsod_daemon.components.bench.score import (
    glossary_hits,
    normalize,
    percentile,
    word_error_rate,
)


def test_normalization_keeps_swedish_letters():
    assert normalize("  Ångström, ÄR  en-Ö! ") == "ångström är en-ö"
    assert normalize("NFC: e\u0301") == "nfc é"
    assert normalize("it's a test") == "it's a test"


def test_word_error_rate_on_known_pairs():
    references = ["hej på dig", "det är bra"]
    hypotheses = ["hej på dig", "det är dåligt"]
    assert word_error_rate(references, hypotheses) == 1 / 6
    assert word_error_rate([], []) is None
    assert word_error_rate(["bra"], ["bra!"]) == 0.0


def test_glossary_hits_count_reference_terms():
    references = ["Vi möter Ångström i Göteborg", "Och Ångström igen"]
    outputs = ["Vi möter Ångström i Göteborg", "Och Angstrom igen"]
    assert glossary_hits(references, outputs, ["Ångström", "Göteborg"]) == (2, 3)
    assert glossary_hits(references, outputs, []) == (0, 0)


def test_latency_percentiles():
    values = [100, 200, 300, 400]
    assert percentile(values, 0.5) == 200
    assert percentile(values, 0.95) == 400
    assert percentile([], 0.5) is None


def test_glossary_hits_match_whole_words_only():
    references = ["I said we are going on a sprint", "We use uv and go"]
    outputs = ["I said we are going on a sprint", "We use uv and Go"]
    assert glossary_hits(references, outputs, ["ai", "go", "pr", "uv"]) == (2, 2)
    assert glossary_hits(["Use Claude Code"], ["use claude code"], ["Claude Code"]) == (
        1,
        1,
    )
