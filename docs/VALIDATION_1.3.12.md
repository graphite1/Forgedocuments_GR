# Local confirmation of automatic storage (1.3.12)

## Reproduced causes

The registered Tomei legacy destination is an extracted 1.3.10 application directory. Its root portable template belongs to AC, and its DB has no saved settings/records. The registered AC destination has one AC setting and no records. Preserved copies reproduce the exact Tomei opening error before the fix; both open successfully after automatic routing. Matching AC custom line/input colors remain unchanged. Actual source DB/settings files were backed up and their SHA256 values rechecked unchanged after verification. Neither legacy profiles nor the installed 1.3.10 executable was replaced.

A separate isolated check of the previous shell confirms an order-dependent UI theme change: initial/home/Tomei use Windows `vista`, then opening AC changes the common theme to `clam`. The new shell initializes the common theme consistently. No cross-form mutation of PDF color settings was reproduced; the old AC settings themselves contain custom purple line ink and blue input ink. Dedicated databases and the native round-trip tests verify color independence.

The installed-folder version metadata is 1.3.10. A live process path lookup was denied by the host, so the exact executable running when the screenshot was taken is not independently confirmed. No alternate process-access method or security change was used.

## Verification

- Full isolated suite: 135 tests in 189.196 seconds; 133 pass, 2 fixed signature-related skips; exit 0.
- Legacy import tests preserve records, setting/history rows and committed WAL data, prefer authoritative DB settings, retain original templates in backups, and reject foreign or unidentified data without deleting it.
- Fresh standalone Windows EXE copied alone to a clean folder: two smoke starts pass. Native shell opens both forms using the production installation-root default and creates `data/ac_toyoake` and `data/tomei_taiheiyo` beside that executable.
- Fresh and migrated scenarios each perform two round trips, five previews per form, saved-record/settings reopen checks, independent color changes, matching preview/PDF pixels, and single/four-up outputs. Tomei plan notices remain within the page and readable.
- No storage-folder picker is permitted in diagnostics. Actual filesystem path obstruction and injected access-denied tests verify clear writable-extraction guidance and no silent fallback. ACLs/security settings were not changed.
- Existing blue-density, fixed-address, input-font, blank-field and outside-plan-notice diagnostics also pass.
- Seven ZIP members and 1,030 embedded data/binary entries audited. No original PDFs, user DB, backups, transaction data, source crops, secrets, private font experiments or Fontspector binary included.

EXE SHA256: `b2c50af10a092fe43fe0cdcd1123c5d25ab75ddd374d71c68b238adc328207af`.

ZIP SHA256: `a98dd11d74718e8e5f9ed0cac84e63e867b69e3c8650f80af6446516f7c83ed8` (47,602,628 bytes).

The two skipped checks are `test_signature_and_tampering` and `test_zip_traversal_and_stage_integrity`, unchanged from earlier key-free verification. Physical printing and AC-original visual identity remain unverified.

All GUI/EXE checks above finished before the user's subsequent instruction to avoid the screen while gaming. After that instruction only headless reporting, file checks and Git operations were performed. No more GUI or focus use is authorized until the user permits it again. This remains a local unsigned build, with no push, tag, publication or PR merge.
