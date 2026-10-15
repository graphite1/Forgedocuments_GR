# Independent blue artwork density

`blue_ink.py` owns validation and color conversion. Missing `blue_ink_density` means 1.0, preserving existing settings and pixels. Allowed range is 0.35–1.50. `blue_ink_settings.py` provides a separate concrete-form control; black ink density and transparency stay independent.

Only pixels whose blue channel exceeds both other channels are changed. The conversion scales distance from white paper, clamps channel values and creates a separate bitmap. The original PNG is never written. Blue vector artwork uses the same conversion. Neutral/black pixels remain unchanged. The outside-frame plan notice uses at least 0.65 density to remain readable; its position, size and text are unchanged.

This does not select a replacement font or modify the fixed AC address. Existing numeric fonts and their glyph outlines are unchanged. Original PDFs and source sampling evidence remain outside the repository and confirmation package. This additional version is local-only pending separate publication approval.
