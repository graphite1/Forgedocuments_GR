# Local confirmation of 1.3.11

CTLBOIC, Windows, existing MS Gothic TTC face 0. No publication or push for this additional version.

- Full isolated suite: 129 tests, 127 passed, 2 fixed signature-related skips; exit 0. `python -X utf8 -B verify_cloud.py`.
- Source blue-density tests cover invalid values, source preservation, unchanged 100% output, black text/position independence, notice visibility, four-up pagination, three previews and saved reopen.
- Actual one-file Windows EXE copied alone to a clean folder, two smoke starts succeeded. Automated Tk/PDF diagnostics passed, including nine blue previews at 35/100/150%, pixel-identical preview/PDF pairs, single/four-up PDFs and saved density after restart.
- All 1,030 embedded data/binary entries and the seven ZIP members audited. Original PDFs, source crops, user databases, secrets, Fontspector and private font experiments are absent. Approved 13-glyph font remains SHA256 `9511a838776102e226de15a6d5f5f6f33c792e8a4bcd7e30657907b4d0cf7997`.
- EXE SHA256: `b897c58aa11509287afa97ecc39d80fa4ecec8d4ab8cb86b3a8cfb89f30eb259`.
- Confirmation ZIP SHA256: `4e02a9671b77c6ad06ff3f1f8973f0243d72f4f50c2d42c744bcb963da81c913` (47,535,090 bytes).

Three original PDFs (13+26+1 pages) were opened and hashes checked before reusing local page renders. All 40 plan-number regions were visually reviewed. Confirmed plan digits: `023457`; `1689` were not observed in that field. Eight per-position crops for six distinct characters were retained privately without stroke reconstruction. Every confirmed digit already exists in numeric13 and observed46, with identical existing numeric outlines. 普通 was visually rechecked in faint/dense original crops; both characters already exist in observed46. Numeric13 intentionally lacks 普通 and the seven characters 配合計画書NO, which continue to use explicit Windows fallback. No requested character is missing from observed46. No glyphs or fonts were modified in this task.

Raw source crop evidence, transaction identifiers, private reports and isolated records stay outside Git and the confirmation ZIP. The two skipped checks are `test_signature_and_tampering` (would create a temporary signing key) and `test_zip_traversal_and_stage_integrity` (requires a genuine signed Windows ZIP). Existing published-manifest verification passed without creating keys. Physical printing and final AC-original visual identity remain unverified.
