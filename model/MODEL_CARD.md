# Khutbah SAT Arabic-to-English pilot

**Status: trained locally; experimental; failed production promotion.**
Run date: 2026-09-22. Intended use: further development of Friday-sermon
translation, with bilingual human review. Not suitable for unsupervised live
sermon or scripture translation.

## Model and training

- Base: [Helsinki-NLP/opus-mt-ar-en](https://huggingface.co/Helsinki-NLP/opus-mt-ar-en),
  Apache 2.0, revision `c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1`.
- Method: LoRA, rank 8, alpha 16, dropout 0.05, query/value attention projections.
  294,912 trainable parameters out of 77,128,704 total parameters including adapters.
- Hardware: NVIDIA GeForce RTX 3050 Laptop GPU, 4 GB; PyTorch 2.7.1+cu128.
- Training: 136 examples from 40 sermons, batch size 1, accumulation 8,
  learning rate 0.0002, maximum 192 tokens, mixed precision and gradient checkpointing.
- Eight epochs configured; early stopping completed at epoch 6 (102 optimizer steps).
  The restored checkpoint is epoch 4 (step 68), selected by validation chrF++.
  Training took 152.53 seconds, excluding installation, downloads, and evaluation.
- Local adapter: `model/artifacts/khutbah-sat-pilot/adapter_model.safetensors`.
  Load with `model/scripts/translate.py`; the tokenizer, training configuration,
  and original base weights are required. The loader pins the recorded base revision.

## Data and attribution

Abbas, Samah (2023), **Sermon_audio_and_text_dataset (SAT)**, Mendeley Data, V1,
[doi:10.17632/fnz5bt24st.1](https://doi.org/10.17632/fnz5bt24st.1),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The publisher describes 21,253 Arabic audio/transcript segments. SAT does not
supply English translations.

This experiment downloaded 600 transcript chunks and joined them into 200
excerpts at four positions in each of 50 sermons. It retained 171 excerpts
from 49 sermons. Codex produced the English translations; **all 171 targets
are AI-generated and have not been reviewed by a bilingual human**. Unclear
fragments and all samples from a likely duplicate sermon were excluded.

Changes to the source: adjacent chunks joined; English translations added;
Unicode and whitespace normalized during preparation. Original Arabic spelling
was retained. No endorsement by the dataset author is implied. File URLs,
publisher checksums, author attribution, and transformation notes accompany
each prepared row. No Awqaf permission-pending data was used.

Whole-sermon splits: training 136 examples / 40 sermons; validation 15 / 4;
test 20 / 5. The pre-existing five-example evaluation seed was protected from
training overlap. Original source fingerprints, annotations, per-split hashes,
configuration, and dependency versions are retained for reproduction.

## Measured results

| Evaluation | Base | Adapted |
|---|---:|---:|
| Held-out SAT BLEU, 20 excerpts | 14.57 | 17.75 |
| Held-out SAT chrF++ | 35.97 | 39.37 |
| Existing seed BLEU, 5 examples | 12.14 | 21.98 |
| Existing seed chrF++ | 35.65 | 47.63 |
| Seed expected-term matches | 4/7 | 6/7 |

The SAT references are AI-generated, including the validation references used
to select the checkpoint. Scores therefore measure agreement with that
translation style, not independent human accuracy. The existing seed is tiny
and its own scripture wording is marked for verification. Expected-term matches
are substring checks, not semantic or theological correctness judgments.
Repeated sermon formulas can still make the task easier despite document splits.
No confidence intervals or general-domain retention evaluation were performed.

The adapted model generated the 20 test excerpts in 3.78 seconds at batch size 2
on this GPU, excluding model loading. This is not an end-to-end streaming latency
benchmark. An offline CLI check of a new sentence produced:

> Muslims, keep your trust and be good to your neighbours.

Input: `أيها المسلمون، حافظوا على الأمانة وأحسنوا إلى جيرانكم.`

## Observed failures and deployment decision

Despite improved aggregate scores, manual inspection found critical failures:

- A held-out Qur'anic passage about parents contained the nonsensical phrase
  "my shrimp is small" (`sat-sermon_1-136`).
- The hadith seed still omitted the Prophet's honorific and distorted the
  relation between deeds and intentions.
- The taqwa seed remained awkward and changed "myself" to "my soul".
- Names, classical idioms, pronouns, and quoted attribution can be mistranslated.

**The quotation and translation-quality promotion gates fail.** The live app
continues using its existing translation backend. Improvement on this small
sample is not evidence that the model is ready for religious use.

The next substantive training stage needs many more human-reviewed paired
sermon passages, an independent larger test set, and verified quotation
references. Permission-pending Awqaf material must retain its rights gate.
Do not tune repeatedly against this pilot test set and then present it as untouched.

## Reproduction and evidence

See [README](README.md), [configuration](config.pilot.json),
[comparison](reports/sat-pilot/comparison.json),
[per-example outputs](reports/sat-pilot/adapted-sat.json), and
[dependency lock](reports/sat-pilot/requirements-lock.txt).
Training checkpoints and downloaded data remain local; no model was published.
