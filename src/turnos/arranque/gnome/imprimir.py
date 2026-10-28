"""Impresión (y PDF, con «Imprimir a archivo») de los informes del mes, como la vista
para imprimir de la web: el calendario (A4 horizontal) y las urgencias y domicilios
(A4 vertical). Se dibujan con Cairo y Pango en un `Gtk.PrintOperation`."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from gi.repository import Gtk, Pango, PangoCairo

from turnos.arranque.gnome.comun import DIAS, DIAS_CORTOS, MITADES, NOMBRE_TURNO, TURNOS, nombre_mes, valor_en_turno

JORNADA = {("M1", "M2"): "M", ("T1", "T2"): "T", ("M1", "M2", "T1"): "M+½T", ("M2", "T1", "T2"): "½M+T",
           ("M1", "M2", "T1", "T2"): "M+T"}
GRIS, BORDE, CABECERA, ACENTO = (0.94, 0.94, 0.94), (0.6, 0.6, 0.6), (0.89, 0.95, 0.95), (0.05, 0.42, 0.44)


@dataclass
class Tabla:
    """Tabla para imprimir: anchos relativos de las columnas, cabecera y filas.

    Una fila es una lista de celdas; una celda puede ser texto o (texto, columnas que
    ocupa). `grises`: índices de filas con fondo gris (festivos)."""

    titulo: str
    anchos: list[float]
    cabecera: list[str]
    filas: list[list] = field(default_factory=list)
    grises: set[int] = field(default_factory=set)
    alinear_derecha: set[int] = field(default_factory=set)
    nueva_pagina: bool = False
    leyenda: str = ""
    tamano: float = 8.5


@dataclass
class Informe:
    titulo: str
    subtitulo: str
    horizontal: bool
    tablas: list[Tabla]


def _celdas(fila):
    for celda in fila:
        yield (celda, 1) if isinstance(celda, str) else celda


def informe_calendario(cal: dict, horarios: list[dict], mes: date) -> Informe:
    horario = {h["turno"]: f"{h['inicio'][:5]}–{h['fin'][:5]}" for h in horarios}
    nombres = {m["id"]: m["nombre"] for m in cal["medicos"]}
    mitades = defaultdict(set)
    for a in cal["asignaciones"]:
        mitades[a["medico_id"], a["fecha"]].add(a["mitad"])
    papeles = {(r["medico_id"], r["fecha"]): r["rol"] for r in cal.get("roles", [])}
    dias = Tabla("", [1.3, 4.35, 4.35], ["Día"] + [f"{NOMBRE_TURNO[t]}  {horario.get(t, '')}" for t in TURNOS],
                 leyenda="½ = medio turno (la mitad contigua a la jornada).")
    for d in cal["dias"]:
        f = date.fromisoformat(d["fecha"])
        etiqueta = f"{DIAS[f.weekday()]} {f.day}"
        if d["festivo"]:
            dias.grises.add(len(dias.filas))
            dias.filas.append([etiqueta, (f"Festivo: {d['festivo']}", 2)])
            continue
        celdas = [etiqueta]
        for t in TURNOS:
            textos = []
            for medico_id, nombre in sorted(nombres.items(), key=lambda i: i[1]):
                v = valor_en_turno(mitades[medico_id, d["fecha"]], t)
                if v:
                    papel = papeles.get((medico_id, d["fecha"])) if t == "TARDE" else None
                    textos.append(nombre + (" (½)" if v == 0.5 else "") + (f" ({papel.lower()})" if papel else ""))
            celdas.append(", ".join(textos))
        dias.filas.append(celdas)
    laborables = [d for d in cal["dias"] if not d["festivo"]]
    matriz = Tabla(f"Turnos por médico — {nombre_mes(mes)}", [3.2] + [1] * len(laborables),
                   ["Médico"] + [f"{DIAS_CORTOS[date.fromisoformat(d['fecha']).weekday()]} {int(d['fecha'][8:])}" for d in laborables],
                   nueva_pagina=True, tamano=7,
                   leyenda="M = mañana · T = tarde · ½ = medio turno · U = urgencias · D = domicilios. Los festivos no aparecen.")
    for m in sorted(cal["medicos"], key=lambda m: m["nombre"]):
        if not m["asignado"]:
            continue
        fila = [m["nombre"]]
        for d in laborables:
            clave = tuple(h for h in ("M1", "M2", "T1", "T2") if h in mitades[m["id"], d["fecha"]])
            papel = papeles.get((m["id"], d["fecha"]))
            fila.append((JORNADA.get(clave, "+".join(clave)) if clave else "") + (f" {papel[0]}" if papel else ""))
        matriz.filas.append(fila)
    return Informe(f"Turnos — {nombre_mes(mes)}", _subtitulo(cal), True, [dias, matriz])


def informe_roles(cal: dict, mes: date) -> Informe:
    nombres = {m["id"]: m["nombre"] for m in cal["medicos"]}
    papel = {(r["fecha"], r["rol"]): nombres.get(r["medico_id"], "") for r in cal.get("roles", [])}
    con_servicio = {
        f for f in {c["fecha"] for c in cal["cobertura"]}
        if all(c["minimo"] >= 2 for c in cal["cobertura"] if c["fecha"] == f and c["mitad"] in MITADES["TARDE"])
    }
    dias = Tabla("", [1.6, 4, 4], ["Día", "Urgencias", "Domicilios"], tamano=9)
    for d in cal["dias"]:
        f = date.fromisoformat(d["fecha"])
        etiqueta = f"{DIAS[f.weekday()]} {f.day}"
        if d["festivo"]:
            dias.grises.add(len(dias.filas))
            dias.filas.append([etiqueta, (f"Festivo: {d['festivo']}", 2)])
        elif d["fecha"] not in con_servicio:
            dias.grises.add(len(dias.filas))
            dias.filas.append([etiqueta, ("Sin servicio (menos de dos médicos de tarde)", 2)])
        else:
            dias.filas.append([etiqueta, papel.get((d["fecha"], "URGENCIAS")) or "Sin asignar",
                               papel.get((d["fecha"], "DOMICILIOS")) or "Sin asignar"])
    resumen = Tabla("Por médico", [4, 1.4, 1.4, 1.2], ["Médico", "Urgencias", "Domicilios", "Total"],
                    alinear_derecha={1, 2, 3}, tamano=9)
    for m in sorted(cal["medicos"], key=lambda m: m["nombre"]):
        u, dm = m.get("urgencias", 0), m.get("domicilios", 0)
        if u or dm:
            resumen.filas.append([m["nombre"], str(u), str(dm), str(u + dm)])
    return Informe(f"Urgencias y domicilios — {nombre_mes(mes)}", _subtitulo(cal), False, [dias, resumen])


def _subtitulo(cal: dict) -> str:
    if cal["estado"] == "PUBLICADO" and cal.get("publicado_en"):
        p = cal["publicado_en"][:10]
        return f"Publicado el {p[8:10]}/{p[5:7]}/{p[:4]}"
    return "BORRADOR — calendario no publicado"


# --- Dibujo ---------------------------------------------------------------------------


class Dibujante:
    """Reparte las filas en páginas (en `begin-print`) y dibuja cada página."""

    MARGEN_CELDA = 3.0

    def __init__(self, informe: Informe) -> None:
        self.informe = informe
        self.paginas: list[list] = []  # por página: [(tabla, filas, con_titulo)]

    def _capa(self, contexto, texto: str, ancho: float, tamano: float, negrita=False) -> Pango.Layout:
        capa = contexto.create_pango_layout()
        letra = Pango.FontDescription.from_string(f"Sans {'Bold ' if negrita else ''}{tamano}")
        capa.set_font_description(letra)
        capa.set_width(int(max(ancho - 2 * self.MARGEN_CELDA, 1) * Pango.SCALE))
        capa.set_wrap(Pango.WrapMode.WORD_CHAR)
        capa.set_text(texto, -1)
        return capa

    def _alto_fila(self, contexto, tabla: Tabla, fila, ancho: float, negrita=False) -> float:
        alto, col = 0.0, 0
        unidad = ancho / sum(tabla.anchos)
        for texto, ocupa in _celdas(fila):
            w = sum(tabla.anchos[col:col + ocupa]) * unidad
            alto = max(alto, self._capa(contexto, texto, w, tabla.tamano, negrita).get_pixel_extents()[1].height)
            col += ocupa
        return alto + 2 * self.MARGEN_CELDA

    def paginar(self, operacion, contexto) -> None:
        ancho, alto = contexto.get_width(), contexto.get_height()
        cabecera_informe = 46
        self.paginas, actual, libre = [], [], alto - cabecera_informe
        for tabla in self.informe.tablas:
            if tabla.nueva_pagina and actual:
                self.paginas.append(actual)
                actual, libre = [], alto - cabecera_informe
            titulo = 22 if tabla.titulo else 0
            leyenda = 16 if tabla.leyenda else 0
            alto_cab = self._alto_fila(contexto, tabla, tabla.cabecera, ancho, True)
            pendientes = list(range(len(tabla.filas)))
            primera = True
            while pendientes or primera:
                necesario = (titulo if primera else 0) + alto_cab
                if libre < necesario + 20 and actual:
                    self.paginas.append(actual)
                    actual, libre = [], alto - cabecera_informe
                libre -= necesario
                trozo = []
                while pendientes:
                    h = self._alto_fila(contexto, tabla, tabla.filas[pendientes[0]], ancho)
                    if h > libre and trozo:
                        break
                    trozo.append(pendientes.pop(0))
                    libre -= h
                actual.append((tabla, trozo, primera))
                primera = False
                if pendientes:
                    self.paginas.append(actual)
                    actual, libre = [], alto - cabecera_informe
            libre -= leyenda + 14
        if actual:
            self.paginas.append(actual)
        operacion.set_n_pages(max(1, len(self.paginas)))

    def dibujar(self, _operacion, contexto, numero: int) -> None:
        cr = contexto.get_cairo_context()
        ancho = contexto.get_width()
        cr.set_source_rgb(0, 0, 0)
        capa = self._capa(contexto, self.informe.titulo, ancho, 14, True)
        cr.move_to(0, 0)
        PangoCairo.show_layout(cr, capa)
        borrador = self.informe.subtitulo.startswith("BORRADOR")
        cr.set_source_rgb(0.72, 0.2, 0.16) if borrador else cr.set_source_rgb(0.35, 0.35, 0.35)
        capa = self._capa(contexto, self.informe.subtitulo, ancho, 8.5, borrador)
        cr.move_to(0, 22)
        PangoCairo.show_layout(cr, capa)
        y = 46.0
        for tabla, filas, con_titulo in self.paginas[numero] if self.paginas else []:
            if con_titulo and tabla.titulo:
                cr.set_source_rgb(0, 0, 0)
                cr.move_to(0, y)
                PangoCairo.show_layout(cr, self._capa(contexto, tabla.titulo, ancho, 11, True))
                y += 22
            y = self._fila(cr, contexto, tabla, tabla.cabecera, y, ancho, cabecera=True)
            for i in filas:
                y = self._fila(cr, contexto, tabla, tabla.filas[i], y, ancho, gris=i in tabla.grises)
            if tabla.leyenda and (not filas or filas[-1] == len(tabla.filas) - 1):
                cr.set_source_rgb(0.35, 0.35, 0.35)
                cr.move_to(0, y + 3)
                PangoCairo.show_layout(cr, self._capa(contexto, tabla.leyenda, ancho, 7.5))
                y += 16
            y += 14

    def _fila(self, cr, contexto, tabla: Tabla, fila, y: float, ancho: float, cabecera=False, gris=False) -> float:
        alto = self._alto_fila(contexto, tabla, fila, ancho, cabecera)
        unidad = ancho / sum(tabla.anchos)
        x, col = 0.0, 0
        for texto, ocupa in _celdas(fila):
            w = sum(tabla.anchos[col:col + ocupa]) * unidad
            fondo = CABECERA if cabecera else GRIS if gris else None
            if fondo:
                cr.set_source_rgb(*fondo)
                cr.rectangle(x, y, w, alto)
                cr.fill()
            cr.set_source_rgb(*BORDE)
            cr.set_line_width(0.5)
            cr.rectangle(x, y, w, alto)
            cr.stroke()
            capa = self._capa(contexto, texto, w, tabla.tamano, cabecera)
            if col in tabla.alinear_derecha:
                capa.set_alignment(Pango.Alignment.RIGHT)
            if cabecera:
                cr.set_source_rgb(*ACENTO)
            elif gris or texto == "Sin asignar":
                cr.set_source_rgb(0.4, 0.4, 0.4)
            else:
                cr.set_source_rgb(0, 0, 0)
            cr.move_to(x + self.MARGEN_CELDA, y + self.MARGEN_CELDA)
            PangoCairo.show_layout(cr, capa)
            x += w
            col += ocupa
        return y + alto


def operacion(informe: Informe) -> Gtk.PrintOperation:
    op = Gtk.PrintOperation(unit=Gtk.Unit.POINTS, job_name=informe.titulo, embed_page_setup=True)
    pagina = Gtk.PageSetup()
    pagina.set_paper_size(Gtk.PaperSize.new(Gtk.PAPER_NAME_A4))
    pagina.set_orientation(Gtk.PageOrientation.LANDSCAPE if informe.horizontal else Gtk.PageOrientation.PORTRAIT)
    for borde in (Gtk.Unit.MM,):
        pagina.set_top_margin(10, borde)
        pagina.set_bottom_margin(10, borde)
        pagina.set_left_margin(10, borde)
        pagina.set_right_margin(10, borde)
    op.set_default_page_setup(pagina)
    dibujante = Dibujante(informe)
    op.connect("begin-print", dibujante.paginar)
    op.connect("draw-page", dibujante.dibujar)
    op.dibujante = dibujante
    return op


def imprimir(ventana, tipo: str, cal: dict, horarios: list[dict], mes: date, pdf: str | None = None) -> None:
    """Abre el diálogo de impresión (o, con `pdf`, guarda directamente ese PDF: pruebas)."""
    informe = informe_calendario(cal, horarios, mes) if tipo == "calendario" else informe_roles(cal, mes)
    if cal["estado"] == "SIN_GENERAR":
        ventana.error("Este mes aún no tiene calendario")
        return
    op = operacion(informe)
    if pdf:
        op.set_export_filename(pdf)
        op.run(Gtk.PrintOperationAction.EXPORT, ventana)
    else:
        op.run(Gtk.PrintOperationAction.PRINT_DIALOG, ventana)
