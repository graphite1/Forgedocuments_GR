# Theme-corrected 1.3.12 prerelease

The user authorized v1.3.12-preview.1 and, before publication, specified the former Tomei screen theme. The previously saved local/Library ZIP is retained unchanged. This release is rebuilt from the theme-corrected source, not a replacement of that Library item or public 1.3.10.

`desktop_theme.py` selects Windows `vista`, which the earlier isolated Windows reproduction identified as the original Tomei theme. Home, AC and Tomei all call this shared function. The former AC `clam` override and AC-specific widget padding are removed. A `default` fallback exists only for non-Windows development runtimes without vista. PDF ink/color, storage/migration code and assets are unchanged by this correction.

Headless verification: 10 tests passed (3 theme-contract/entry-point checks, 5 storage safety regressions, 2 blue/PDF checks). Real entry points were interrupted immediately after theme application using a fake style backend. Tk root/Toplevel/Style constructors were blocked so no windows could be created. Both-form entry points retain vista across the tested AC/Tomei round trips. Static guards prevent bypassing the shared theme selector.

The new executable was not launched. Its embedded compiled desktop_theme module was extracted and executed with a fake style backend and GUI constructors blocked; vista remained selected. Compiled Home/AC/Tomei code all reference the shared selector, with no old theme_use/Style/clam overrides. Seven ZIP members and 1,030 embedded data/binary entries were audited against tracked defaults and approved assets. No user settings, DB, originals, source crops, backups, secrets, private font experiments or Fontspector binary are included.

Release ZIP: 47,603,685 bytes.

ZIP SHA256: `d0ec1ba3f08416e1ef25becfff270a22d41c6b12af131eff559ac3fc4e838aa4`.

EXE SHA256: `876e5945d659a632e970341e6b11f9e6e6eae4fd5d82da34be5c568a22873e06`.

Before this theme correction and the screen-use prohibition, the preceding storage build passed 135 tests (133 pass, 2 signature-related skips) and native GUI/storage/PDF diagnostics; those results and hashes are historical in `VALIDATION_1.3.12.md`. The updated 138-case combined suite was not run because it includes GUI cases. The final theme-corrected binary has no post-change GUI restart verification. Physical printing, new-key signature/tampering and signed-Windows-ZIP staging remain unverified. This is an unsigned, nonlatest prerelease, not a signed GR Release Hub automatic-update package.

All work after the user's screen prohibition uses headless tools. No screen/focus operations, user-app replacement, main merge or existing tag moves.
