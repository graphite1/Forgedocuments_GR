"""Keep the former Tomei Windows appearance across every form entry point."""
from tkinter import ttk

WINDOWS_THEME='vista'


def configure_theme(root=None,*,style=None):
    style=ttk.Style(root) if style is None else style
    # Windows ships vista; non-Windows development runtimes use native default.
    selected=WINDOWS_THEME if WINDOWS_THEME in style.theme_names() else 'default'
    style.theme_use(selected)
    return selected
