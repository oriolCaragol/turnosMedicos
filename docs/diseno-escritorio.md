# turnosMedicos — Diseño del modo escritorio GNOME (Flatpak)

| | |
|---|---|
| Estado | v1.1 — implementado (cambios respecto a la v1.0 en la sección 16) |
| Fecha | 2026-10-16 |
| Parte de | v2.6 |
| Relacionado | [diseno.md](diseno.md), [documentacion-tecnica.md](documentacion-tecnica.md) |

## 1. Objetivo

Que la aplicación pueda usarse también como **aplicación nativa de GNOME**:
con ventana propia, en el menú de aplicaciones de **todos los usuarios** del
equipo y sin terminal ni navegador, distribuida como **Flatpak**.

Debe convivir siempre con el **modo web** actual. Los dos modos comparten un
único núcleo (motor, datos, API e interfaz), de modo que cualquier mejora
llega a ambos.

## 2. Decisiones de partida

| # | Decisión | Motivo |
|---|---|---|
| E1 | Ventana GTK4/libadwaita con WebKitGTK que muestra la interfaz actual | Reutiliza todo lo construido; integración nativa (ventana, menú, tema, diálogos). |
| E2 | Distribución como Flatpak, instalado a nivel de sistema (`--system`) | Estándar en GNOME/Fedora; aparece en el menú de todos los usuarios; incluye sus dependencias. |
| E3 | Datos locales por usuario, sin acceso concurrente | Así lo ha decidido el usuario: cada usuario tiene su propio calendario. |
| E4 | Los dos modos usan **la misma carpeta de datos** del usuario | Alternar entre web y escritorio no duplica ni pierde datos. |
| E5 | Una sola versión y una sola etiqueta para los dos modos | Evita que se separen; la base de datos siempre es compatible. |

## 3. Entorno comprobado (2026-10-16)

| Pieza | En el sistema (Fedora 43) | En el runtime Flatpak |
|---|---|---|
| Runtime | `org.gnome.Platform` 50 y **51** ya instalados (Flathub) | GNOME **51** |
| Python | 3.14 (el `.venv` del proyecto) | **3.14.7**: el mismo, así que valen las mismas ruedas de OR-Tools |
| WebKitGTK (API 6.0) | 2.52 | 2.54 |
| libadwaita | 1.8 | 1.10 |
| PyGObject | 3.54 (`python3-gobject`) | incluido |
| `flatpak-builder` | **no instalado** | hace falta para compilar el Flatpak (sección 11) |
| SDK | — | `org.gnome.Sdk//51` disponible en Flathub (873 MB) |

## 4. Arquitectura

```
                 ┌──────────────── núcleo común (sin cambios) ────────────────┐
                 │  interfaz React  ──▶  API FastAPI  ──▶  servicios  ──▶ motor│
                 │                                           └──▶ datos SQLite│
                 └─────────────────────────────────────────────────────────────┘
                          ▲                                  ▲
       modo web           │                 modo escritorio  │
  ┌─────────────────────┐ │             ┌───────────────────┐ │
  │ turnos              │ │             │ turnos-escritorio │ │
  │  arranque.web       │─┘             │  arranque.        │─┘
  │  · servidor (hilo   │               │   escritorio      │
  │    principal)       │               │  · Adw.Application│
  │  · abre el navegador│               │  · ventana WebKit │
  └─────────────────────┘               │  · servidor en un │
              ▲                         │    hilo           │
              └──── arranque.servidor ──┴───────────────────┘
                    (compartido: puerto, token, datos, migraciones)
```

## 5. Estructura del código

```
src/turnos/
  dominio/ motor/ datos/ servicios/ api/ exportar/   ← núcleo (sin cambios funcionales)
  config.py            ← ruta de datos común a los dos modos (sección 8)
  arranque/
    __init__.py
    servidor.py        ← NUEVO: crear y arrancar el servidor (compartido)
    web.py             ← lo que hoy hace __main__.py
    escritorio/        ← NUEVO: solo se importa en el modo escritorio
      __init__.py      ← main(): comprueba GTK y lanza la aplicación
      aplicacion.py    ← Adw.Application: una instancia, servidor, atajos, «Acerca de»
      ventana.py       ← Adw.ApplicationWindow + WebKit.WebView
      descargas.py     ← descargas → diálogo «Guardar como»
      errores.py       ← textos de la página de error si el servidor no arranca
      estado.py        ← tamaño de la ventana (ventana.json)
  __main__.py          ← llama a arranque.web.main (compatibilidad)
interfaz/              ← una sola interfaz para los dos modos
empaquetado/
  flatpak/
    io.oriol.TurnosMedicos.yml        ← manifiesto
    io.oriol.TurnosMedicos.desktop
    io.oriol.TurnosMedicos.metainfo.xml
    python3-dependencias.json                ← generado (scripts/generar-dependencias-flatpak.py)
    iconos/ (scalable + symbolic, SVG)
scripts/
  empaquetar-flatpak.sh   ← compila la interfaz, la rueda de la aplicación y el Flatpak
  generar-dependencias-flatpak.py   ← ruedas cp314 de las dependencias, con sha256
```

Órdenes (`pyproject.toml`):

| Orden | Modo |
|---|---|
| `turnos` | web, como ahora |
| `turnos-escritorio` | ventana GNOME (requiere PyGObject, GTK4, libadwaita y WebKitGTK) |

PyGObject **no** se añade a las dependencias de `pip`: en el Flatpak lo aporta
el runtime, y para desarrollar el modo escritorio fuera del Flatpak se usa el
`python3-gobject` del sistema (sección 12).

## 6. Arranque compartido (`arranque/servidor.py`)

```python
@dataclass
class Servidor:
    url: str        # http://127.0.0.1:<puerto>/?token=<token>
    puerto: int
    token: str
    def detener(self) -> None: ...

def arrancar(puerto: int = 0, en_hilo: bool = False) -> Servidor:
    """Inicializa la base de datos (migraciones con copia previa), crea la app y
    arranca Uvicorn en 127.0.0.1. Puerto 0 = uno libre al azar."""
```

- **Puerto:** en el modo escritorio, siempre aleatorio (0). En el modo web se
  mantiene el 8000 por defecto (configurable con `TURNOS_PUERTO`), y se
  admite 0.
- **Token:** `secrets.token_urlsafe(32)`, uno nuevo en cada arranque.
- **Ruta de la interfaz:** la interfaz compilada se busca en
  `TURNOS_INTERFAZ`, o junto al código en desarrollo. Hoy la ruta se calcula a
  partir de la carpeta del repositorio, cosa que no funciona una vez
  instalado; en el Flatpak se fija con la variable
  (`/app/share/turnos-medicos/interfaz`).
- **Espera a estar listo:** `arrancar` devuelve cuando Uvicorn ya acepta
  conexiones (`server.started`), para no cargar la ventana antes de tiempo.
- **Parada limpia:** `detener()` pone `should_exit` y espera al hilo.

## 7. Seguridad del servidor local

Problema: en un equipo con varios usuarios, cualquier usuario local puede
conectarse a `127.0.0.1:<puerto>` de otro.

Solución (para los dos modos):

1. **Token por sesión.** La primera petición lleva `?token=…` en la URL. El
   servidor responde poniendo una cookie `turnos_sesion` (`HttpOnly`,
   `SameSite=Strict`, válida para `127.0.0.1:<puerto>`) y redirige a la misma
   ruta sin el token.
2. **Middleware** que rechaza con 401 cualquier petición sin la cookie (o sin
   la cabecera `X-Turnos-Token`, para las pruebas y herramientas).
3. Puerto aleatorio en el modo escritorio: nadie puede adivinarlo de antemano.
4. Solo escucha en `127.0.0.1`, como ahora.
5. El modo web abre el navegador con la URL que lleva el token. Desactivable
   con `TURNOS_SIN_TOKEN=1`, solo para desarrollo.

Mejora posible a futuro, no incluida: un esquema propio `turnos://`
(`WebKit.WebContext.register_uri_scheme`) que pase las peticiones directamente
a la aplicación ASGI dentro del proceso, sin abrir ningún puerto.

## 8. Datos

### 8.1 Ubicación

Los dos modos usan **`~/.local/share/turnosMedicos/turnos.sqlite`**.

- Dentro de Flatpak, `XDG_DATA_HOME` apunta a `~/.var/app/<id>/data`, así que
  `config.ruta_datos()` no puede usarlo sin más. Si está definida
  `FLATPAK_ID`, la ruta se calcula a partir de `Path.home()`:
  `~/.local/share/turnosMedicos`.
- El Flatpak solo recibe acceso a esa carpeta:
  `--filesystem=xdg-data/turnosMedicos:create`.
- `TURNOS_DATOS` sigue permitiendo cambiarla en los dos modos.

### 8.2 Compatibilidad de versiones

Riesgo: si una versión nueva actualiza la base de datos (migración) y después
se abre con una versión antigua del otro modo, la antigua no conoce las tablas
nuevas.

- Al arrancar, si la revisión de la base de datos **no existe** entre las
  migraciones de la versión que arranca (es decir, es más nueva), no se toca
  nada y se muestra un aviso claro: «Estos datos son de una versión más
  reciente de turnosMedicos. Actualiza la aplicación.». En el modo escritorio
  aparece en la ventana; en el web, en el terminal y en la página.
- Manteniendo una sola versión para los dos modos (E5) no debería pasar.

### 8.3 Uso simultáneo de los dos modos

No hay usuarios concurrentes (E3), pero un mismo usuario podría abrir los dos
modos a la vez. SQLite lo soporta. Además:

- se activa `PRAGMA busy_timeout` para esperar en lugar de fallar si el otro
  modo está escribiendo;
- no se añade bloqueo exclusivo, porque no compensa la complejidad.

## 9. Modo escritorio

### 9.1 Aplicación y ventana

| Aspecto | Diseño |
|---|---|
| Identificador | `io.oriol.TurnosMedicos` |
| Clase | `Adw.Application`, con una sola instancia: lanzarla de nuevo enfoca la ventana abierta |
| Ventana | `Adw.ApplicationWindow` con `WebKit.WebView` a pantalla completa. La interfaz ya trae su propia cabecera, así que no se duplica: la barra de título de GNOME solo muestra el título y los botones |
| Título | El de la página (`notify::title`), por ejemplo «Turnos médicos» |
| Tamaño | Se recuerda el tamaño y si estaba maximizada, en `~/.config/turnosMedicos/ventana.json` (sin GSettings, para no compilar esquemas) |
| Tema | WebKit transmite `prefers-color-scheme` según el tema de GNOME (`Adw.StyleManager`); la interfaz ya lo usa |
| Atajos | Ctrl+Q para salir, Ctrl+R para recargar, Ctrl+P para imprimir y Ctrl+± para el zoom. Ctrl+Z y Ctrl+Y siguen siendo de la interfaz |

### 9.2 Ciclo de vida

1. `activate`: arranca el servidor en un hilo (`arrancar(puerto=0, en_hilo=True)`).
   Mientras tanto se ve una pantalla «Abriendo turnos…» (`Adw.StatusPage` con
   indicador de carga).
2. Cuando está listo, el WebView carga `servidor.url`.
3. Si falla (puerto, migración, datos más nuevos…), se muestra una página de
   error con el motivo y el botón «Copiar detalles».
4. Al cerrar la ventana: `webview.try_close()`. Así la página ejecuta
   `pagehide` y **envía los guardados pendientes**, el mismo mecanismo que se
   corrigió en la v2.1. Cuando WebKit emite `close`, se detiene el servidor y
   se sale.

### 9.3 Navegación, descargas e impresión

| Caso | Comportamiento |
|---|---|
| Enlaces internos | En la misma ventana |
| Enlaces externos (`http(s)` a otro sitio) | Se abren en el navegador del sistema (`Gtk.UriLauncher`) y no en la ventana |
| Descargas (XLSX, copia de seguridad) | Señal `download-started` → diálogo nativo «Guardar como» (`Gtk.FileDialog`) con el nombre sugerido → aviso «Guardado en …» |
| «Imprimir / PDF» | `window.print()` abre el diálogo de impresión de GTK, que permite «Imprimir a fichero (PDF)» |
| Menú contextual | Se quitan «Atrás», «Recargar» e «Inspeccionar»; se mantienen copiar y pegar |
| Herramientas de desarrollo | Solo con `TURNOS_DEPURAR=1` |

### 9.4 Interfaz React

No necesita cambios para el modo escritorio, y esa es la regla: **la interfaz
no sabe en qué modo corre**. Descargas e impresión funcionan como en la web,
y el envoltorio las intercepta. Si algún día hiciera falta algo propio de un
modo, se detectaría la capacidad en lugar de bifurcar el código.

## 10. Integración con el escritorio

- **`.desktop`**:
  - `Name=Turnos médicos`, `Comment=Asigna los turnos de mañana y tarde del equipo`;
  - `Categories=Office;Calendar;`, `Keywords=turnos;médicos;guardias;calendario;horario;`;
  - `StartupNotify=true`, `SingleMainWindow=true`.
- **Icono**: SVG de un calendario con una cruz médica, en la paleta de la
  aplicación, más su versión simbólica. Se diseñará aparte (sección 15).
- **AppStream** (`metainfo.xml`): resumen, descripción, capturas (las de
  `docs/imagenes`), licencia, notas de versión y `content_rating`. Es lo que
  muestra GNOME Software.

## 11. Empaquetado Flatpak

### 11.1 Manifiesto (resumen)

```yaml
id: io.oriol.TurnosMedicos
runtime: org.gnome.Platform
runtime-version: "51"
sdk: org.gnome.Sdk
command: turnos-escritorio
finish-args:
  - --socket=wayland
  - --socket=fallback-x11
  - --share=ipc
  - --device=dri
  - --filesystem=xdg-data/turnosMedicos:create
  - --env=TURNOS_INTERFAZ=/app/share/turnos-medicos/interfaz
  # Sin --share=network: servidor y ventana se comunican por el bucle local del propio entorno aislado.
  # (Desde la v2.7 se añade --share=network para buscar los festivos oficiales; ver documentación técnica.)
modules:
  - python3-dependencias.json      # OR-Tools, FastAPI, SQLAlchemy, Alembic, openpyxl… (ruedas cp314)
  - name: turnos
    buildsystem: simple
    build-commands:
      - pip3 install --no-deps --no-build-isolation --prefix=/app .
      - install -Dm644 empaquetado/flatpak/*.desktop -t /app/share/applications/
      - install -Dm644 empaquetado/flatpak/*.metainfo.xml -t /app/share/metainfo/
      - install -Dm644 empaquetado/flatpak/iconos/*.svg -t /app/share/icons/hicolor/scalable/apps/
      - cp -r interfaz/dist /app/share/turnos-medicos/interfaz
    sources:
      - type: dir
        path: ../..
```

- La interfaz se compila **antes**, con `npm run build` en el script. El
  empaquetado no necesita Node ni red: usa `interfaz/dist`.
- Las dependencias de Python se fijan a las versiones del proyecto con
  `flatpak-pip-generator`, a partir de `pip freeze` del `.venv`.
- Por verificar al implementar: que el bucle local funciona sin
  `--share=network`. Lo esperado es que sí; si no, se añadiría ese permiso.

### 11.2 Tamaño estimado

| Parte | Tamaño |
|---|---|
| Runtime GNOME 51 | ya instalado en el equipo (compartido con otras aplicaciones) |
| Dependencias de Python | ~300 MB instaladas (OR-Tools 80 MB, pandas 72 MB, numpy 43 MB…) |
| Aplicación e interfaz | < 5 MB |

### 11.3 Compilación, instalación y actualización

```sh
scripts/empaquetar-flatpak.sh                 # interfaz + dependencias + flatpak-builder → repo local
flatpak build-bundle repo turnos-medicos.flatpak io.oriol.TurnosMedicos
sudo flatpak install --system turnos-medicos.flatpak     # en el menú de todos los usuarios
```

- **Requisito**: `flatpak-builder` (`sudo dnf install flatpak-builder`) y el
  SDK `org.gnome.Sdk//51` (se descarga una vez).
- **Actualizar**: generar el paquete de la nueva versión e instalarlo de nuevo.
  Las migraciones actualizan los datos al abrirla, con copia previa.
- **Más adelante**, si se quiere que GNOME Software avise de las
  actualizaciones: un repositorio Flatpak propio (fuera de alcance).

## 12. Desarrollo

| Tarea | Cómo |
|---|---|
| Modo web | Igual que ahora: `.venv/bin/turnos` y `npm run dev` |
| Modo escritorio sin Flatpak | Crear el entorno con acceso a los paquetes del sistema: `python3 -m venv --system-site-packages .venv`. Así ve el `python3-gobject` de Fedora. Luego `.venv/bin/turnos-escritorio` |
| Flatpak | `scripts/empaquetar-flatpak.sh` y `flatpak run io.oriol.TurnosMedicos` |

Recrear el `.venv` con `--system-site-packages` no afecta al modo web; las
versiones fijadas del proyecto tienen prioridad sobre las del sistema.

## 13. Pruebas

| Nivel | Qué | Cómo |
|---|---|---|
| Núcleo | Lo de siempre (139 pruebas) | `pytest` |
| Arranque compartido | Puerto aleatorio; token obligatorio (401 sin él, cookie tras `?token=`); parada limpia; datos de una versión más nueva rechazados con mensaje | `pytest` (nuevas) |
| Interfaz | Lo de siempre (27 pruebas) | `vitest` |
| Flujo completo | Las 15 pruebas actuales, **también con el motor WebKit** de Playwright, el más cercano a WebKitGTK | `scripts/e2e.sh` con `--project=chromium` y `--project=webkit` |
| Envoltorio | Prueba de humo: arranca sin pantalla (`GDK_BACKEND=broadway` o `xvfb-run`), carga la interfaz, cierra y comprueba que el servidor se ha detenido | `pytest` marcada como `escritorio`, se salta si no hay GTK |
| Manual | Lista de comprobación: menú de aplicaciones, icono, una sola instancia, descargas, impresión, tema oscuro, cierre con cambios pendientes, otro usuario del equipo | `docs/` |

## 14. Plan de implementación

| Fase | Contenido | Resultado verificable |
|---|---|---|
| 1 | `arranque/servidor.py` y `arranque/web.py`; token y cookie; ruta de la interfaz configurable; comprobación de versión de datos; `busy_timeout` | Modo web igual que ahora pero con token; pruebas nuevas en verde |
| 2 | Envoltorio GTK: aplicación, ventana, ciclo de vida, cierre con guardados pendientes, enlaces externos, descargas, impresión, estado de la ventana | `turnos-escritorio` funciona fuera de Flatpak (con `--system-site-packages`) |
| 3 | `.desktop`, icono y AppStream | Validación con `desktop-file-validate` y `appstreamcli validate` |
| 4 | Manifiesto Flatpak, dependencias generadas y script de empaquetado | Instalación de prueba con `--system`; aparece en el menú de otro usuario |
| 5 | Pruebas con WebKit y prueba de humo del envoltorio; guía de uso y documentación técnica | Todas las pruebas en verde; guía con la instalación y el uso del modo escritorio |

## 15. Decisiones

| # | Pregunta | Decisión |
|---|---|---|
| D-E1 | Identificador de la aplicación | `io.oriol.TurnosMedicos` |
| D-E2 | Icono | Calendario con cruz médica en el verde azulado de la aplicación, dibujado para el proyecto (SVG normal y simbólico) |
| D-E3 | ¿Token también en el modo web? | Sí (sección 7); desactivable solo para desarrollo |
| D-E4 | Distribución | Fichero `.flatpak` que se instala con `sudo flatpak install --system`; repositorio propio, más adelante si hace falta |
| D-E5 | ¿Publicar en Flathub? | No por ahora: exige revisión, licencia y mantenimiento públicos |

## 16. Cambios durante la implementación

| Tema | v1.0 | Implementado | Motivo |
|---|---|---|---|
| API del arranque | `arrancar(puerto, en_hilo) -> Servidor` | `preparar(puerto, con_token, ruta) -> Servidor`, con `ejecutar()` (primer plano), `iniciar_en_hilo()`, `esperar_peticiones()` y `detener()` | El puerto se reserva al preparar, así la URL se conoce antes de arrancar y un puerto ocupado falla pronto |
| Cierre | `webview.try_close()` | La vista navega a `about:blank`, espera a que termine la carga y a las peticiones en curso del servidor, y sale | La prueba de humo demostró que `try_close()` emite `close` **sin** descargar la página: `pagehide` no se ejecutaba y se perdían los guardados pendientes. Navegar fuera sí lo ejecuta |
| Sesión del WebView | — | Efímera (sin caché ni cookies en disco) y **sin proxy** | Los datos están en SQLite; la cookie de sesión vale solo para ese arranque. Sin permiso de red, el portal que resuelve el proxy rechaza la consulta («This call is not available inside the sandbox») y la página no cargaba; para 127.0.0.1 nunca hace falta proxy |
| `flatpak-builder` | — | Con `--disable-rofiles-fuse` | El montaje FUSE falla de forma intermitente en la carpeta del proyecto (sobre todo si está sincronizada con la nube) |
| Dependencias | `flatpak-pip-generator` | `scripts/generar-dependencias-flatpak.py` (`pip install --dry-run --report` para cp314/manylinux) | Elegir la plataforma de las ruedas y fijar las versiones del `.venv` |
| Fuente de la aplicación en el manifiesto | Carpeta del repositorio (`../..`) | `build/flatpak/fuentes`: la rueda de `turnos` y la interfaz compilada | No copiar `.venv`, `node_modules` ni `.git` al entorno de compilación |
| AppStream | Con capturas | Sin capturas ni página web | AppStream exige URL públicas y el proyecto no está publicado. Queda un aviso de `appstreamcli` por la página web y otro, pedante, por las mayúsculas del identificador |
| Pruebas | Playwright también con WebKit | Prueba de humo con la ventana GTK real (Xvfb), `pytest -m escritorio` | Prueba el WebKitGTK de verdad (el de Playwright no está soportado en Fedora) y detectó el fallo del cierre |
| Entorno de desarrollo | Recrear el `.venv` con `--system-site-packages` | Basta con `include-system-site-packages = true` en `.venv/pyvenv.cfg` | Mismo efecto sin reinstalar |

### Comprobado con el paquete instalado

`scripts/empaquetar-flatpak.sh --instalar` genera un paquete de 58 MB
(258 MB instalado). La prueba de humo se ejecutó dentro de la aplicación
instalada (`flatpak run --command=python3 io.oriol.TurnosMedicos …`, con Xvfb
y datos temporales): carga la interfaz por el bucle local **sin permiso de
red**, la cookie de sesión funciona, el guardado de `pagehide` llega al
cerrar y el servidor se detiene. Sin `TURNOS_DATOS`, la ruta de datos es
`~/.local/share/turnosMedicos/turnos.sqlite`, la misma que el modo web.

