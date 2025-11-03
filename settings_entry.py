"""
settings_entry.py
-----------------
Standalone oppstart av innstillingsvinduet for kolonneminne.
Kjør:  python settings_entry.py
"""
import tkinter as tk
from views_settings import open_settings

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # ikke vis egen root
    open_settings(root)
    root.mainloop()
