import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import pymupdf  # PyMuPDF


def _nums(texto):
    """Convierte '1,3', '2–4' o '[1]' en una lista de números."""
    nums = []
    for parte in re.split(r"[,\s]+", texto.strip("[]() ")):
        m = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", parte)
        if m:
            nums += list(range(int(m[1]), int(m[2]) + 1))
        elif parte.isdigit():
            nums.append(int(parte))
    return nums


AZUL_ENLACE = (0.165, 0.365, 0.69)   # azul mate para las citas enlazadas
TINTA_RGB = (0.18, 0.23, 0.25)       # tinta para figuras y tablas, en negrita

_PATRON_REF = r"\b(Figura|Figure|Fig\.|Tabla|Table)\s*(\d+)"
_PATRON_LEYENDA = r"^(Figura|Figure|Fig\.|Tabla|Table)\s*(\d+)[\.:]"


def _tipo(texto):
    return "figura" if texto.lower().startswith("fig") else "tabla"


def encontrar_citas(page, formato):
    """Devuelve una lista de (rectángulo, [números citados], texto original)."""
    resultados = []
    if formato == "superindice":
        for bloque in page.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                for span in linea["spans"]:
                    t = span["text"].strip()
                    # flags & 1 indica superíndice en PyMuPDF
                    if t and span["flags"] & 1 and re.fullmatch(r"[\d,–\-\s]+", t):
                        resultados.append((pymupdf.Rect(span["bbox"]), _nums(t), t))
    else:
        patron = {
            "corchetes": r"\[[\d,–\-\s]+\]",
            "parentesis": r"\([\d,–\-\s]+\)",
        }[formato]
        for m in re.finditer(patron, page.get_text()):
            for rect in page.search_for(m.group()):
                resultados.append((rect, _nums(m.group()), m.group()))
    return resultados


def destino_en_bibliografia(doc, paginas_bib, n):
    """Busca la entrada n en las páginas de bibliografía.
    Devuelve (índice de página, punto) o None si no la encuentra."""
    for idx in paginas_bib:
        pagina = doc[idx]
        for etiqueta in (f"[{n}]", f"{n}.", f"{n})"):
            rects = pagina.search_for(etiqueta)
            if rects:
                return idx, pymupdf.Point(rects[0].x0, rects[0].y0)
    return None


def mapa_leyendas(doc, omitir):
    """Localiza el pie o título de cada figura y tabla.
    Devuelve {(tipo, n): (índice de página, punto, rectángulo de la leyenda)}."""
    mapa = {}
    for i, page in enumerate(doc):
        if i in omitir:
            continue
        for bloque in page.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                texto = "".join(s["text"] for s in linea["spans"]).strip()
                m = re.match(_PATRON_LEYENDA, texto)
                if not m:
                    continue
                clave = (_tipo(m[1]), int(m[2]))
                if clave not in mapa:
                    x0, y0, x1, y1 = linea["bbox"]
                    mapa[clave] = (i, pymupdf.Point(x0, y0), pymupdf.Rect(x0, y0, x1, y1))
    return mapa


def encontrar_menciones(page, leyendas):
    """Menciones 'Figura n' / 'Tabla n' que no son la propia leyenda."""
    menciones = []
    for m in re.finditer(_PATRON_REF, page.get_text()):
        clave = (_tipo(m[1]), int(m[2]))
        for rect in page.search_for(m.group()):
            if any(rect.intersects(r) for r in leyendas):
                continue
            menciones.append((rect, clave, m.group()))
    return menciones


def _spans(page):
    """Todos los spans de la página, con sus caracteres y su estilo original."""
    spans = []
    for bloque in page.get_text("rawdict")["blocks"]:
        for linea in bloque.get("lines", []):
            spans.extend(linea["spans"])
    return spans


def _rgb(entero):
    return (((entero >> 16) & 255) / 255, ((entero >> 8) & 255) / 255, (entero & 255) / 255)


def _numeros_en(page, rect):
    """Cada número dentro de la cita (secuencia de dígitos), con su valor y sus caracteres.
    En '[2-5]' devuelve 2 y 5; en '[1, 3]' devuelve 1 y 3."""
    chars = []
    for span in _spans(page):
        for ch in span.get("chars", []):
            x0, y0, x1, y1 = ch["bbox"]
            if rect.contains(pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                chars.append(ch)
    grupos, actual = [], []
    for ch in chars:
        if ch["c"].isdigit():
            actual.append(ch)
        elif actual:
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return [(int("".join(c["c"] for c in g)), g) for g in grupos]


def procesar(entrada, salida, formato, pag_ini, pag_fin, tipos=()):
    """tipos: subconjunto de ('figura', 'tabla') que se quieren enlazar."""
    doc = pymupdf.open(entrada)
    paginas_bib = list(range(pag_ini - 1, pag_fin))  # índices 0-based
    if any(i < 0 or i >= len(doc) for i in paginas_bib):
        raise ValueError(f"The bibliography page range does not exist in a PDF with {len(doc)} pages.")

    mapa = {k: v for k, v in mapa_leyendas(doc, omitir=paginas_bib).items() if k[0] in tipos} if tipos else {}
    total = 0
    total_figuras = 0
    sin_destino = []

    for i, page in enumerate(doc):
        if i in paginas_bib:
            continue  # no tocar la propia bibliografía
        cambios = []  # (rect, color, negrita, página destino, punto, tipo)

        for rect, nums, _ in encontrar_citas(page, formato):
            if not nums:
                continue
            # Cada número de la cita (incluidos los extremos de un rango) tiene su propio enlace
            for valor, grupo in _numeros_en(page, rect):
                destino = destino_en_bibliografia(doc, paginas_bib, valor)
                if destino is None:
                    sin_destino.append(f"p.{i + 1}: {valor}")
                    continue
                idx, punto = destino
                rect_num = pymupdf.Rect(grupo[0]["bbox"])
                for ch in grupo[1:]:
                    rect_num |= pymupdf.Rect(ch["bbox"])
                cambios.append((rect_num, AZUL_ENLACE, False, idx, punto, "cita"))

        if tipos:
            leyendas = [r for (idx, _, r) in mapa.values() if idx == i]
            for rect, clave, _ in encontrar_menciones(page, leyendas):
                if clave not in mapa:
                    continue
                idx, punto, _ = mapa[clave]
                cambios.append((rect, TINTA_RGB, True, idx, punto, "figura"))

        if not cambios:
            continue

        # Para cada span que contiene un enlace, asignamos a cada carácter
        # su cambio (o None si no es parte de un enlace).
        afectados = []  # (span, lista de cambio-o-None por carácter)
        for span in _spans(page):
            chars = span.get("chars", [])
            asignados = [None] * len(chars)
            tocado = False
            for k, ch in enumerate(chars):
                x0, y0, x1, y1 = ch["bbox"]
                centro = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
                for cambio in cambios:
                    if cambio[0].contains(centro):
                        asignados[k] = cambio
                        tocado = True
                        break
            if tocado:
                afectados.append((span, asignados))
        if not afectados:
            continue

        # 1) Borra el texto de los spans afectados (todos sus caracteres)
        for span, _ in afectados:
            for ch in span.get("chars", []):
                caja = pymupdf.Rect(ch["bbox"])
                page.add_redact_annot(pymupdf.Rect(caja.x0 + 0.2, caja.y0, caja.x1 - 0.2, caja.y1),
                                      fill=(1, 1, 1))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)

        # 2) Reescribe cada carácter: con el estilo nuevo si es enlace, con el original si no
        for span, asignados in afectados:
            base_color = _rgb(span["color"])
            base_font = "hebo" if (span.get("flags", 0) & 16 or "Bold" in span.get("font", "")) else "helv"
            tamano = span["size"]
            caja_por_cambio = {}
            for ch, cambio in zip(span.get("chars", []), asignados):
                # En las citas solo se colorea el número: corchetes y espacios conservan su estilo
                if cambio is None or (cambio[5] == "cita" and ch["c"] in "[] "):
                    fuente, color = base_font, base_color
                else:
                    _, color_c, negrita, _, _, _ = cambio
                    fuente, color = ("hebo" if negrita else "helv"), color_c
                page.insert_text(pymupdf.Point(ch["origin"]), ch["c"], fontsize=tamano,
                                 fontname=fuente, color=color)
                if cambio is not None:
                    key = id(cambio)
                    if key in caja_por_cambio:
                        caja_por_cambio[key][0] |= pymupdf.Rect(ch["bbox"])
                    else:
                        caja_por_cambio[key] = [pymupdf.Rect(ch["bbox"]), cambio]

            for rect_total, cambio in caja_por_cambio.values():
                _, _, _, idx, punto, tipo = cambio
                page.insert_link({
                    "kind": pymupdf.LINK_GOTO,
                    "from": rect_total,
                    "page": idx,
                    "to": punto,
                })
                if tipo == "cita":
                    total += 1
                else:
                    total_figuras += 1

    doc.save(salida)
    return total, total_figuras, sin_destino


def recurso(nombre):
    """Ruta a un archivo incluido en la app (funciona también empaquetada)."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return Path(base) / nombre


# ---------- Interfaz ----------

# Paleta mate, tipo papel académico
FONDO = "#EEEBE5"      # papel
TARJETA = "#F8F6F2"    # superficie de cada bloque
BORDE = "#D6D0C4"      # líneas suaves
TINTA = "#2E3A3F"      # texto principal
APAGADO = "#7D868B"    # texto secundario
ACENTO = "#5E7D78"     # verde grisáceo
ACENTO_OSCURO = "#4D6A65"
BOTON = "#E4E0D7"
CAMPO = "#FBFAF7"
CLARO = "#F8F6F2"

FUENTE_TITULO = ("Georgia", 17, "bold")
FUENTE_SUB = ("Georgia", 11, "italic")
FUENTE_TEXTO = ("Helvetica", 11)
FUENTE_PEQ = ("Helvetica", 10)
FUENTE_SECC = ("Helvetica", 10, "bold")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Refspider")
        root.configure(bg=FONDO)
        root.resizable(False, False)
        self._estilos()

        self.ruta = tk.StringVar(value="")
        self.formato = tk.StringVar(value="corchetes")
        self.pag_ini = tk.IntVar(value=2)
        self.pag_fin = tk.IntVar(value=2)
        self.nombre_salida = tk.StringVar(value="")
        self.figuras = tk.BooleanVar(value=False)
        self.tablas = tk.BooleanVar(value=False)

        principal = ttk.Frame(root, padding=22)
        principal.pack(fill="both", expand=True)

        cabecera = ttk.Frame(principal)
        cabecera.pack(anchor="w")
        self._logo = tk.PhotoImage(file=str(recurso("refspider_icono_64.png")))
        ttk.Label(cabecera, image=self._logo).pack(side="left", padx=(0, 10))
        ttk.Label(cabecera, text="Refspider", style="Titulo.TLabel").pack(side="left")
        ttk.Label(principal, text="Turns citations, figures and tables into clickable links",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 16))

        # 1. Documento
        b1, c1 = self._tarjeta(principal, "1 · Document")
        b1.pack(fill="x", pady=(0, 12))
        ttk.Button(c1, text="Select PDF…", command=self.elegir).pack(anchor="w")
        ttk.Label(c1, textvariable=self.ruta, style="Muted.TLabel",
                  wraplength=460).pack(anchor="w", pady=(8, 0))

        # 2. Citas
        b2, c2 = self._tarjeta(principal, "2 · Citation format")
        b2.pack(fill="x", pady=(0, 12))
        fila = ttk.Frame(c2, style="Card.TFrame")
        fila.pack(anchor="w")
        for valor, texto in [("corchetes", "Brackets  [1]"),
                             ("parentesis", "Parentheses  (1)"),
                             ("superindice", "Superscript  ¹")]:
            ttk.Radiobutton(fila, text=texto, value=valor,
                            variable=self.formato).pack(side="left", padx=(0, 18))
        ttk.Label(c2, text="Also link:", style="Card.TLabel").pack(anchor="w", pady=(12, 0))
        ttk.Checkbutton(c2, text="Figures  (Figure n)",
                        variable=self.figuras).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(c2, text="Tables  (Table n)",
                        variable=self.tablas).pack(anchor="w", pady=(2, 0))

        # 3. Bibliografía y salida
        b3, c3 = self._tarjeta(principal, "3 · Bibliography and output")
        b3.pack(fill="x", pady=(0, 16))
        rango = ttk.Frame(c3, style="Card.TFrame")
        rango.pack(anchor="w")
        ttk.Label(rango, text="Bibliography, from page", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(rango, from_=1, to=999, width=5,
                    textvariable=self.pag_ini).pack(side="left", padx=8)
        ttk.Label(rango, text="to page", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(rango, from_=1, to=999, width=5,
                    textvariable=self.pag_fin).pack(side="left", padx=8)

        salida = ttk.Frame(c3, style="Card.TFrame")
        salida.pack(anchor="w", pady=(12, 0))
        ttk.Label(salida, text="Output PDF name", style="Card.TLabel").pack(side="left")
        ttk.Entry(salida, textvariable=self.nombre_salida, width=34).pack(side="left", padx=8)
        ttk.Label(salida, text=".pdf", style="Muted.TLabel").pack(side="left")

        # Acción
        ttk.Button(principal, text="Create linked PDF", style="Accent.TButton",
                   command=self.ejecutar).pack(fill="x")
        self.estado = ttk.Label(principal, text="", style="Muted.TLabel")
        self.estado.pack(anchor="w", pady=(10, 0))

    def _estilos(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TFrame", background=FONDO)
        st.configure("Card.TFrame", background=TARJETA)
        st.configure("TLabel", background=FONDO, foreground=TINTA, font=FUENTE_TEXTO)
        st.configure("Card.TLabel", background=TARJETA, foreground=TINTA, font=FUENTE_TEXTO)
        st.configure("Muted.TLabel", background=TARJETA, foreground=APAGADO, font=FUENTE_PEQ)
        st.configure("Secc.TLabel", background=TARJETA, foreground=ACENTO, font=FUENTE_SECC)
        st.configure("Titulo.TLabel", background=FONDO, foreground=TINTA, font=FUENTE_TITULO)
        st.configure("Sub.TLabel", background=FONDO, foreground=APAGADO, font=FUENTE_SUB)
        # Casillas y botones de opción: el marcado debe verse con claridad (acento sobre campo)
        for boton in ("TRadiobutton", "TCheckbutton"):
            st.configure(boton, background=TARJETA, foreground=TINTA, font=FUENTE_TEXTO,
                         focuscolor=TARJETA, indicatorbackground=CAMPO,
                         indicatorforeground=ACENTO, indicatorrelief="flat",
                         indicatormargin=(2, 2, 8, 2), padding=(2, 4))
            st.map(boton,
                   background=[("active", TARJETA)],
                   indicatorbackground=[("pressed", BORDE), ("selected", CAMPO)],
                   indicatorforeground=[("selected", ACENTO), ("!selected", CAMPO)])
        st.configure("TButton", background=BOTON, foreground=TINTA, font=FUENTE_TEXTO,
                     padding=(12, 7), borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("active", BORDE)])
        st.configure("Accent.TButton", background=ACENTO, foreground=CLARO,
                     font=("Helvetica", 12, "bold"), padding=(14, 10),
                     borderwidth=0, focusthickness=0)
        st.map("Accent.TButton",
               background=[("active", ACENTO_OSCURO), ("pressed", ACENTO_OSCURO)],
               foreground=[("active", CLARO)])
        for campo in ("TEntry", "TSpinbox"):
            st.configure(campo, fieldbackground=CAMPO, foreground=TINTA,
                         bordercolor=BORDE, lightcolor=BORDE, darkcolor=BORDE,
                         arrowcolor=TINTA, padding=4)

    def _tarjeta(self, padre, titulo):
        """Bloque con borde sutil y título de sección."""
        borde = tk.Frame(padre, bg=BORDE, padx=1, pady=1)
        interior = ttk.Frame(borde, style="Card.TFrame", padding=(16, 12))
        interior.pack(fill="both", expand=True)
        ttk.Label(interior, text=titulo.upper(), style="Secc.TLabel").pack(
            anchor="w", pady=(0, 8))
        return borde, interior

    def elegir(self):
        ruta = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if ruta:
            self.ruta.set(ruta)
            self.nombre_salida.set(Path(ruta).stem + "_enlaces")
            self.estado.config(text="")

    def ejecutar(self):
        if not self.ruta.get():
            messagebox.showwarning("Missing file", "Select a PDF first.")
            return
        if self.pag_fin.get() < self.pag_ini.get():
            messagebox.showwarning("Invalid range",
                                   "The last page cannot be before the first page.")
            return
        nombre = self.nombre_salida.get().strip() or Path(self.ruta.get()).stem + "_enlaces"
        if nombre.lower().endswith(".pdf"):
            nombre = nombre[:-4]
        entrada = Path(self.ruta.get())
        salida = entrada.with_name(nombre + ".pdf")
        if salida.resolve() == entrada.resolve():
            messagebox.showwarning("Name clash",
                                   "The output name cannot be the same as the original file.")
            return
        try:
            tipos = tuple(t for t, v in [("figura", self.figuras), ("tabla", self.tablas)] if v.get())
            total, total_figuras, sin_destino = procesar(
                str(entrada), str(salida), self.formato.get(),
                int(self.pag_ini.get()), int(self.pag_fin.get()),
                tipos=tipos)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        resumen = f"{total} citation links."
        if total_figuras:
            resumen += f"\n{total_figuras} figure and table links."
        texto = resumen
        if sin_destino:
            texto += "\n\nNo bibliography entry found for:\n" + "\n".join(sin_destino[:15])
        self.estado.config(text=f"{total} citations and {total_figuras} figures/tables linked.")
        messagebox.showinfo("Done", f"{texto}\n\n{salida}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
