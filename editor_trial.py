# pip install PyMuPDF ttkbootstrap Pillow

import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
import traceback
from copy import deepcopy

import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import ttkbootstrap as tb
from PIL import Image, ImageTk

# extras para o sistema de licença
import json
import uuid
import hashlib
import datetime

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


# ================== MENU INICIAL (LICENÇA / TRIAL) ==================
class LicenseMenu:
    """
    Tela inicial com:
    - Texto da licença (MIT)
    - HWID (mostrado e copiável)
    - Campo para inserir chave (hex) e botão 'Ativar'
    - Botão 'Gerar chave (DEV)' -> gera chave hex para o HWID atual (para testes)
    - Informação do trial (dias restantes e execuções restantes)
    - Botão 'Aceitar e iniciar o Editor' que usa o trial se disponível
    """

    TRIAL_DAYS = 7
    TRIAL_USES = 30
    SALT = "PDFEditorSecret2025"  # diferente do outro app — garante chaves distintas

    def __init__(self, root: tb.Window):
        self.root = root

        # pasta e arquivo onde armazenamos license/trial
        self.lic_dir = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "PDFEditorApp")
        os.makedirs(self.lic_dir, exist_ok=True)
        self.lic_path = os.path.join(self.lic_dir, "license.json")

        # inicializa/garante arquivo
        self.init_license_file()

        # lê licença atual
        self.lic = self.read_license()

        # se já ativado, pular tela de licença e iniciar app
        if self.lic.get("activated", False):
            logger.info("Aplicativo já ativado — iniciando editor.")
            PDFEditorApp(self.root)
            return

        # caso contrário, mostra menu de licença
        self.frame = tb.Frame(root)
        self.frame.pack(fill="both", expand=True, padx=20, pady=20)

        tb.Label(self.frame, text="📝 Editor de PDF", font=("Segoe UI", 18, "bold")).pack(pady=10)

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
        # caixa de texto com a licença
        self.text_box = tk.Text(self.frame, wrap="word", height=12, font=("Segoe UI", 10))
        self.text_box.insert("1.0", license_text)
        self.text_box.config(state="disabled")
        self.text_box.pack(fill="both", expand=True, pady=10)

        # HWID + copiar
        hw_frame = tb.Frame(self.frame)
        hw_frame.pack(fill="x", pady=(6,4))
        tb.Label(hw_frame, text="HWID da máquina:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0,6))
        self.hwid_var = tk.StringVar(value=self.get_hwid())
        # usar tk.Entry para fácil controle do estado readonly
        self.hwid_entry = tk.Entry(hw_frame, textvariable=self.hwid_var, width=40, font=("Segoe UI", 10), fg="black")
        self.hwid_entry.pack(side=tk.LEFT, padx=(0,6))
        self.hwid_entry.config(state="readonly", fg="black")
        tb.Button(hw_frame, text="📋 Copiar HWID", bootstyle="info-outline", command=self.copy_hwid).pack(side=tk.LEFT)

        # Chave (entrada) + ativar + gerar (DEV)
        key_frame = tb.Frame(self.frame)
        key_frame.pack(fill="x", pady=(6,4))
        tb.Label(key_frame, text="Chave de ativação (hex):", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0,6))
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(key_frame, textvariable=self.key_var, width=44, font=("Segoe UI", 10))
        self.key_entry.pack(side=tk.LEFT, padx=(0,6))
        tb.Button(key_frame, text="Ativar", bootstyle="success", command=self.validate_key).pack(side=tk.LEFT, padx=(6,0))

        # botão gerar chave DEV (apenas para geração local de teste)
        # tb.Button(self.frame, text="Gerar chave (DEV)", bootstyle="secondary", command=self.generate_dev_key).pack(pady=(6,0))

        # Info do trial (dias e usos)
        self.trial_info_var = tk.StringVar()
        self.update_trial_info_text()
        tb.Label(self.frame, textvariable=self.trial_info_var, font=("Segoe UI", 11, "bold"), foreground="red").pack(pady=(8,4))

        # Botões inferiores (Aceitar / Sair)
        btn_frame = tb.Frame(self.frame)
        btn_frame.pack(pady=10)
        tb.Button(btn_frame, text=f"▶️ Aceitar e iniciar o Editor (Trial)", bootstyle="warning", width=28,
                  command=self.continue_trial).pack(side=tk.LEFT, padx=6)
        tb.Button(btn_frame, text="❌ Sair", bootstyle="danger", width=12, command=self.root.quit).pack(side=tk.LEFT, padx=6)

    # ---------- Funções de licença/arquivo ----------
    def get_hwid(self) -> str:
        """Retorna o hwid (número decimal do MAC via uuid.getnode)."""
        try:
            return str(uuid.getnode())
        except Exception:
            # fallback simples
            return hashlib.sha256(os.getenv("COMPUTERNAME", "unknown").encode()).hexdigest()

    def copy_hwid(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.hwid_var.get())
            messagebox.showinfo("HWID", "HWID copiado para área de transferência!")
        except Exception as e:
            logger.error(f"Erro ao copiar HWID: {e}")
            messagebox.showerror("Erro", "Não foi possível copiar o HWID.")

    def init_license_file(self):
        """Garante que license.json exista com campos mínimos."""
        if not os.path.exists(self.lic_path):
            expire = (datetime.datetime.now() + datetime.timedelta(days=self.TRIAL_DAYS)).isoformat()
            data = {
                "trial_expire": expire,
                "install_date": datetime.datetime.now().isoformat(),
                "uses": 0,
                "max_uses": self.TRIAL_USES,
                "activated": False,
                "key": ""
            }
            with open(self.lic_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    def read_license(self) -> dict:
        try:
            with open(self.lic_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # garantir campos mínimos caso arquivo editado manualmente
            changed = False
            if "trial_expire" not in data:
                data["trial_expire"] = (datetime.datetime.now() + datetime.timedelta(days=self.TRIAL_DAYS)).isoformat()
                changed = True
            if "install_date" not in data:
                data["install_date"] = datetime.datetime.now().isoformat()
                changed = True
            if "uses" not in data:
                data["uses"] = 0
                changed = True
            if "max_uses" not in data:
                data["max_uses"] = self.TRIAL_USES
                changed = True
            if "activated" not in data:
                data["activated"] = False
                changed = True
            if "key" not in data:
                data["key"] = ""
                changed = True
            if changed:
                self.write_license(data)
            return data
        except Exception as e:
            logger.error(f"Erro lendo license.json: {e}")
            # recria
            self.init_license_file()
            return self.read_license()

    def write_license(self, data: dict):
        try:
            with open(self.lic_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Erro gravando license.json: {e}")

    # ---------- Trial helpers ----------
    def trial_days_left(self) -> int:
        data = self.read_license()
        try:
            expire = datetime.datetime.fromisoformat(data["trial_expire"])
        except Exception:
            expire = datetime.datetime.now() + datetime.timedelta(days=self.TRIAL_DAYS)
            data["trial_expire"] = expire.isoformat()
            self.write_license(data)
        days_left = (expire - datetime.datetime.now()).days
        return max(days_left, 0)

    def trial_uses_left(self) -> int:
        data = self.read_license()
        uses = int(data.get("uses", 0))
        max_uses = int(data.get("max_uses", self.TRIAL_USES))
        return max(max_uses - uses, 0)

    def update_trial_info_text(self):
        days = self.trial_days_left()
        uses_left = self.trial_uses_left()
        self.trial_info_var.set(f"Trial: {days} dia(s) restante(s)  •  Aberturas restantes: {uses_left}")

    # ---------- Ações de UI ----------
    def continue_trial(self):
        data = self.read_license()
        if data.get("activated", False):
            # caso já ativado, iniciar
            self.start_editor()
            return

        days_left = self.trial_days_left()
        uses_left = self.trial_uses_left()
        if days_left <= 0 or uses_left <= 0:
            messagebox.showwarning("Trial Expirado", "O período de trial ou número de execuções expirou. Insira uma chave para continuar.")
            return

        # incrementar uso e salvar
        data["uses"] = int(data.get("uses", 0)) + 1
        self.write_license(data)
        logger.info(f"Continuando trial. Uso incrementado: {data['uses']}")
        self.start_editor()

    def start_editor(self):
        # fecha frame de licença e inicia editor
        try:
            self.frame.destroy()
        except Exception:
            pass
        PDFEditorApp(self.root)

    def generate_dev_key(self):
        """Gera a chave hex para o HWID atual (modo DEV)."""
        hwid = self.get_hwid()
        raw = hwid + self.SALT
        hexkey = hashlib.sha256(raw.encode()).hexdigest().upper()
        # mostrar em diálogo (copiar facilmente)
        dlg = tk.Toplevel(self.root)
        dlg.title("Chave Gerada (DEV)")
        dlg.geometry("640x160")
        dlg.transient(self.root)
        tk.Label(dlg, text="Chave (copie e cole no campo 'Chave de ativação'):", font=("Segoe UI", 10)).pack(pady=(8,4))
        txt = tk.Text(dlg, height=4, width=78)
        txt.insert("1.0", hexkey)
        txt.config(state="disabled")
        txt.pack(padx=8, pady=(0,8))
        def copy_and_close():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(hexkey)
                messagebox.showinfo("Copiado", "Chave copiada para a área de transferência!")
            except Exception:
                pass
        tb.Button(dlg, text="📋 Copiar", bootstyle="info", command=copy_and_close).pack(side=tk.LEFT, padx=12, pady=8)
        tb.Button(dlg, text="Fechar", bootstyle="secondary", command=dlg.destroy).pack(side=tk.RIGHT, padx=12, pady=8)

    def validate_key(self):
        """Valida a chave inserida: se bater com a derivada do HWID+SALT ativa permanentemente."""
        key = self.key_var.get().strip().upper()
        if not key:
            messagebox.showwarning("Chave vazia", "Insira a chave de ativação.")
            return
        hwid = self.get_hwid()
        expected = hashlib.sha256((hwid + self.SALT).encode()).hexdigest().upper()
        if key == expected:
            data = self.read_license()
            data["activated"] = True
            data["key"] = key
            self.write_license(data)
            messagebox.showinfo("Ativado", "Licença ativada com sucesso! Obrigado.")
            logger.info("Aplicativo ativado via chave.")
            # iniciar editor
            self.start_editor()
        else:
            messagebox.showerror("Chave inválida", "A chave inserida é inválida para este HWID.")


# ================== EDITOR DE PDF (mantive íntegro) ==================
class PDFEditorApp:
    def __init__(self, root: tb.Window):
        self.root = root
        self.doc = None
        self.pdf_path = None
        self.current_page = 0
        self.scale = None  # factor de zoom (1.0 padrão)
        self.words = []    # palavras extraídas da página atual (em coordenadas de PDF)
        self.photo_image = None

        # Histórico (undo/redo) guarda (doc_bytes, objects_state)
        self.undo_stack = []
        self.redo_stack = []

        # Objetos sobrepostos (não gravados no PDF até salvar)
        # cada objeto: {"page": int, "x": float (pdf coords), "y": float (pdf coords top), "text": str, "size": int, "canvas_id": int}
        self.objects = []

        # estado da entry ativa (criar/editar/mover)
        self.active_entry = None
        self.entry_window = None
        self.entry_mode = None   # 'new', 'edit', 'move_pdf'
        self.edit_obj_index = None
        self.moving_pdf_word = None  # {"rect": fitz.Rect, "word": str}

        # fonte e alinhamento
        self.font_size = 12
        self.baseline_factor = 0.8

        # arraste de objetos
        self.dragging_obj_index = None
        self.drag_offset_x = 0
        self.drag_offset_y = 0

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

        # Botões para controle de fonte
        tb.Button(top_frame, text="➕ Letra", bootstyle="info", command=self.increase_font_button).pack(side=tk.RIGHT, padx=4)
        tb.Button(top_frame, text="➖ Letra", bootstyle="info", command=self.decrease_font_button).pack(side=tk.RIGHT, padx=4)

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

        # Eventos principais
        self.canvas.bind("<Button-1>", self.on_click_canvas)
        # eventos para mover objetos (canvas text)
        self.canvas.bind("<B1-Motion>", self.on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # atalhos
        self.root.bind("<Control-z>", lambda e: self.undo_edit())
        self.root.bind("<Control-y>", lambda e: self.redo_edit())
        self.root.bind("<Tab>", self.increase_font_size)
        self.root.bind("<Shift-Tab>", self.decrease_font_size)

        logger.info("Editor iniciado")

    # ---------------- Estado / histórico ----------------
    def save_state(self):
        """Salva estado do documento + objetos para undo"""
        if self.doc:
            self.undo_stack.append((self.doc.tobytes(), deepcopy(self.objects)))
            self.redo_stack.clear()
            logger.debug("Estado salvo para undo")

    def undo_edit(self):
        if not self.undo_stack:
            messagebox.showinfo("Desfazer", "Nenhuma ação para desfazer.")
            return
        try:
            last_doc_bytes, last_objs = self.undo_stack.pop()
            # salva atual para redo
            self.redo_stack.append((self.doc.tobytes() if self.doc else None, deepcopy(self.objects)))
            # restaura
            self.doc = fitz.open("pdf", last_doc_bytes) if last_doc_bytes else None
            self.objects = deepcopy(last_objs)
            self.render_page()
            logger.info("Desfazer realizado")
        except Exception as e:
            logger.error(f"Erro ao desfazer: {e}")
            messagebox.showerror("Erro", f"Falha ao desfazer:\n{e}")

    def redo_edit(self):
        if not self.redo_stack:
            messagebox.showinfo("Refazer", "Nenhuma ação para refazer.")
            return
        try:
            next_doc_bytes, next_objs = self.redo_stack.pop()
            self.undo_stack.append((self.doc.tobytes() if self.doc else None, deepcopy(self.objects)))
            self.doc = fitz.open("pdf", next_doc_bytes) if next_doc_bytes else None
            self.objects = deepcopy(next_objs)
            self.render_page()
            logger.info("Refazer realizado")
        except Exception as e:
            logger.error(f"Erro ao refazer: {e}")
            messagebox.showerror("Erro", f"Falha ao refazer:\n{e}")

    # ---------------- Fonte / botões ----------------
    def increase_font_button(self):
        self.font_size += 2
        if self.active_entry:
            # ajustar fonte da entry pelo zoom atual
            display_font = max(1, int(self.font_size * (self.scale or 1.0)))
            self.active_entry.config(font=("Helvetica", display_font))

    def decrease_font_button(self):
        self.font_size = max(4, self.font_size - 2)
        if self.active_entry:
            display_font = max(1, int(self.font_size * (self.scale or 1.0)))
            self.active_entry.config(font=("Helvetica", display_font))

    def increase_font_size(self, event):
        self.increase_font_button()
        return "break"

    def decrease_font_size(self, event):
        self.decrease_font_button()
        return "break"

    # ---------------- Abrir / Salvar ----------------
    def open_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("Arquivos PDF", "*.pdf")])
        if not path:
            return
        try:
            self.doc = fitz.open(path)
            self.pdf_path = path
            self.current_page = 0
            self.scale = None
            self.words = []
            self.objects.clear()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.render_page()
            logger.info(f"PDF aberto: {path}")
        except Exception as e:
            logger.error(f"Erro ao abrir PDF: {e}")
            messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{e}")

    def save_pdf(self):
        """Aplica os objetos no documento (gravando sobre as páginas) e salva em disco."""
        if not self.doc:
            return
        if not self.objects:
            # Se não há objetos, apenas salvar doc atual
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                     filetypes=[("PDF", "*.pdf")])
            if not save_path:
                return
            try:
                self.doc.save(save_path)
                messagebox.showinfo("Sucesso", f"PDF salvo em:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")
            return

        # salvar estado antes de aplicar
        self.save_state()
        try:
            # aplicamos todos os objetos no documento
            for obj in self.objects:
                page = self.doc[obj["page"]]
                px = obj["x"]
                py_top = obj["y"]
                insert_y = py_top + obj["size"] * self.baseline_factor
                page.insert_text((px, insert_y),
                                 obj["text"],
                                 fontsize=obj["size"],
                                 fontname="helv",
                                 color=(0, 0, 0))
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                     filetypes=[("PDF", "*.pdf")])
            if not save_path:
                return
            self.doc.save(save_path)
            # após aplicar e salvar, limpamos objetos (agora já estão embutidos no PDF)
            self.objects.clear()
            self.render_page()
            messagebox.showinfo("Sucesso", f"PDF salvo em:\n{save_path}")
            logger.info(f"PDF salvo com objetos em: {save_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar PDF com objetos: {e}")
            messagebox.showerror("Erro", f"Falha ao salvar:\n{e}")

    # ---------------- Navegação / Zoom ----------------
    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.render_page()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.render_page()

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
        """Renderiza a página atual + desenha os objetos sobrepostos (com escala)."""
        if not self.doc:
            return
        page = self.doc[self.current_page]
        zoom = self.scale or 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        mode = "RGB" if pix.alpha == 0 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        self.photo_image = ImageTk.PhotoImage(img)

        # limpa canvas e redesenha imagem da página
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo_image)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))

        # atualiza label
        self.page_label.config(text=f"Página: {self.current_page+1}/{len(self.doc)}")

        # guarda palavras atuais (em coords PDF) para detectar cliques em texto existente
        self.words = page.get_text("words")

        # desenha objetos que pertencem a essa página
        for idx, obj in enumerate(self.objects):
            if obj["page"] != self.current_page:
                continue
            # posição no canvas = coord_pdf * zoom
            cx = obj["x"] * zoom
            cy = obj["y"] * zoom
            fsize = max(1, int(obj["size"] * zoom))
            # cria texto no canvas com tag 'obj' e tag única
            cid = self.canvas.create_text(cx, cy, text=obj["text"], anchor="nw",
                                          font=("Helvetica", fsize), fill="black",
                                          tags=("obj", f"obj{idx}"))
            obj["canvas_id"] = cid
            # bind dinâmicos (um handler genérico usa 'current')
            self.canvas.tag_bind(f"obj{idx}", "<Button-1>", self.on_object_click)
            self.canvas.tag_bind(f"obj{idx}", "<B1-Motion>", self.on_object_drag)
            self.canvas.tag_bind(f"obj{idx}", "<ButtonRelease-1>", self.on_object_release)
            self.canvas.tag_bind(f"obj{idx}", "<Double-1>", self.on_object_double_click)

    # ---------------- Eventos canvas / objetos ----------------
    def on_click_canvas(self, event):
        """Tratamento de clique no canvas:
           - se clicou em objeto sobreposto: editar / selecionar
           - se clicou em palavra do PDF: opção substituir/mover
           - caso contrário: criar novo objeto (entry)
        """
        if not self.doc:
            return

        # coordenadas canvas
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        zoom = self.scale or 1.0
        px = cx / zoom
        py = cy / zoom

        # 1) se clicou sobre um objeto canvas (tag 'obj'), deixamos o handler de objetos cuidar
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for it in items:
            tags = self.canvas.gettags(it)
            if "obj" in tags:
                # o binding do objeto já gerencia edição/drags (usamos on_object_click)
                # forçamos chamada do handler (ele será acionado pelo tag_bind também)
                return

        # 2) verificar se clicou em palavra existente do PDF (usando coords PDF)
        clicked_word = None
        rect = None
        for w in self.words:
            x0, y0, x1, y1, word, *_ = w
            if x0 <= px <= x1 and y0 <= py <= y1:
                clicked_word = word
                rect = fitz.Rect(x0, y0, x1, y1)
                break

        if clicked_word and rect:
            # Perguntar ação: Substituir / Mover / Cancelar
            self.handle_existing_word_action(rect, clicked_word, cx, cy)
            return

        # 3) caso contrário, criar nova entry para objeto sobreposto (modo 'new')
        self.create_entry_at_canvas(cx, cy, mode="new")

    def create_entry_at_canvas(self, cx, cy, mode="new", prefill_text=None, preset_size=None, edit_index=None):
        """Cria uma Entry sobre o canvas na posição (cx,cy) [coordenadas canvas].
           mode: 'new', 'edit', 'move_pdf'
        """
        # remove entry anterior (se houver)
        if self.active_entry:
            self.cancel_entry()

        display_font = max(1, int((preset_size or self.font_size) * (self.scale or 1.0)))
        self.active_entry = tk.Entry(self.canvas, font=("Helvetica", display_font), bg="white")
        self.entry_window = self.canvas.create_window(cx, cy, anchor="nw", window=self.active_entry)
        if prefill_text:
            self.active_entry.insert(0, prefill_text)
        self.active_entry.focus_set()

        self.entry_mode = mode
        self.edit_obj_index = edit_index

        # binds: arrastar da entry (para reposicionar antes de salvar)
        self.active_entry.bind("<Button-1>", self.start_drag)
        self.active_entry.bind("<B1-Motion>", self.do_drag)
        # salvar / cancelar
        self.active_entry.bind("<Return>", lambda e: self.commit_entry())
        self.active_entry.bind("<Escape>", lambda e: self.cancel_entry())

    def start_drag(self, event):
        # event.x/event.y são coordenadas dentro da widget entry
        self.drag_offset_x = event.x
        self.drag_offset_y = event.y

    def do_drag(self, event):
        # movendo a entry pelo canvas (usando pointer)
        try:
            pointer_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
            pointer_y = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
            self.canvas.coords(self.entry_window, pointer_x - self.drag_offset_x, pointer_y - self.drag_offset_y)
        except Exception:
            pass

    def commit_entry(self):
        """Finaliza entry, dependendo do modo: new -> cria objeto; edit -> atualiza objeto; move_pdf -> move palavra do PDF"""
        if not self.active_entry:
            return
        text = self.active_entry.get()
        # remove entry visual
        coords = self.canvas.coords(self.entry_window)
        self.canvas.delete(self.entry_window)
        self.entry_window = None
        self.active_entry.destroy()
        self.active_entry = None

        if not text.strip():
            # nada para salvar
            self.entry_mode = None
            self.edit_obj_index = None
            self.moving_pdf_word = None
            return

        # converte coords canvas -> pdf
        zoom = self.scale or 1.0
        x_canvas, y_canvas = coords[0], coords[1]
        px = x_canvas / zoom
        py = y_canvas / zoom

        if self.entry_mode == "new":
            # <-- SALVA O ESTADO ANTES DE CRIAR O OBJETO (correção para undo funcionar) -->
            self.save_state()
            # cria objeto em memória (não grava no PDF ainda)
            obj = {"page": self.current_page, "x": px, "y": py, "text": text, "size": self.font_size, "canvas_id": None}
            self.objects.append(obj)
            logger.info(f"Objeto criado na página {self.current_page+1}: '{text}' @ ({px:.1f},{py:.1f}) size={self.font_size}")
            self.render_page()
        elif self.entry_mode == "edit" and self.edit_obj_index is not None:
            # <-- SALVA O ESTADO ANTES DE EDITAR O OBJETO (correção para undo funcionar) -->
            self.save_state()
            # atualiza objeto existente
            idx = self.edit_obj_index
            if 0 <= idx < len(self.objects):
                self.objects[idx]["text"] = text
                # atualiza posição para o local novo
                self.objects[idx]["x"] = px
                self.objects[idx]["y"] = py
                self.objects[idx]["size"] = self.font_size
                logger.info(f"Objeto editado idx={idx}: '{text}'")
            self.render_page()
        elif self.entry_mode == "move_pdf" and self.moving_pdf_word:
            # mover palavra do PDF: apagar retângulo original e inserir no novo local
            rect = self.moving_pdf_word["rect"]
            original_word = self.moving_pdf_word["word"]
            try:
                self.save_state()
                page = self.doc[self.current_page]
                # apagar original (no doc) - atenção: isso afeta imediatamente o documento
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                # tamanho de fonte baseado no tamanho original do rect
                computed_font = max(4, (rect.height) * 0.8)
                insert_y = py + computed_font * self.baseline_factor
                page.insert_text((px, insert_y), text, fontsize=int(computed_font), fontname="helv", color=(0, 0, 0))
                logger.info(f"Palavra '{original_word}' movida para ({px:.1f},{py:.1f}) fontsize={int(computed_font)}")
                # limpar estado
                self.moving_pdf_word = None
                self.render_page()
            except Exception as e:
                logger.error(f"Erro ao mover palavra do PDF: {e}")
                messagebox.showerror("Erro", f"Falha ao mover palavra:\n{e}")

        # reset modes
        self.entry_mode = None
        self.edit_obj_index = None
        self.moving_pdf_word = None

    def cancel_entry(self):
        if self.active_entry:
            self.canvas.delete(self.entry_window)
            self.active_entry.destroy()
            self.active_entry = None
            self.entry_window = None
        self.entry_mode = None
        self.edit_obj_index = None
        self.moving_pdf_word = None

    # ---------------- Manipulação de objetos já desenhados no canvas ----------------
    def on_object_click(self, event):
        """Ao clicar em objeto canvas: seleciona (permitindo arrastar) e também abre edição com duplo clique."""
        # identificamos o item current
        items = self.canvas.find_withtag("current")
        if not items:
            return
        cid = items[0]
        # encontra index do objeto
        idx = None
        for i, obj in enumerate(self.objects):
            if obj.get("canvas_id") == cid:
                idx = i
                break
        if idx is None:
            return

        # <-- SALVA O ESTADO ANTES DE INICIAR O DRAG (correção para undo do movimento) -->
        self.save_state()

        # iniciar arraste
        self.dragging_obj_index = idx
        # calcula offset entre posição do mouse e posição do objeto
        pos = self.canvas.coords(cid)
        if pos:
            self.drag_offset_x = event.x - pos[0]
            self.drag_offset_y = event.y - pos[1]

    def on_object_drag(self, event):
        """Arrastar objeto (apenas movimenta a representação canvas)."""
        if self.dragging_obj_index is None:
            return
        cid = self.objects[self.dragging_obj_index]["canvas_id"]
        # mantem no canvas
        new_x = event.x - self.drag_offset_x
        new_y = event.y - self.drag_offset_y
        self.canvas.coords(cid, new_x, new_y)

    def on_object_release(self, event):
        """Ao soltar, atualiza coordenadas do objeto (converte para coords PDF)."""
        if self.dragging_obj_index is None:
            return
        cid = self.objects[self.dragging_obj_index]["canvas_id"]
        coords = self.canvas.coords(cid)
        if coords:
            cx, cy = coords[0], coords[1]
            zoom = self.scale or 1.0
            self.objects[self.dragging_obj_index]["x"] = cx / zoom
            self.objects[self.dragging_obj_index]["y"] = cy / zoom
            logger.info(f"Objeto idx={self.dragging_obj_index} movido para pdf coords ({self.objects[self.dragging_obj_index]['x']:.1f},{self.objects[self.dragging_obj_index]['y']:.1f})")
        self.dragging_obj_index = None

    def on_object_double_click(self, event):
        """Edição rápida: ao dar duplo clique em um objeto, abre entry para editar."""
        items = self.canvas.find_withtag("current")
        if not items:
            return
        cid = items[0]
        idx = None
        for i, obj in enumerate(self.objects):
            if obj.get("canvas_id") == cid:
                idx = i
                break
        if idx is None:
            return
        # abre entry pré-preenchida no local do objeto
        zoom = self.scale or 1.0
        cx = self.objects[idx]["x"] * zoom
        cy = self.objects[idx]["y"] * zoom
        self.font_size = self.objects[idx]["size"]
        self.create_entry_at_canvas(cx, cy, mode="edit", prefill_text=self.objects[idx]["text"],
                                    preset_size=self.objects[idx]["size"], edit_index=idx)

    # ---------------- Click em palavra do PDF (substituir/mover) ----------------
    def handle_existing_word_action(self, rect, word, canvas_x, canvas_y):
        """Mostra um diálogo simples com opções: Substituir, Mover, Cancelar."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Ação sobre texto")
        dlg.geometry("320x120")

        # Mantém a janela sempre na frente
        dlg.attributes("-topmost", True)  # força a ficar no topo
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.focus_force()
        dlg.lift()

        # Remove topmost depois que ganha foco para não interferir em outras janelas
        dlg.after(100, lambda: dlg.attributes("-topmost", False))

        tk.Label(dlg, text=f"Texto: '{word}'", font=("Segoe UI", 10, "bold")).pack(pady=6)
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=6)

        def do_replace():
            dlg.destroy()
            new_text = simpledialog.askstring("Substituir Texto", f"Substituir '{word}' por:")
            if new_text is None:
                return
            try:
                self.save_state()
                page = self.doc[self.current_page]
                # apaga área original e insere novo texto
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                fontsize = max(4, rect.height * 0.8)
                insert_y = rect.y0 + rect.height * 0.8
                page.insert_text((rect.x0, insert_y), new_text, fontsize=fontsize, fontname="helv", color=(0, 0, 0))
                self.render_page()
                logger.info(f"Substituído '{word}' por '{new_text}'")
            except Exception as e:
                logger.error(f"Erro ao substituir: {e}")
                messagebox.showerror("Erro", f"Falha ao substituir:\n{e}")

        def do_move():
            dlg.destroy()
            # modo move: criamos entry pré-preenchida no ponto clicado
            # definimos entry_mode = 'move_pdf' e armazenamos rect+word
            self.moving_pdf_word = {"rect": rect, "word": word}
            # definir font_size baseado no rect (para visual corresponder)
            self.font_size = max(4, int(rect.height * 0.8))
            self.create_entry_at_canvas(canvas_x, canvas_y, mode="move_pdf", prefill_text=word, preset_size=self.font_size)

        def do_cancel():
            dlg.destroy()

        tk.Button(btn_frame, text="Substituir", width=10, command=do_replace).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Mover", width=8, command=do_move).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancelar", width=8, command=do_cancel).pack(side="left", padx=6)

    # ---------------- Canvas geral drag (para não conflitar) ----------------
    def on_canvas_motion(self, event):
        # usado se necessário para interações gerais; mantemos vazio para não atrapalhar
        pass

    def on_canvas_release(self, event):
        # usado se necessário
        pass


if __name__ == "__main__":
    app = tb.Window(themename="darkly")
    app.title("Editor de PDF")
    app.geometry("1200x650")
    LicenseMenu(app)
    app.mainloop()
