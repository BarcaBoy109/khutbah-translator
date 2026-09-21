# Training-data source audit

Reviewed 2026-09-22. “Publicly accessible” does not mean “licensed for model
training.” Only rows from sources marked **approved** may enter the processed
training files.

Current API snapshot: 131 bilingual records were cataloged, 130 downloaded
completely, and 94 passed strict OOXML extraction. The structural aligner
created 2,664 review candidates; none are approved training pairs yet.

| Source | What it offers | Licence/status | Planned use |
|---|---|---|---|
| UAE Awqaf sermons via [Islamic Network](https://sermons.islamic.network/) | Arabic and English sermon documents, mostly weekly, 2015-present | **Permission required.** The API states that copyright remains with UAE Awqaf. | Best domain corpus once written training permission is obtained. Align paragraphs/sentences, then human-QA a sample. |
| [Sermon Audio and Text (SAT)](https://data.mendeley.com/datasets/fnz5bt24st/1) | 21,253 Arabic sermon audio/transcript segments, as stated by its publisher | **Approved for its stated CC BY 4.0 terms**, with attribution. It has no English target. | Acquired for the pilot below with explicitly AI-produced English targets. |
| [Helsinki-NLP OPUS-MT Arabic-English](https://huggingface.co/Helsinki-NLP/opus-mt-ar-en) | General Arabic-English translation checkpoint | **Approved, Apache 2.0.** | Base model, not domain data. |
| [Tatoeba downloads](https://tatoeba.org/en/downloads) | General sentence translations | Usually CC BY 2.0, but attribution is per sentence/contributor and must be retained. | Optional small general replay set after exporting full attribution. Not Khutbah-specific. |
| Tanzil / OPUS Tanzil | Qur'an Arabic and English translations | **Excluded for now.** Tanzil Arabic permits attributed verbatim copying and forbids changing the text; English translations have separate rights and Tanzil describes them as non-commercial. | Evaluation/reference matching only after choosing a translation and confirming its exact terms. |
| [QuranLab Hadith](https://huggingface.co/datasets/quranlab/hadith) | Aligned Arabic and multilingual hadith collections | **Excluded by default.** The dataset is explicitly mixed-licence/per-config; translations retain translator/publisher rights. | Import only a specifically audited config whose terms allow training. |
| [IslamicFaithQA](https://huggingface.co/datasets/QCRI/IslamicFaithQA) | Arabic and English Islamic question answering | Apache 2.0, but it is not a sentence-aligned translation corpus. | Possible terminology/evaluation research; do not treat language folders as translation pairs. |

## Data we should actively collect

### SAT pilot acquired in this repository

The text-only downloader now acquires 200 excerpts from all 50 SAT sermon
folders, joining three adjacent chunks per excerpt. The selected 171 excerpts
have AI-authored English targets, explicitly marked `synthetic_target: true`
and `review_status: AI-only; bilingual human review pending`. This creates
**synthetic translation supervision**, not a claim that SAT supplies English.
Twenty-nine excerpts are excluded, including all four from sermon 21 because
its sampled content substantially duplicates sermon 12.

Attribution: Abbas, Samah (2023), "Sermon_audio_and_text_dataset (SAT)",
Mendeley Data, V1, DOI: [10.17632/fnz5bt24st.1](https://doi.org/10.17632/fnz5bt24st.1).
License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Changes: adjacent transcript chunks joined, English translations added,
Unicode/whitespace normalization during preparation. No endorsement by the
dataset author is implied. Each row retains original file URLs and hashes.

No UAE Awqaf candidates or third-party English scripture translations were
used in this pilot. HadeethEnc was checked again; its published reuse terms
require unmodified content, so it remains outside this training experiment.
Other classical-text collections are not substituted for Friday-sermon data.

### Larger human-reviewed corpus

The highest-value corpus is not a generic web scrape. It is a permissioned,
versioned collection of complete Arabic sermons and their human English
translations, segmented while retaining `document_id`, date, publisher,
translator, topic, and quote spans. The project should seek written permission
from Awqaf publishers and local mosques, and offer a simple contributor
agreement for original translations.

Each quotation should additionally record its type (`quran`, `hadith`, or
`none`) and canonical reference when known. This lets evaluation distinguish
ordinary sermon prose from passages that must reproduce an approved published
translation exactly.

## Quality risks

- Never randomly split individual lines from the same sermon across train and
  test; recurring openings and quotations would inflate scores.
- Do not train directly on OCR output without Arabic/English alignment checks.
- Do not mix machine translations into the gold evaluation set.
- Preserve honorifics and named religious terms according to a reviewed style
  guide rather than forcing one community's wording without documentation.
- Keep provenance attached at row level so a source can be removed and the
  dataset/model rebuilt if permission changes.
