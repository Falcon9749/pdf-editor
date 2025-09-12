# pip install PyMuPDF ttkbootstrap Pillow

import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
import traceback
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import ttkbootstrap as tb
from PIL import Image, ImageTk

# ================== LOGGER DIÁRIO ==================
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1,
                                   backupCount=30, encoding="utf-8")
handler.suffix = "%Y-%m-%d.log"
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

def excecao_nao_tratada(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Exceção não tratada", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = excecao_nao_tratada

def report_callback_exception(self, exc, val, tb_):
    erro = "".join(traceback.format_exception(exc, val, tb_))
    logger.error(f"Erro no Tkinter:\n{erro}")

tk.Tk.report_callback_exception = report_callback_exception
# ====================================================


# ================== MENU INICIAL ==================
class LicenseMenu:
    def __init__(self, root: tb.Window):
        self.root = root
        self.frame = tb.Frame(root)
        self.frame.pack(fill="both", expand=True, padx=20, pady=20)

        tb.Label(self.frame, text="📝 Editor de PDF",
                 font=("Segoe UI", 18, "bold")).pack(pady=10)

        license_text = """MIT License

Copyright (c) 2025 Gilnei Monteiro

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

        text_box = tk.Text(self.frame, wrap="word", height=15, font=("Segoe UI", 10))
        text_box.insert("1.0", license_text)
        text_box.config(state="disabled")
        text_box.pack(fill="both", expand=True, pady=10)

        tb.Button(self.frame, text="▶️ Aceitar e iniciar o Editor",
                  bootstyle="success", command=self.start_app).pack(pady=5, ipadx=10, ipady=5)

        tb.Button(self.frame, text="❌ Sair",
                  bootstyle="danger", command=self.root.quit).pack(pady=5, ipadx=10, ipady=5)

    def start_app(self):
        self.frame.destroy()
        PDFEditorApp(self.root)


# ================== EDITOR DE PDF ==================
class PDFEditorApp:
    def __init__(self, root: tb.Window):
        self.root = root
        self.doc = None
        self.pdf_path = None
        self.current_page = 0
        self.scale = None
        self.words = []
        self.photo_image = None
        self.undo_stack = []
        self.redo_stack = []

        # ---------------- Top Frame ----------------
        top_frame = tb.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, pady=4)

        tb.Button(top_frame, text="📂 Abrir PDF", bootstyle="info", command=self.open_pdf).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="💾 Salvar PDF", bootstyle="success", command=self.save_pdf).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="⏮ Anterior", bootstyle="secondary", command=self.prev_page).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="⏭ Próxima", bootstyle="secondary", command=self.next_page).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="🔍 Zoom +", bootstyle="secondary", command=self.zoom_in).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="🔍 Zoom -", bootstyle="secondary", command=self.zoom_out).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="↩️ Desfazer", bootstyle="warning", command=self.undo_edit).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="🔄 Refazer", bootstyle="info", command=self.redo_edit).pack(side=tk.LEFT, padx=4)

        self.page_label = tb.Label(top_frame, text="Página: -/-", bootstyle="inverse-dark")
        self.page_label.pack(side=tk.RIGHT, padx=10)

        # ---------------- Canvas + Scrollbars ----------------
        canvas_frame = tb.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(canvas_frame, bg="black",
                                yscrollcommand=v_scroll.set,
                                xscrollcommand=h_scroll.set)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        v_scroll.config(command=self.canvas.yview)
        h_scroll.config(command=self.canvas.xview)

        self.canvas.bind("<Button-1>", self.on_click)
        self.root.bind("<Control-z>", lambda e: self.undo_edit())
        self.root.bind("<Control-y>", lambda e: self.redo_edit())

        logger.info("Editor iniciado")

    # ---------------- Abrir PDF ----------------
    def open_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos PDF", "*.pdf")])
        if not path:
            return
        try:
            self.doc = fitz.open(path)
            self.pdf_path = path
            self.current_page = 0
            self.scale = None
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.render_page()
            logger.info(f"PDF aberto: {path}")
        except Exception as e:
            logger.error(f"Erro ao abrir PDF: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{e}")

    # ---------------- Salvar PDF ----------------
    def save_pdf(self):
        if not self.doc:
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                 filetypes=[("PDF", "*.pdf")])
        if not save_path:
            return
        try:
            self.doc.save(save_path)
            logger.info(f"PDF salvo em: {save_path}")
            messagebox.showinfo("Sucesso", f"PDF salvo em:\n{save_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar PDF: {e}")
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")

    # ---------------- Navegação ----------------
    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.render_page()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.render_page()

    # ---------------- Zoom ----------------
    def zoom_in(self):
        if not self.doc:
            return
        self.scale = min((self.scale or 1.0) * 1.25, 3.0)
        self.render_page()

    def zoom_out(self):
        if not self.doc:
            return
        self.scale = max((self.scale or 1.0) / 1.25, 0.5)
        self.render_page()

    # ---------------- Renderização ----------------
    def render_page(self):
        if not self.doc:
            return

        page = self.doc[self.current_page]
        zoom = self.scale or 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        mode = "RGB" if pix.alpha == 0 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        self.photo_image = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_image)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))

        self.page_label.config(text=f"Página: {self.current_page+1}/{len(self.doc)}")
        self.words = page.get_text("words")

    # ---------------- Clique em texto ----------------
    def on_click(self, event):
        if not self.doc:
            return

        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        zoom = self.scale or 1.0
        px = x / zoom
        py = y / zoom

        clicked_word = None
        rect = None
        for w in self.words:
            x0, y0, x1, y1, word, *_ = w
            if x0 <= px <= x1 and y0 <= py <= y1:
                clicked_word = word
                rect = fitz.Rect(x0, y0, x1, y1)
                break

        if clicked_word and rect:
            new_text = simpledialog.askstring("Editar Texto", f"Substituir '{clicked_word}' por:")
            if new_text:
                page = self.doc[self.current_page]
                self.save_state()
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                fontsize = max(4, rect.height * 0.8)
                x, y = rect.x0, rect.y0 + rect.height * 0.8
                page.insert_text((x, y), new_text, fontsize=fontsize, fontname="helv", color=(0, 0, 0))
                self.render_page()

    # ---------------- Histórico ----------------
    def save_state(self):
        if self.doc:
            self.undo_stack.append(self.doc.tobytes())
            self.redo_stack.clear()

    def undo_edit(self):
        if not self.undo_stack:
            return
        try:
            last_state = self.undo_stack.pop()
            self.redo_stack.append(self.doc.tobytes())
            self.doc = fitz.open("pdf", last_state)
            self.render_page()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao desfazer:\n{e}")

    def redo_edit(self):
        if not self.redo_stack:
            return
        try:
            next_state = self.redo_stack.pop()
            self.undo_stack.append(self.doc.tobytes())
            self.doc = fitz.open("pdf", next_state)
            self.render_page()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao refazer:\n{e}")


# ================== MAIN ==================
if __name__ == "__main__":
    app = tb.Window(themename="darkly")
    app.title("Editor de PDF")
    app.geometry("900x650")
    LicenseMenu(app)
    app.mainloop()
