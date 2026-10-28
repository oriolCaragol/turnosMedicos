"""Textos de los errores de arranque que se muestran en la ventana."""

import traceback

from turnos.datos.bd import DatosMasNuevos


def explicar(error: BaseException) -> tuple[str, str]:
    """(título, descripción) para la página de error."""
    causa = error.__cause__ or error
    if isinstance(causa, DatosMasNuevos):
        return "Datos de una versión más reciente", str(causa)
    if isinstance(causa, OSError):
        return (
            "No se ha podido abrir",
            f"El servidor interno no ha podido arrancar ({causa.strerror or causa}).",
        )
    return (
        "No se ha podido abrir",
        "Ha ocurrido un error inesperado al arrancar. Copia los detalles si necesitas ayuda.",
    )


def detalles(error: BaseException) -> str:
    """Texto completo para «Copiar detalles»."""
    return "".join(traceback.format_exception(error)).strip()
