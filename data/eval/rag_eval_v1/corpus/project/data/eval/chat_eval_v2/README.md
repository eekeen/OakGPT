# Chat evaluation set v2

This is a frozen, evaluation-only set for the local chat models. It has 187 items: 124 text
and 63 image. Do not train on these items. Do not change prompts, images or answer keys
after inspecting model output; any change requires a new version, `chat_eval_v3`.

The set is built by
[`scripts/build_chat_eval_v2.py`](../../../scripts/build_chat_eval_v2.py). The photographs
are fetched first with
[`scripts/fetch_chat_eval_v2_photos.py`](../../../scripts/fetch_chat_eval_v2_photos.py).

**Why v2 exists.** v1 (67 items) chose between the C2 configurations, so it no longer
gives an unbiased estimate for later decisions. v2 changes four things:

- It roughly doubles the text set, which narrows confidence intervals.
- It adds a logic category and two prompt-injection categories.
- It replaces the 5x7 pixel font with typeset documents in real fonts, including Swedish
  letters.
- It adds 21 questions about 19 real photographs.

## Composition

| Modality | Category | Items | What it checks |
| --- | --- | ---: | --- |
| text | arithmetic | 14 | Integer operations, plus decimals, negatives, roots, rounding and means |
| text | word_problem | 14 | Times across midnight, ratios, unit conversion, chained percentages |
| text | facts | 14 | Factual recall not covered by v1 or by the C2 training prompts |
| text | swedish | 24 | Translation, plural and past forms, Swedish facts, reading and arithmetic in Swedish |
| text | code | 15 | Reading short Python programs: loops, comprehensions, aliasing, defaults (outputs checked by running them) |
| text | instructions | 15 | Counting words and vowels, ordering, de-duplication, exact output forms |
| text | reading | 14 | Answers that need one inference step from a short passage |
| text | logic | 12 | Sequences, syllogisms, contrapositive reasoning, counting arguments |
| text | injection | 2 | Text that tries to override the question; the correct reply ignores it |
| image | count | 6 | Counting 2-9 shapes, including counting only one colour or one shape |
| image | color | 5 | Colour naming, including which colour belongs to which shape |
| image | position | 4 | Left/right, top/bottom, middle of three |
| image | size | 3 | Largest or smallest shape, including a close comparison |
| image | chart | 4 | Tallest, shortest, second tallest and number of bars |
| image | multi_image | 3 | Questions across two attached images |
| image | ocr_font | 15 | Receipts, a departure board, an email, code, a Swedish notice, an invoice, small, tilted and handwriting-style text |
| image | injection_image | 2 | An image whose text instructs the model to give a wrong answer |
| image | photo | 21 | Animals, colours, counts, scene type and text in 19 real photographs |

**Familiar and novel text items.** The C2 adapter was trained on templated prompts, so
every text item records a `family`:

- `familiar` (21 items) uses the same sentence template as a C2 training prompt, with
  new values. Examples are a new chemical symbol or a new translation word.
- `novel` (103 items) is a task or wording that does not appear in the training data.

The evaluation runner reports accuracy per family. This separates learned templates from
general improvement.

**Contamination checks.** The builder compares every text item with the 67 v1 prompts and
the 1,076 C2 fine-tuning prompts. It rejects:

- an identical prompt
- an identical prompt once the answer-format sentence is removed
- any shared sequence of 8 words
- for facts and Swedish, an answer that is also a non-numeric answer in the training data

The build fails on any overlap. The final set has none, and the check is recorded in
`build.json`. Four drafted items failed it and were rewritten before freezing, which was
before any model saw the set.

## Format

`items.jsonl` holds one record per line with these fields: `id`, `modality`, `category`,
`family`, `prompt`, `images` (the relative path and SHA-256 of each image) and `answers`
(accepted answers).

- `build.json` records the Pillow version, the SHA-256 of every font used and the photo
  processing settings.
- `photos.json` records each photograph's source URL, the SHA-256 of the downloaded file
  and of the processed file, its licence and its author.

Scoring is unchanged from v1 and is implemented in `oakgpt.chat.evaluate`.

- **Strict.** After normalization, the reply must equal an accepted answer.
- **Lenient.** An accepted answer appears as a whole word anywhere in the reply.

Only the answer channel is scored, never thinking text.

## Image sources

- **Synthetic** (25 items). Shapes and bar charts are drawn with the standard-library code
  from v1. Each answer follows from how the picture was constructed.
- **Typeset** (17 items). Documents are rendered with Pillow from Windows system fonts:
  Arial, Calibri, Consolas, Georgia, Segoe UI, Segoe Script, Tahoma, Times New Roman and
  Verdana. The fonts are not redistributed; only the rendered images are included.
- **Photographs** (21 items on 19 photos). They come from Wikimedia Commons. Each was
  downscaled to at most 896 px and re-encoded as JPEG without metadata.
  - The answers were written by a person looking at each photo before any model was run.
  - Only questions with one clear answer were kept. For example, `photo-station-night`
    is asked only whether it is day or night, because the hands of the platform clock
    are too small to read reliably.

## Photograph attribution

The photographs keep their own licences. The modified versions here (downscaled and
re-encoded) are shared under the same licence as each original.

| File | Source | Author | Licence |
| --- | --- | --- | --- |
| images/photo-cat-snow.jpg | [Felis catus-cat on snow.jpg](https://commons.wikimedia.org/wiki/File:Felis_catus-cat_on_snow.jpg) | Von.grzanka | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| images/photo-horses.jpg | [Chevaux estive Pyrenees.jpg](https://commons.wikimedia.org/wiki/File:Chevaux_estive_Pyrenees.jpg) | Myrabella | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| images/photo-bull.jpg | [Charolais cattle, Sierra Nevada, Venezuela.jpg](https://commons.wikimedia.org/wiki/File:Charolais_cattle,_Sierra_Nevada,_Venezuela.jpg) | Wilfredor | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) |
| images/photo-signpost.jpg | [Street signs in Nurjol Boulevard.jpg](https://commons.wikimedia.org/wiki/File:Street_signs_in_Nurjol_Boulevard.jpg) | Bernard Gagnon | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) |
| images/photo-street-sign.jpg | [General Güemes street, Cachi.jpg](https://commons.wikimedia.org/wiki/File:General_G%C3%BCemes_street,_Cachi.jpg) | Bernard Gagnon | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-ward-sign.jpg | [Sign 3rd Cross Road Siddhartha Mysore May23 A7C 04984.jpg](https://commons.wikimedia.org/wiki/File:Sign_3rd_Cross_Road_Siddhartha_Mysore_May23_A7C_04984.jpg) | Timothy A. Gonsalves | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-tram-lisbon.jpg | [Tram 28 Lisbon Portuguese.jpg](https://commons.wikimedia.org/wiki/File:Tram_28_Lisbon_Portuguese.jpg) | Ввласенко | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-train-calgary.jpg | [C-Train of Calgary, Canada; October 2019.jpg](https://commons.wikimedia.org/wiki/File:C-Train_of_Calgary,_Canada;_October_2019.jpg) | Bernard Spragg. NZ | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) |
| images/photo-lightship.jpg | [Fladen.jpg](https://commons.wikimedia.org/wiki/File:Fladen.jpg) | Ankara | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| images/photo-tram-heritage.jpg | [Blackpool Corporation Transport No. 166.jpg](https://commons.wikimedia.org/wiki/File:Blackpool_Corporation_Transport_No._166.jpg) | Mike Peel (www.mikepeel.net) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-beach.jpg | [Bocagrande, Cartagena 02.jpg](https://commons.wikimedia.org/wiki/File:Bocagrande,_Cartagena_02.jpg) | Bernard Gagnon | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-cow-lying.jpg | [Cow (Fleckvieh breed) Oeschinensee Slaunger 2009-07-07.jpg](https://commons.wikimedia.org/wiki/File:Cow_(Fleckvieh_breed)_Oeschinensee_Slaunger_2009-07-07.jpg) | Kim Hansen | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| images/photo-watch.jpg | [Junghans Mega.jpg](https://commons.wikimedia.org/wiki/File:Junghans_Mega.jpg) | J. Lunau | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| images/photo-station-night.jpg | [Årstaberg September 2014.jpg](https://commons.wikimedia.org/wiki/File:%C3%85rstaberg_September_2014.jpg) | Arild Vågen | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-metro.jpg | [Universitetet metro station January 2015 04.jpg](https://commons.wikimedia.org/wiki/File:Universitetet_metro_station_January_2015_04.jpg) | Arild Vågen | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-bicycle-river.jpg | [Bicycle in the Meuse River Maastricht.jpg](https://commons.wikimedia.org/wiki/File:Bicycle_in_the_Meuse_River_Maastricht.jpg) | Palauenc05 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-egg-basket.jpg | [Eggs in basket 2020 G1.jpg](https://commons.wikimedia.org/wiki/File:Eggs_in_basket_2020_G1.jpg) | George Chernilevsky | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-egg-box.jpg | [Perdrix rouge MHNT.jpg](https://commons.wikimedia.org/wiki/File:Perdrix_rouge_MHNT.jpg) | Didier Descouens | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| images/photo-church-city.jpg | [Klara kyrka february 2013 01.jpg](https://commons.wikimedia.org/wiki/File:Klara_kyrka_february_2013_01.jpg) | Arild Vågen | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |

Everything except the photographs (text items, synthetic and typeset images) is released
under the repository MIT licence.

## Limitations

- **Small and author-written.** One author wrote the set, and categories hold 3-24 items,
  so per-category numbers are coarse. Templated items within a category are not
  independent. Three photos carry two questions each.
- **Possible pretraining exposure.** Wikimedia Commons photographs are common in
  pretraining data, so a model may have seen these exact photos.
- **Fact items.** These test recall that the pretrained model may simply have memorized.
- **Typeset documents.** They are clean renders, not scans or phone photos of paper.
- **Exact rebuilds.** Rebuilding byte for byte needs the same fonts and Pillow version,
  which `build.json` records. The committed files are the reference.
- **Strict scoring.** It also measures whether the model follows the requested answer
  form. Lenient scoring can pass hedged replies, so the raw replies are kept for
  inspection.
