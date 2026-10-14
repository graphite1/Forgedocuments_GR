"""Unique, short-lived PDFs shared by form screens and print workflows."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def generated_pdf(directory, prefix='preview'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{prefix}-{uuid4().hex}.pdf'
    try:
        yield path
    finally:
        # A cancelled print or failed render must not break the next attempt.
        # Some external Windows readers may still hold the file: retain that
        # unique file instead of masking the original error with cleanup.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
