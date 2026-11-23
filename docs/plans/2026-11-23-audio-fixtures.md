# Plan: audio fixtures

- Status: Draft
- Depends on: none
- Design: [ADR-0010](../adr/0010-contracts-and-runtime.md) (Test
  fixtures), [ADR-0012](../adr/0012-speech.md) (Build without hardware)

## Goal

- One shared set of short speech clips in `tests/testdata/audio/`, used by
  speech, transcript, bench and the system tests.
- Every file has a source and a license that allow it in a public repo.

## Scope

- In: public-domain or CC0 speech in Swedish and English, plus silence and
  noise made with `sox`. A `PROVENANCE.md` and a reference text per clip.
- Out: the owner's voice or real meetings (phase 3 adds real audio).
  Clips with a license that needs attribution in the code.

## Steps

1. Research, done by a web research worker (agy, Gemini 4 Hydrogen), not
   the implementing worker. It writes a report; steps 2 to 5 use it: find LibriVox recordings (public domain) or
   other CC0 speech:
   - 2 Swedish clips, 10 to 20 s each;
   - 2 English clips, 10 to 20 s each;
   - 1 clip with Swedish speech and English terms, if one exists; else
     note "not found";
   - for each: page URL, file URL, reader, book, license, date fetched,
     and the text read (from the book's public-domain text).
     Rules: fetch every cited URL with `defuddle parse <url> --md`. Drop a
     URL that fails. End the report with a References list.
2. Download into a new empty dir under `/tmp`. Never run anything from it.
3. Cut and convert with `ffmpeg`: 16 kHz, mono, s16le, at the sentence
   edges. Save as `.wav` and as raw `.pcm` only if the tests need raw.
4. Make with `sox`: 5 s of digital silence, 5 s of low room noise
   (pink noise at about -60 dBFS), 5 s of fan-like noise (brown noise at
   about -45 dBFS). Tests that need longer noise loop these.
5. Write `tests/testdata/audio/PROVENANCE.md`: one row per file with the
   fields of step 1, and `<name>.txt` with the reference text.

## Done when

```sh
du -cb tests/testdata/audio/* | tail -1        # at most 4,000,000 bytes
for f in tests/testdata/audio/*.wav; do soxi -r -c "$f"; done   # 16000, 1
for f in tests/testdata/audio/*.wav; do rg -q "$(basename "$f")" tests/testdata/audio/PROVENANCE.md || echo "no provenance: $f"; done
```

- The last loop prints nothing. Each speech clip has a `.txt` reference.

## Progress log

- 2026-11-23: Downloaded the four report audio URLs into a temp dir under `/tmp`. No downloaded file was run.
- 2026-11-23: Cut four speech clips at 16 kHz mono s16le; made 5 s silence and two noise files with `sox`. No `.pcm` because no test needs raw.
- 2026-11-23: Swedish+English clip: not found (per research report).
- 2026-11-23: Swedish clip 2: the first 3 min end at the start of the preamble. A 4 min whisper pass located the paragraph; cut 218.75-238.55 s and took the reference text from the 1940s official Swedish translation, matched to the whisper words.
- 2026-11-23: Wrote `PROVENANCE.md` and four `.txt` reference files. Done when: 2,516,446 bytes total; all WAVs 16000 Hz mono; provenance loop prints nothing.

## Decisions to confirm

- File names use `<lang>-<work>.wav`; rename them if the speech tests expect other names.
- Synthetic noise levels are RMS about -60 and -45 dBFS; `sox vol` was calibrated to RMS, not peak.
- Swedish clip 2 uses the third preamble paragraph (1940s official translation). The first 3 min only reach the start of the preamble.
