# InkAlive v1.0.0 validation

## Reproducible reference

The project owner accepted the bundled Panna gaze/nod as the final reference effect. The GIF SHA256 is:

```text
3db81ef6b0d3113056e418f218857c2bbde6a2b7d12e4984c707fc5b5eca4312
```

The published source recipe, static generated sequence sheet and two alpha sheets were run through the complete local pipeline from the public distribution directory. The resulting GIF is byte-identical to the accepted reference: 50 decoded image states, 252 × 252 and 2,000 ms total. It derives from 24 drawn keys and 26 inferred images. Original key pixels/timestamps and source-static pixels were retained by the verified pipeline.

Verified environment: Python 3.12.10, Pillow 12.3.0, numpy 2.5.2, OpenCV 5.0.0. Exact bytes are an environment-specific result, not a guarantee across all dependency versions or operating systems.

## Review and artifact checks

The existing workflow had separately exercised `init`, full rendering, GIF-source continuation, `inspect`, `record-review` and `finalize`. The public distribution reran the complete bundled render and checked the resulting GIF against the reference hash. The new run correctly remains pending visual review; historical reference acceptance is not treated as approval of an unrelated new output.

Skill metadata/frontmatter validation and CLI help/import checks passed. Python syntax, JSON/YAML, relative links, skill file equality and ZIP integrity are checked before publication. The canonical, installed and public skill copies contain the same portable files. Public packaging edits remove the acceptance quotation and project-only case narrative; the Python processing logic, drawing/matte data and source recipe are retained.

## Limits

This evidence covers the included small chest-up action. No new-character, walking/hand-heavy action, cross-platform installation, new image-generation run, independent continuous-playback judgment or new test suite is claimed for this release.

Review records attest to performed inspection and bind artifact/evidence hashes. They cannot prove honest notes, natural acting or correct source drawings. Inspect anatomy, pupils/lips, fine hair and neck edges, props and the loop in every new job. Large occlusions may require new drawn keys instead of software interpolation.

Only the skill, its reproducible example and public documentation are distributed. Private project continuity, conversations, account paths, full serial-comic packages, credentials and unrelated outputs are excluded. The helper does not authorize external publishing or autonomous future work.
