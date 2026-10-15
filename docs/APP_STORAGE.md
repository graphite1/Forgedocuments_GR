# Automatic form storage

The installation root from `updates.install_root()` owns `data/ac_toyoake` and `data/tomei_taiheiyo`. Routed update executables keep that same installation root. Neither the embedded resource directory nor the application-level `template.json` is a user-data destination. The shell never asks for a storage folder. “保存フォルダーを開く” only opens the current fixed folder.

Legacy APPDATA profiles/preferences are read only as migration input and never rewritten. On a form's first open, `app_storage.py` copies only the old database, WAL/journal, and template to a timestamped backup under `data/backups`. Stable DB/WAL bytes are checked before import. A separate working copy is inspected; the original database and immutable backup are not opened by SQLite. Authoritative DB settings take priority over a portable template mirror. A matching form is copied into a staged destination; a different form is preserved in backup and excluded. No automatic destination is merged or reset. Unidentified nonempty data, invalid automatic form identity and unreadable/corrupt data stop with an error.

Each destination has a form marker, and the existing Store/check_form and form-specific policy checks remain enabled. Color settings belong to that form's own database. The shell initializes the same desktop theme before opening either form to avoid an order-dependent UI theme switch. Blue density remains separate from black input ink; the outside plan notice retains its readability floor.

Writing is tested in the fixed destination before opening a Store. Unwritable or occupied destinations produce a clear instruction to extract the whole application into a writable folder. There is no silent fallback to another path or another form's database. Moving the app manually requires moving its `data` folder with it.

The reported failure was reproduced using preserved copies: the Tomei profile pointed to an extracted 1.3.10 application folder whose root template belongs to AC. Opening Tomei therefore hit the correct cross-form protection. The old AC settings also contain custom purple line ink and blue input ink; no cross-form color mutation was reproduced. The storage fix preserves matching legacy colors and prevents future routing into another form's settings.

1.3.12 is a local-only unsigned confirmation build. No push, tag, release publication, PR merge, new credential, signing key or security-setting changes are authorized by this task. Original user data and diagnostic fixtures are excluded from the package.
