# pip install PyMuPDF ttkbootstrap Pillow

import fitz # PyMuPDF
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import ttkbootstrap as tb
from PIL import Image, ImageTk


class PDFEditorApp:
    def __init__(self, root: tb.Window):
        self.root = root
        self.root.title("📝 Editor de PDF")
        self.root.geometry("1000x700")

        self.doc = None
        self.pdf_path = None
        self.current_page = 0
        self.scale = None  # zoom control
        self.words = []    # words on current page
        self.photo_image = None

        # ---------------- Top Frame ----------------
        top_frame = tb.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, pady=4)

        tb.Button(top_frame, text="📂 Abrir PDF", bootstyle="info", command=self.open_pdf).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="💾 Salvar PDF", bootstyle="success", command=self.save_pdf).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="⏮ Anterior", bootstyle="secondary", command=self.prev_page).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="⏭ Próxima", bootstyle="secondary", command=self.next_page).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="🔍 Zoom +", bootstyle="secondary", command=self.zoom_in).pack(side=tk.LEFT, padx=4)
        tb.Button(top_frame, text="🔍 Zoom -", bootstyle="secondary", command=self.zoom_out).pack(side=tk.LEFT, padx=4)

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
            self.render_page()
        except Exception as e:
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
            messagebox.showinfo("Sucesso", f"PDF salvo em:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar PDF:\n{e}")

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
        rect = page.rect
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

        # guarda palavras da página atual
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
            new_text = simpledialog.askstring("Editar Texto",
                                              f"Substituir '{clicked_word}' por:")
            if new_text:
                page = self.doc[self.current_page]

                # 1) cobre com branco
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))

                # 2) escreve novo texto
                fontsize = max(4, rect.height * 0.8)
                x, y = rect.x0, rect.y0 + rect.height * 0.8
                page.insert_text((x, y),
                                 new_text,
                                 fontsize=fontsize,
                                 fontname="helv",
                                 color=(0, 0, 0))

                self.render_page()


if __name__ == "__main__":
    app = tb.Window(themename="darkly")
    PDFEditorApp(app)
    app.mainloop()
