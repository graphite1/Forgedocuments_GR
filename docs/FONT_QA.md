# Numeric subset validation (1.3.10)

Fontspector 1.9.0 is a development tool, never an application dependency or bundled executable. Official Windows GNU ZIP and executable SHA256 are pinned in `tools/fontspector.lock.json`. Download that exact release asset, verify its archive hash, and extract the executable under `.dev-tools/fontspector/1.9.0/`. No installer, PATH changes or OS font registration. Official instructions: https://github.com/fonttools/fontspector/blob/fontspector-v1.9.0/INSTALLATION.md and https://github.com/fonttools/fontspector/blob/fontspector-v1.9.0/USING.md .

Run `python -B tools/check_digits_font.py`. Both profiles use `--skip-network`; no `--hotfix` or `--fix-sources`. Raw and scoped reports are retained under ignored `test-results/`. No font is sent to a web checker.

The font contains only 0–9, period, hyphen and B, plus space and empty glyph zero. Numeric-only mode uses 0–9, period and hyphen; every other character explicitly uses the selected Windows font. This is not a complete Latin or Japanese text font.

The original TTF remains unchanged. The separate checked copy repairs version consistency, lossless horizontal metrics compression, monospaced PANOSE metadata, Windows descent matching existing ink, and names of existing glyphs. `glyf`, `loca` and `cmap` bytes, decoded advances and glyph IDs are unchanged. No characters or strokes were added. `tools/repair_digits_font_structure.py` records proof and refuses source/destination overwrites.

## Raw findings and scoped exclusions

After repair, raw OpenType retains 1 FAIL and 1 ERROR; universal retains 4 FAIL and 1 ERROR. Scoped exclusions reflect deliberately partial coverage:

| Check | Reason |
| --- | --- |
| `opentype/code_pages` | OS/2 version 0 and this subset cannot claim a full Windows code page. |
| `opentype/xavgcharwidth` | Checker assumes missing English letters. Actual decoded advances and xAvgCharWidth are all 467. |
| `case_mapping` | Lowercase b is outside the subset and explicitly falls back. |
| `mandatory_glyphs` | Existing glyph zero is intentionally empty; unsupported characters never route to the subset. No replacement shape invented. |
| `whitespace_glyphs` | NBSP is outside the subset and explicitly falls back. |

First two exclusions apply to both profiles, others only to universal. Remaining warnings (raster-derived contour fragments, no STAT, existing line gaps) remain visible. Scoped success does not mean all raw checks pass or prove original-scan visual identity. Private 46/74-character experiments remain unchanged and undistributed.

## Approval and scope

On 2026-10-15 the user authorized development-only Fontspector and the numeric subset in a public GitHub confirmation prerelease. Only the approved 13-glyph font and public background are bundled. Original PDFs, crops, transactions, diagnostics, databases and secrets are excluded. This unsigned prerelease is not a signed GR Release Hub automatic update.
