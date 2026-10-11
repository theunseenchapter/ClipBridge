from __future__ import annotations
import ctypes, json, queue, time, tkinter as tk
from tkinter import ttk
from typing import Callable

import qrcode
from PIL import ImageTk

from .config import PORT
from .security import local_ip


class UI:
    def __init__(self, engine_getter: Callable, hist, settings) -> None:
        self.eng, self.hist, self.s = engine_getter, hist, settings
        self.q: "queue.SimpleQueue[Callable]" = queue.SimpleQueue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.configure(bg="#0f172a")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Clip.TButton", background="#2563eb", foreground="#ffffff",
                        borderwidth=0, padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Clip.TButton", background=[("active", "#3b82f6")])
        style.configure("Clip.Secondary.TButton", background="#1e293b", foreground="#e2e8f0",
                        borderwidth=0, padding=(12, 8), font=("Segoe UI", 9))
        style.map("Clip.Secondary.TButton", background=[("active", "#334155")])
        style.configure("Clip.TEntry", fieldbackground="#1e293b", foreground="#f8fafc",
                        insertcolor="#f8fafc", borderwidth=0, padding=8)
        self.root.after(100, self._poll)

    def post(self, fn: Callable) -> None:
        self.q.put(fn)

    def _poll(self) -> None:
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def run(self) -> None:
        self.root.mainloop()

    # ---- non-focus-stealing toast
    def toast(self, title: str, msg: str) -> None:
        self.post(lambda: self._toast(title, msg))

    def _toast(self, title: str, msg: str) -> None:
        t = tk.Toplevel(self.root)
        t.withdraw()
        t.overrideredirect(True)
        t.attributes("-topmost", True, "-alpha", 0.95)
        f = tk.Frame(t, bg="#222", padx=14, pady=8)
        f.pack()
        tk.Label(f, text=title, fg="white", bg="#222", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(f, text=msg, fg="#bbb", bg="#222", font=("Segoe UI", 9)).pack(anchor="w")
        t.update_idletasks()
        t.geometry(f"+{t.winfo_screenwidth() - t.winfo_reqwidth() - 16}+{t.winfo_screenheight() - t.winfo_reqheight() - 64}")
        u = ctypes.windll.user32
        hwnd = u.GetParent(t.winfo_id()) or t.winfo_id()
        u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80 | 0x08)  # NOACTIVATE|TOOLWINDOW|TOPMOST
        t.deiconify()
        t.after(3000, t.destroy)

    # ---- pairing QR
    def show_pair(self) -> None:
        eng = self.eng()
        tok = eng.pairing.create()
        payload = json.dumps({"v": 1, "id": self.s.device_id, "name": self.s.device_name, "host": local_ip(),
                              "port": PORT, "fp": eng.identity.fingerprint, "tok": tok}, separators=(",", ":"))
        t = tk.Toplevel(self.root)
        t.title("Pair a phone")
        t.configure(bg="#0f172a")
        t.resizable(False, False)
        img = ImageTk.PhotoImage(qrcode.make(payload).resize((280, 280)))
        lbl = tk.Label(t, image=img)
        lbl.image = img
        lbl.configure(bg="#ffffff")
        lbl.pack(padx=24, pady=(24, 16))
        tk.Label(t, text="Pair your phone", fg="#f8fafc", bg="#0f172a",
                 font=("Segoe UI", 16, "bold")).pack()
        tk.Label(t, text="Scan this code in ClipBridge on Android.\nThe code expires in 5 minutes.",
                 fg="#94a3b8", bg="#0f172a", justify="center",
                 font=("Segoe UI", 10)).pack(pady=(6, 22))
        t.after(300000, t.destroy)
        t.bind("<Destroy>", lambda e: eng.pairing.clear() if e.widget is t else None)

    # ---- history window
    def show_history(self) -> None:
        t = tk.Toplevel(self.root)
        t.title("ClipBridge history")
        t.geometry("640x420")
        t.configure(bg="#0f172a")
        qv = tk.StringVar()
        tk.Label(t, text="Clipboard history", fg="#f8fafc", bg="#0f172a",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
        tk.Label(t, text="Search, restore, pin, or remove copied text", fg="#94a3b8",
                 bg="#0f172a", font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 12))
        ttk.Entry(t, textvariable=qv, style="Clip.TEntry").pack(fill="x", padx=20, pady=(0, 12))
        lb = tk.Listbox(t, font=("Segoe UI", 10), activestyle="none",
                        bg="#111c31", fg="#e2e8f0", selectbackground="#2563eb",
                        selectforeground="#ffffff", borderwidth=0, highlightthickness=0)
        lb.pack(fill="both", expand=True, padx=8)
        rows: list[dict] = []

        def refresh(*_):
            rows[:] = self.hist.search(qv.get())
            lb.delete(0, "end")
            for r in rows:
                txt = (r["text"] or "").replace("\n", " ")[:70]
                lb.insert("end", f"{'* ' if r['pinned'] else '  '}{time.strftime('%d %b %H:%M', time.localtime(r['created']))} "
                                 f"[{r['direction'][:3]}/{r['status']}] {txt}")

        def sel():
            i = lb.curselection()
            return rows[i[0]] if i else None

        def act(fn):
            def go():
                r = sel()
                if r:
                    fn(r)
                    refresh()
            return go

        bar = tk.Frame(t, bg="#0f172a")
        bar.pack(fill="x", padx=20, pady=14)
        for label, fn in (("Restore", lambda r: self.eng().restore(r["id"])),
                          ("Pin/Unpin", lambda r: self.hist.set_pinned(r["id"], not r["pinned"])),
                          ("Delete", lambda r: self.hist.delete(r["id"]))):
            ttk.Button(bar, text=label, style="Clip.TButton" if label == "Restore" else "Clip.Secondary.TButton",
                       command=act(fn)).pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="Clear unpinned", style="Clip.Secondary.TButton",
                   command=lambda: (self.hist.clear(), refresh())).pack(side="right")
        qv.trace_add("write", refresh)
        lb.bind("<Double-Button-1>", lambda e: act(lambda r: self.eng().restore(r["id"]))())
        refresh()
