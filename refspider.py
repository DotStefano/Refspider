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


def encontrar_citas(page, formato):
    """Devuelve una lista de (rectángulo, [números citados])."""
    resultados = []
    if formato == "superindice":
        for bloque in page.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                for span in linea["spans"]:
                    t = span["text"].strip()
                    # flags & 1 indica superíndice en PyMuPDF
                    if t and span["flags"] & 1 and re.fullmatch(r"[\d,–\-\s]+", t):
                        resultados.append((pymupdf.Rect(span["bbox"]), _nums(t)))
    else:
        patron = {
            "corchetes": r"\[[\d,–\-\s]+\]",
            "parentesis": r"\([\d,–\-\s]+\)",
        }[formato]
        for m in re.finditer(patron, page.get_text()):
            for rect in page.search_for(m.group()):
                resultados.append((rect, _nums(m.group())))
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


# ---------- Figuras y tablas (opcional) ----------

_PATRON_REF = r"\b(Figura|Fig\.|Tabla)\s*(\d+)"
_PATRON_LEYENDA = r"^(Figura|Fig\.|Tabla)\s*(\d+)[\.:]"


def _tipo(texto):
    return "figura" if texto.lower().startswith("fig") else "tabla"


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


def enlazar_figuras(doc, omitir, mapa):
    """Enlaza las menciones 'Figura n' / 'Tabla n' con su leyenda.
    No enlaza la propia leyenda ni las páginas de bibliografía."""
    total = 0
    for i, page in enumerate(doc):
        if i in omitir:
            continue
        leyendas = [r for (idx, _, r) in mapa.values() if idx == i]
        for m in re.finditer(_PATRON_REF, page.get_text()):
            clave = (_tipo(m[1]), int(m[2]))
            if clave not in mapa:
                continue
            for rect in page.search_for(m.group()):
                if any(rect.intersects(r) for r in leyendas):
                    continue  # es la propia leyenda
                idx, punto, _ = mapa[clave]
                page.insert_link({
                    "kind": pymupdf.LINK_GOTO,
                    "from": rect,
                    "page": idx,
                    "to": punto,
                })
                total += 1
    return total


def procesar(entrada, salida, formato, pag_ini, pag_fin, con_figuras=False):
    doc = pymupdf.open(entrada)
    paginas_bib = list(range(pag_ini - 1, pag_fin))  # índices 0-based
    if any(i < 0 or i >= len(doc) for i in paginas_bib):
        raise ValueError(f"El rango de bibliografía no existe en un PDF de {len(doc)} páginas.")

    total = 0
    sin_destino = []
    for i, page in enumerate(doc):
        if i in paginas_bib:
            continue  # no enlazar dentro de la propia bibliografía
        for rect, nums in encontrar_citas(page, formato):
            if not nums:
                continue
            destino = destino_en_bibliografia(doc, paginas_bib, nums[0])
            if destino is None:
                sin_destino.append(f"p.{i + 1}: {nums[0]}")
                continue
            idx, punto = destino
            page.insert_link({
                "kind": pymupdf.LINK_GOTO,
                "from": rect,
                "page": idx,
                "to": punto,
            })
            total += 1

    total_figuras = 0
    if con_figuras:
        mapa = mapa_leyendas(doc, omitir=paginas_bib)
        total_figuras = enlazar_figuras(doc, paginas_bib, mapa)

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

        principal = ttk.Frame(root, padding=22)
        principal.pack(fill="both", expand=True)

        cabecera = ttk.Frame(principal)
        cabecera.pack(anchor="w")
        self._logo = tk.PhotoImage(file=str(recurso("refspider_icono_64.png")))
        ttk.Label(cabecera, image=self._logo).pack(side="left", padx=(0, 10))
        ttk.Label(cabecera, text="Refspider", style="Titulo.TLabel").pack(side="left")
        ttk.Label(principal, text="Convierte citas, figuras y tablas en enlaces navegables",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 16))

        # 1. Documento
        b1, c1 = self._tarjeta(principal, "1 · Documento")
        b1.pack(fill="x", pady=(0, 12))
        ttk.Button(c1, text="Seleccionar PDF…", command=self.elegir).pack(anchor="w")
        ttk.Label(c1, textvariable=self.ruta, style="Muted.TLabel",
                  wraplength=460).pack(anchor="w", pady=(8, 0))

        # 2. Citas
        b2, c2 = self._tarjeta(principal, "2 · Formato de las citas")
        b2.pack(fill="x", pady=(0, 12))
        fila = ttk.Frame(c2, style="Card.TFrame")
        fila.pack(anchor="w")
        for valor, texto in [("corchetes", "Corchetes  [1]"),
                             ("parentesis", "Paréntesis  (1)"),
                             ("superindice", "Superíndice  ¹")]:
            ttk.Radiobutton(fila, text=texto, value=valor,
                            variable=self.formato).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(c2, text="También enlazar figuras y tablas (Figura n, Tabla n)",
                        variable=self.figuras).pack(anchor="w", pady=(12, 0))

        # 3. Bibliografía y salida
        b3, c3 = self._tarjeta(principal, "3 · Bibliografía y salida")
        b3.pack(fill="x", pady=(0, 16))
        rango = ttk.Frame(c3, style="Card.TFrame")
        rango.pack(anchor="w")
        ttk.Label(rango, text="Bibliografía, de la página", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(rango, from_=1, to=999, width=5,
                    textvariable=self.pag_ini).pack(side="left", padx=8)
        ttk.Label(rango, text="a la", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(rango, from_=1, to=999, width=5,
                    textvariable=self.pag_fin).pack(side="left", padx=8)

        salida = ttk.Frame(c3, style="Card.TFrame")
        salida.pack(anchor="w", pady=(12, 0))
        ttk.Label(salida, text="Nombre del PDF de salida", style="Card.TLabel").pack(side="left")
        ttk.Entry(salida, textvariable=self.nombre_salida, width=34).pack(side="left", padx=8)
        ttk.Label(salida, text=".pdf", style="Muted.TLabel").pack(side="left")

        # Acción
        ttk.Button(principal, text="Crear PDF con enlaces", style="Accent.TButton",
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
        st.configure("TRadiobutton", background=TARJETA, foreground=TINTA, font=FUENTE_TEXTO,
                     focuscolor=TARJETA, indicatorbackground=CAMPO)
        st.map("TRadiobutton", background=[("active", TARJETA)])
        st.configure("TCheckbutton", background=TARJETA, foreground=TINTA, font=FUENTE_TEXTO,
                     focuscolor=TARJETA, indicatorbackground=CAMPO)
        st.map("TCheckbutton", background=[("active", TARJETA)])
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
            messagebox.showwarning("Falta el archivo", "Selecciona un PDF primero.")
            return
        if self.pag_fin.get() < self.pag_ini.get():
            messagebox.showwarning("Rango incorrecto",
                                   "La página final no puede ser menor que la inicial.")
            return
        nombre = self.nombre_salida.get().strip() or Path(self.ruta.get()).stem + "_enlaces"
        if nombre.lower().endswith(".pdf"):
            nombre = nombre[:-4]
        entrada = Path(self.ruta.get())
        salida = entrada.with_name(nombre + ".pdf")
        if salida.resolve() == entrada.resolve():
            messagebox.showwarning("Nombre repetido",
                                   "El nombre de salida no puede ser el del original.")
            return
        try:
            total, total_figuras, sin_destino = procesar(
                str(entrada), str(salida), self.formato.get(),
                int(self.pag_ini.get()), int(self.pag_fin.get()),
                con_figuras=self.figuras.get())
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        resumen = f"{total} enlaces a citas."
        if self.figuras.get():
            resumen += f"\n{total_figuras} enlaces a figuras y tablas."
        texto = resumen
        if sin_destino:
            texto += "\n\nNo encontré la entrada de bibliografía para:\n" + "\n".join(sin_destino[:15])
        self.estado.config(text=f"{total} citas y {total_figuras} figuras/tablas enlazadas.")
        messagebox.showinfo("Listo", f"{texto}\n\n{salida}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
