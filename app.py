"""Compatibility import and application entry point."""
from ac_screen import App
from main_app import main

if __name__=='__main__':
    import sys
    try:main()
    except Exception as e:
        if '--diagnostic' in sys.argv:raise
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw();messagebox.showerror('Forgedocuments GR',str(e),parent=root);root.destroy()
        sys.exit(1)
