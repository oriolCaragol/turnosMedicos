"""La ventana del lanzador de Windows (Tkinter, que viene con Python).

1. «¿Dónde quieres trabajar?»: en este equipo o en un servidor de la red (los
   anunciados por mDNS, el último usado u otra dirección). Con «Recordar mi elección»
   no vuelve a preguntar (se recuerda en %APPDATA%\\TurnosMedicos\\conexion.json).
2. En este equipo: arranca el servidor interno y abre el navegador. La ventana queda
   para volver a abrirlo o cerrar la aplicación (al cerrar, se detiene el servidor).
   Si ya estaba abierta, otro arranque solo abre el navegador (instancia única).
3. En un servidor: abre su dirección en el navegador (el certificado de su autoridad
   se instala en Windows desde la página de entrada del servidor).
"""

import json
import os
import threading
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import messagebox, ttk

from turnos import __version__
from turnos.arranque import conexion as cx
from turnos.config import ruta_datos

TITULO = "Turnos médicos"


def _fichero_abierto():
    return ruta_datos().parent / "abierto.json"


def _ya_abierto() -> str | None:
    """Dirección de una instancia que ya está en marcha (si responde)."""
    try:
        datos = json.loads(_fichero_abierto().read_text(encoding="utf-8"))
        with urllib.request.urlopen(f"http://127.0.0.1:{datos['puerto']}/api/estado", timeout=2):
            pass  # sin token responde 401: basta con que responda
    except urllib.error.HTTPError:
        return datos["url"]
    except (OSError, ValueError, KeyError):
        return None
    return datos["url"]


class Lanzador:
    def __init__(self) -> None:
        self.servidor = None
        self.url: str | None = None
        self.raiz = tk.Tk()
        self.raiz.title(TITULO)
        self.raiz.minsize(460, 300)
        self.raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        estilo = ttk.Style(self.raiz)
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 15, "bold"))
        estilo.configure("Nota.TLabel", foreground="#56676f")
        self.marco = ttk.Frame(self.raiz, padding=18)
        self.marco.pack(fill="both", expand=True)

    def ejecutar(self) -> None:
        anterior = _ya_abierto()
        if anterior:
            webbrowser.open(anterior)
            self.raiz.destroy()
            return
        conexion = cx.leer()
        if not conexion.preguntar:
            self.raiz.after(10, lambda: self._iniciar(conexion))
        else:
            self._pantalla_inicio(conexion)
        self.raiz.mainloop()

    def _limpiar(self) -> None:
        for hijo in self.marco.winfo_children():
            hijo.destroy()

    # --- Dónde trabajar ------------------------------------------------------------------

    def _pantalla_inicio(self, actual: cx.Conexion) -> None:
        self._limpiar()
        ttk.Label(self.marco, text="¿Dónde quieres trabajar?", style="Titulo.TLabel").pack(anchor="w")
        ttk.Button(self.marco, text="En este equipo", command=lambda: self._elegir_local(actual)).pack(
            fill="x", pady=(12, 2))
        ttk.Label(self.marco, text="Los datos y el motor en este ordenador, solo para ti.", style="Nota.TLabel").pack(anchor="w")

        ttk.Label(self.marco, text="En un servidor de la red", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(16, 2))
        self.lista = tk.Listbox(self.marco, height=4, activestyle="dotbox")
        self.lista.pack(fill="x")
        self.direcciones: list[str] = []
        if actual.direccion:
            self._anadir_servidor("Último usado", actual.direccion)
        self.lista.bind("<Double-Button-1>", lambda _e: self._elegir_de_la_lista(actual))
        fila = ttk.Frame(self.marco)
        fila.pack(fill="x", pady=(6, 0))
        self.otra = ttk.Entry(fila)
        self.otra.insert(0, "turnos.local:8443")
        self.otra.pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Abrir", command=lambda: self._elegir_servidor(self.otra.get(), actual)).pack(
            side="left", padx=(6, 0))
        self.buscando = ttk.Label(self.marco, text="Buscando servidores en la red…", style="Nota.TLabel")
        self.buscando.pack(anchor="w")

        self.recordar = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.marco, text="Recordar mi elección y no volver a preguntar",
                        variable=self.recordar).pack(anchor="w", pady=(14, 0))
        ttk.Label(self.marco, text=f"Versión {__version__}", style="Nota.TLabel").pack(anchor="e", pady=(8, 0))

        def buscar() -> None:
            encontrados = cx.buscar_servidores()
            self.raiz.after(0, lambda: self._encontrados(encontrados))

        threading.Thread(target=buscar, daemon=True).start()

    def _anadir_servidor(self, nombre: str, direccion: str) -> None:
        if direccion in self.direcciones:
            return
        self.direcciones.append(direccion)
        self.lista.insert("end", f"{nombre} — {direccion}")

    def _encontrados(self, encontrados) -> None:
        if not self.buscando.winfo_exists():
            return
        for nombre, direccion in encontrados:
            self._anadir_servidor(nombre, cx.normalizar(direccion))
        self.buscando.configure(text="" if self.direcciones else
                                "No se ha encontrado ninguno: escribe la dirección que muestra el servidor.")

    def _elegir_de_la_lista(self, actual: cx.Conexion) -> None:
        seleccion = self.lista.curselection()
        if seleccion:
            self._elegir_servidor(self.direcciones[seleccion[0]], actual)

    def _elegir_local(self, actual: cx.Conexion) -> None:
        conexion = cx.Conexion("personal", actual.direccion, actual.huella, actual.usuario, not self.recordar.get())
        cx.guardar(conexion)
        self._iniciar(conexion)

    def _elegir_servidor(self, texto: str, actual: cx.Conexion) -> None:
        try:
            direccion = cx.normalizar(texto)
        except ValueError as error:
            messagebox.showerror(TITULO, str(error), parent=self.raiz)
            return
        conexion = cx.Conexion("servidor", direccion, actual.huella if actual.direccion == direccion else "",
                               actual.usuario, not self.recordar.get())
        cx.guardar(conexion)
        self._iniciar(conexion)

    def _iniciar(self, conexion: cx.Conexion) -> None:
        if conexion.en_servidor:
            self.url = conexion.direccion + "/"
            webbrowser.open(self.url)
            self._pantalla_abierta(f"Turnos médicos del servidor\n{conexion.direccion}",
                                   "Si el navegador avisa de que la conexión no es segura, instala el certificado del "
                                   "servidor: lo explica su página de entrada.")
            return
        self._limpiar()
        ttk.Label(self.marco, text="Abriendo Turnos médicos…", style="Titulo.TLabel").pack(anchor="w")
        threading.Thread(target=self._arrancar, daemon=True).start()

    # --- Este equipo -----------------------------------------------------------------------

    def _arrancar(self) -> None:
        from turnos.arranque.servidor import preparar
        from turnos.datos.bd import DatosMasNuevos

        try:
            servidor = preparar(puerto=0)
            servidor.iniciar_en_hilo()
        except DatosMasNuevos as error:
            texto = str(error)
            self.raiz.after(0, lambda: self._fallo(texto))
            return
        except Exception as error:  # noqa: BLE001 — se muestra
            texto = f"No se ha podido arrancar: {error}"
            self.raiz.after(0, lambda: self._fallo(texto))
            return
        self.servidor, self.url = servidor, servidor.url
        try:
            _fichero_abierto().write_text(json.dumps({"puerto": servidor.puerto, "url": servidor.url, "pid": os.getpid()}),
                                          encoding="utf-8")
        except OSError:
            pass
        webbrowser.open(servidor.url)
        self.raiz.after(0, lambda: self._pantalla_abierta(
            "Turnos médicos está abierto en el navegador",
            f"Los datos están en {ruta_datos()}.\nAl cerrar esta ventana se cierra la aplicación."))

    def _fallo(self, texto: str) -> None:
        messagebox.showerror(TITULO, texto, parent=self.raiz)
        self.raiz.destroy()

    def _pantalla_abierta(self, titulo: str, nota: str) -> None:
        self._limpiar()
        ttk.Label(self.marco, text=titulo, style="Titulo.TLabel", wraplength=420, justify="left").pack(anchor="w")
        ttk.Label(self.marco, text=nota, style="Nota.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=(8, 14))
        ttk.Button(self.marco, text="Abrir en el navegador", command=lambda: webbrowser.open(self.url)).pack(fill="x")
        ttk.Button(self.marco, text="Cambiar dónde trabajar…", command=self._cambiar).pack(fill="x", pady=(6, 0))
        ttk.Button(self.marco, text="Cerrar Turnos médicos", command=self.cerrar).pack(fill="x", pady=(6, 0))

    def _cambiar(self) -> None:
        self._detener()
        conexion = cx.leer()
        conexion.preguntar = True
        cx.guardar(conexion)
        self._pantalla_inicio(conexion)

    def _detener(self) -> None:
        if self.servidor is not None:
            self.servidor.esperar_peticiones()
            self.servidor.detener()
            self.servidor = None
            try:
                _fichero_abierto().unlink()
            except OSError:
                pass

    def cerrar(self) -> None:
        self._detener()
        self.raiz.destroy()
