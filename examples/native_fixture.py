"""Small deterministic Tkinter fixture for manual Windows DeskPilot demos."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def main() -> None:
    root = tk.Tk()
    root.title("DeskPilot Native Fixture")
    root.geometry("520x360")

    value = tk.StringVar()
    status = tk.StringVar(value="Native fixture waiting")

    menubar = tk.Menu(root)
    options = tk.Menu(menubar, tearoff=False)
    options.add_command(
        label="Enable Fixture Mode", command=lambda: status.set("Menu opened")
    )
    menubar.add_cascade(label="Options", menu=options)
    root.config(menu=menubar)

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="DeskPilot Native Fixture").pack(anchor="w")
    ttk.Label(frame, text="Native Input").pack(anchor="w", pady=(24, 4))
    ttk.Entry(frame, textvariable=value, width=42).pack(anchor="w")
    ttk.Button(
        frame,
        text="Submit Native Fixture",
        command=lambda: status.set(
            "Native fixture success" if value.get().strip() else "Native input required"
        ),
    ).pack(anchor="w", pady=(24, 0))
    ttk.Button(
        frame, text="Open Menu State", command=lambda: status.set("Menu opened")
    ).pack(
        anchor="w",
        pady=(12, 0),
    )
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(24, 0))

    root.mainloop()


if __name__ == "__main__":
    main()
