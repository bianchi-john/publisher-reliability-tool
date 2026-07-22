# Dataset input and public release

`sampleDataset.csv` is synthetic. The public paper-associated prediction
release is `predictions/manifest.json` plus its listed CSV parts. Private source
data is never tracked.

Generate the public release from a private `.csv`, `.csv.gz`, or single-CSV ZIP
using the repository preparation script (ZIP is a build-time input only, not a
runtime import format):

```bash
python3 scripts/prepare_public_dataset.py \
  /path/to/fullDataset.csv.gz \
  dataset/predictions \
  --duplicate-policy first
```

The generator retains URL, recomputed domain, model class, fold, and available
probabilities. It writes empty `title`, `text`, and `authors` compatibility
fields and excludes protected provider columns/values. The first exact URL in
source order wins; the manifest records source, duplicate, skipped, part-size,
part-SHA-256, and `prt-dataset-content-v1` counts/digests.

Verify before commit:

```bash
python3 scripts/verify_public_dataset.py dataset/predictions
```

With the private source available, add `--source PATH` for field-by-field
projection verification.

The current release has 19,476 source rows, 19,429 released exact URLs, 42
duplicate groups, and 47 skipped later rows. Runtime canonicalization derives
19,411 articles, 77,708 runs, and 20 historical family/fold identities.

Runtime user import intentionally supports only CSV and CSV.GZ. The browser/API
spools one local upload; CLI accepts one path. Default supported limits are
512 MiB and 300,000 logical rows. ZIP, generic manifests, arbitrary directories,
and multi-gigabyte inputs are outside the demo. The official bundled manifest
directory remains a startup/verification input.

User schema needs `url` and at least one family label/fold pair. Source ID,
domain, title, text, and authors are optional compatibility fields. Editorial
and protected values are discarded before staging. CSV and CSV.GZ with the same
projected record sequence share an import digest and are not duplicated.

Generated outputs/database arrangement are covered only by the limited CC0
dedication in `../MODEL-OUTPUT-LICENSE.md`; URLs, publishers, source pages,
trademarks, models, and weights are not.
