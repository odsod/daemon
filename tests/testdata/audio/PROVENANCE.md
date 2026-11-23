# Audio fixture provenance

All speech files were downloaded on 2026-11-23, cut with `ffmpeg`, and
converted to 16 kHz, mono, 16-bit signed PCM WAV. The synthetic files were
made with `sox` on 2026-11-23. No downloaded file was executed.

## Speech

| File | Page URL | File URL | Reader | Book / work | License | Fetched | Passage | Text read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sv-udhr-article1.wav` | https://commons.wikimedia.org/wiki/File:Universal_Declaration_of_Human_Rights_-_swe_-_lr_-_Art1.ogg | https://upload.wikimedia.org/wikipedia/commons/9/94/Universal_Declaration_of_Human_Rights_-_swe_-_lr_-_Art1.ogg | Lars Rolander (LibriVox reader 2234) | *The Universal Declaration of Human Rights* (United Nations), Article 1 in Swedish | Public Domain (LibriVox; Wikimedia Commons upload 2014-01-06) | 2026-11-23 | 00:00.00-00:14.45 (whole file) | "Alla människor är födda fria och lika i värdighet och rättigheter. De har utrustats med förnuft och samvete och bör handla gentemot varandra i en anda av gemenskap." (`sv-udhr-article1.txt`) |
| `sv-udhr-preamble.wav` | https://commons.wikimedia.org/wiki/File:Universal_Declaration_of_Human_Rights_-_swe_-_adam.ogg | https://upload.wikimedia.org/wikipedia/commons/8/84/Universal_Declaration_of_Human_Rights_-_swe_-_adam.ogg | Adam (LibriVox reader 3103) | *The Universal Declaration of Human Rights* (United Nations), full Swedish reading | Public Domain (LibriVox; Wikimedia Commons upload 2013-12-01) | 2026-11-23 | 00:03:38.75-00:03:58.55 (from full reading) | "enär skapandet av en värld, där människorna åtnjuta yttrandefrihet, trosfrihet samt frihet från fruktan och nöd, kungjorts som folkens högsta strävan," (`sv-udhr-preamble.txt`) |
| `en-study-in-scarlet.wav` | https://commons.wikimedia.org/wiki/File:Studyinscarlet_01_doyle_read_by_david_clarke.ogg | https://upload.wikimedia.org/wikipedia/commons/9/9e/Studyinscarlet_01_doyle_read_by_david_clarke.ogg | David Clarke (LibriVox) | *A Study in Scarlet*, Part I, Chapter I, by Sir Arthur Conan Doyle (1887) | Public Domain (novel; recording CC0 1.0; Wikimedia Commons upload 2023-02-11) | 2026-11-23 | 00:00:26.276-00:00:44.690 | "In the year 1878 I took my degree of Doctor of Medicine of the University of London, and proceeded to Netley to go through the course prescribed for surgeons in the army. Having completed my studies there, I was duly attached to the Fifth Northumberland Fusiliers as Assistant Surgeon." (`en-study-in-scarlet.txt`) |
| `en-chinese-feet.wav` | https://commons.wikimedia.org/wiki/File:Chinese_Women%27s_Feet_by_Scientific_American_-_read_by_Availle_for_LibriVox%27s_Short_Nonfiction_Collection_Vol._023_(2011).ogg | https://upload.wikimedia.org/wikipedia/commons/3/38/Chinese_Women%27s_Feet_by_Scientific_American_-_read_by_Availle_for_LibriVox%27s_Short_Nonfiction_Collection_Vol._023_%282011%29.ogg | Availle (LibriVox) | "Chinese Women's Feet", *Scientific American*, Vol. XLIII, No. 25 (1880-12-18), in LibriVox *Short Nonfiction Collection Vol. 023* | Public Domain (LibriVox; source text published 1880; Wikimedia Commons upload 2018-01-06) | 2026-11-23 | 00:00:13.000-00:00:23.800 | "An American missionary, Miss Norwood, of Swatow, recently described in a Times paragraph, how the size of the foot is reduced in Chinese women." (`en-chinese-feet.txt`) |

### Swedish clip 2 note

The research report had no timestamps for the Adam reading. The first 3
minutes contain the LibriVox and booklet introduction; the UDHR preamble
starts at 179.98 s. A whisper verbose_json pass on the first 4 minutes
located the paragraph, and the reference text is the official 1940s
Swedish translation from
[Wikisource](https://sv.wikisource.org/wiki/FN:s_deklaration_om_de_m%C3%A4nskliga_r%C3%A4ttigheterna_(1940-talets_%C3%B6vers%C3%A4ttning)),
matched to the whisper words.

## Synthetic

| File | Source | License | Made | Command |
| --- | --- | --- | --- | --- |
| `silence.wav` | 5 s of digital silence (all samples zero) | CC0 (generated) | 2026-11-23 | `sox -n -r 16000 -c 1 -b 16 -D silence.wav trim 0 5` |
| `noise-room.wav` | 5 s of low room noise, pink noise at about -60 dBFS RMS | CC0 (generated) | 2026-11-23 | `sox -n -r 16000 -c 1 -b 16 noise-room.wav synth 5 pinknoise vol -46dB` |
| `noise-fan.wav` | 5 s of fan-like noise, brown noise at about -45 dBFS RMS | CC0 (generated) | 2026-11-23 | `sox -n -r 16000 -c 1 -b 16 noise-fan.wav synth 5 brownnoise vol -40dB` |

Tests that need longer silence or noise loop these files.
