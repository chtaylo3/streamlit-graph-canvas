# Static sprite atlas benchmark evidence

Recorded 2026-09-02 with the repository's locked Python/Pillow environment on
the development WSL host. These measurements are evidence for the current
implementation, not a general performance claim. Reproduce them with:

```bash
uv run python benchmarks/benchmark_sprite_atlas.py
```

The representative workload uses 500 nodes, 100 unique transparent 72×72 PNG
sources, and one newly introduced image on the changed rerun.

| Measurement | Recorded value |
|---|---:|
| Unique source images / deduplicated tiles | 100 / 100 |
| Packed atlas pages / Blob URLs | 3 / 3 |
| One-tile Blob URL baseline | 100 |
| Packed-page fill ratio | 65.92% |
| Initial encoded page bytes | 44,673 |
| Browser decoded image estimate | 3,145,728 bytes |
| Unchanged rerun delta | 0 pages |
| One-new-image rerun delta | 1 page |
| Initial serialization | 0.225783 seconds |
| Unchanged serialization | 0.166374 seconds |
| One-new-image serialization | 0.172436 seconds |

The benchmark intentionally reports the browser decoded-memory estimate as
page width × page height × four RGBA bytes. It does not measure browser render
time; browser timing and screenshot correctness remain part of conformance
testing.
