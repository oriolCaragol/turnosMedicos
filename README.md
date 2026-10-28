# turnosMedicos

Planificador de los turnos de mañana y tarde de un equipo médico (de lunes a
viernes). Un motor de optimización (OR-Tools CP-SAT) reparte los turnos
respetando la disponibilidad de cada médico, sus ausencias, la carga mensual, la
cobertura mínima y máxima de cada turno, los festivos y el reparto equitativo de
urgencias y domicilios; después se retoca a mano, arrastrando, y se publica.

El mismo núcleo se usa de cuatro formas:

- **Aplicación de escritorio GNOME** (Flatpak), con los datos en el propio
  ordenador. Hay dos interfaces: la web dentro de una ventana y una nativa (GTK 4
  y libadwaita).
- **Windows** (`TurnosMedicos.exe`, sin instalar nada): los datos en el propio
  ordenador y la interfaz en el navegador; también puede conectarse a un servidor.
  Ver [docs/windows.md](docs/windows.md).
- **Web local** en el navegador (`turnos`).
- **Servidor en la red de casa** (`turnos servidor`, en un PC o una Raspberry Pi):
  varios usuarios a la vez, cuentas para planificadores y médicos, los médicos
  consultan sus turnos desde el móvil y proponen cambios, con HTTPS y certificado
  propio. Las aplicaciones de escritorio pueden trabajar contra él.

Viene con los festivos de **Madrid** precargados; para otro municipio se buscan
sus festivos oficiales desde *Configuración*. Todo está en español.

![Calendario](docs/imagenes/calendario.png)

## Estructura

- `src/` — código fuente
- `tests/` — pruebas
- `docs/` — documentación

## Documentación

- [Guía de uso](docs/guia-de-uso.md) — para el planificador
- [Arquitectura](docs/arquitectura.md) — cómo encajan las piezas y por qué
- [Pruebas automáticas](docs/pruebas.md) — qué se prueba, cómo ejecutarlas y cómo ampliarlas
- [Manual de mantenimiento](docs/mantenimiento.md) — cada componente en detalle, cómo se usa, por qué se eligió y cómo modificarlo
- [Documentación técnica](docs/documentacion-tecnica.md) — instalación, arquitectura, operación e historia de la construcción
- [Especificaciones](docs/especificaciones.md)
- [Diseño técnico](docs/diseno.md)
- [Diseño del modo escritorio](docs/diseno-escritorio.md)
- [Diseño del modo servidor](docs/diseno-servidor.md) — núcleo en un equipo de la red doméstica (fases 1 a 5)
- [Guía del modo servidor](docs/guia-servidor.md) — para el administrador: arrancarlo, certificado, cuentas, solicitudes y copias
- [Instalación en la Raspberry Pi](docs/instalacion-raspberry.md) — reinstalar con 64 bits (conservando otros servicios, como Pi-hole), desplegar y actualizar
- [Interfaz nativa GNOME](docs/prototipo-gnome-nativo.md) — alternativa completa a la interfaz web, para comparar
- [Windows](docs/windows.md) — instalar y usar `TurnosMedicos.exe`, y cómo se construye

## Puesta en marcha

Requisitos: Python ≥ 3.13 y Node.js (solo para compilar la interfaz).

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
(cd interfaz && npm ci && npm run build)
.venv/bin/turnos          # arranca en http://127.0.0.1:8000 y abre el navegador
```

Los datos se guardan en `~/.local/share/turnosMedicos/turnos.sqlite` (se
cambia con `TURNOS_DATOS`). Otras variables: `TURNOS_PUERTO`,
`TURNOS_SIN_NAVEGADOR=1`.

### Aplicación de escritorio (Flatpak)

Requisitos para empaquetar: `sudo dnf install flatpak-builder` (el guion
ofrece instalar el SDK de GNOME 51 la primera vez).

```sh
scripts/empaquetar-flatpak.sh                       # → build/turnos-medicos-<versión>.flatpak
flatpak install --user build/turnos-medicos-*.flatpak   # o sudo flatpak install --system … para todos
```

Necesita la plataforma GNOME 51 de Flathub. Al abrirla se elige dónde trabajar:
en este equipo (cada usuario tiene sus propios datos, en la misma ruta que el
modo web) o contra un servidor de la red. Instálala solo de una forma (usuario o
sistema): si están las dos, se abre la de usuario.

### Windows

```sh
scripts/construir-windows.sh      # → build/turnos-medicos-<versión>-windows.zip (con Wine, en podman)
```

O en GitHub: el flujo *Windows* (`.github/workflows/windows.yml`) lo construye en
un Windows de verdad y lo adjunta a cada versión etiquetada. Ver
[docs/windows.md](docs/windows.md).

### Servidor en la red de casa

```sh
.venv/bin/pip install -e '.[servidor]'
.venv/bin/turnos servidor crear-administrador
.venv/bin/turnos servidor                 # https://turnos.local:8443/
```

Ver la [guía del modo servidor](docs/guia-servidor.md) y, para dejarlo en una
Raspberry Pi, la [guía de instalación](docs/instalacion-raspberry.md).

Sin Flatpak (para desarrollar): con `include-system-site-packages = true` en
`.venv/pyvenv.cfg` y `python3-gobject`, `webkitgtk6.0` y `libadwaita` del
sistema, `.venv/bin/turnos-escritorio`. La interfaz nativa:
`.venv/bin/turnos-gnome` (en el Flatpak, «Turnos médicos (nativa)» en el menú).

## Desarrollo

```sh
.venv/bin/pytest                     # pruebas de Python (incluida la ventana GTK con Xvfb)
(cd interfaz && npm test)            # pruebas de la interfaz
scripts/e2e.sh                       # flujo completo con Playwright (Chromium del sistema)
(cd interfaz && npm run comprobar)   # comprobación de tipos
```

Interfaz con recarga en caliente: arranca `TURNOS_SIN_TOKEN=1 .venv/bin/turnos`
y, en paralelo, `cd interfaz && npm run dev` (Vite redirige `/api` al puerto 8000).

Si cambia la API, regenera los tipos de la interfaz:

```sh
.venv/bin/python -m turnos.api.openapi interfaz/openapi.json
(cd interfaz && npm run tipos)
```

Crear o actualizar solo la base de datos, o generar un mes de ejemplo con el
motor:

```sh
.venv/bin/python -m turnos.datos
.venv/bin/python -m turnos.motor.ejemplo 2026 11
```

Notas:

- Las dependencias de la interfaz están fijadas a versiones exactas con al
  menos dos semanas de antigüedad. `interfaz/.npmrc` activa
  `legacy-peer-deps` para evitar un fallo de npm con las dependencias
  opcionales de vite/vitest/jsdom; las necesarias están declaradas en
  `package.json`.
- Si VS Code se ejecuta como flatpak, su terminal no tiene Node y su Python no
  es el del sistema: el entorno `.venv` está creado con el Python del sistema,
  así que usa una terminal del sistema (o `flatpak-spawn --host …`).

## Licencia

Software libre bajo la [GNU General Public License v3.0](LICENSE) o posterior:
puedes usarlo, estudiarlo, modificarlo y compartirlo; si distribuyes una versión
modificada, debe ser también GPL-3.0 y con su código fuente.
