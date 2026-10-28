# turnosMedicos — Documentación técnica

Documento de referencia para quien instale, mantenga o amplíe la
aplicación. Complementa a:

- [especificaciones.md](especificaciones.md): qué debe hacer (requisitos y
  decisiones de producto, P1–P18).
- [diseno.md](diseno.md): cómo se diseñó (decisiones técnicas, D1–D5).
- [guia-de-uso.md](guia-de-uso.md): manual para el planificador.
- [arquitectura.md](arquitectura.md): visión de conjunto (capas, recorridos,
  modelo de datos, decisiones).
- [mantenimiento.md](mantenimiento.md): cada componente en detalle y recetas
  para modificarlo.
- [pruebas.md](pruebas.md): las pruebas automáticas, cómo ejecutarlas y cómo
  ampliarlas.

La [sección 14](#14-historia-de-la-construcción) cuenta, paso a paso, cómo se
construyó la aplicación y por qué se tomó cada decisión.

## Índice

1. [Resumen](#1-resumen)
2. [Instalación y arranque](#2-instalación-y-arranque)
3. [Arquitectura y tecnologías](#3-arquitectura-y-tecnologías)
4. [Estructura del repositorio](#4-estructura-del-repositorio)
5. [Dominio](#5-dominio)
6. [Motor de asignación](#6-motor-de-asignación)
7. [Datos y migraciones](#7-datos-y-migraciones)
8. [API](#8-api)
9. [Interfaz](#9-interfaz)
10. [Exportación](#10-exportación)
11. [Pruebas](#11-pruebas)
12. [Operación y mantenimiento](#12-operación-y-mantenimiento)
13. [Limitaciones conocidas y trabajo futuro](#13-limitaciones-conocidas-y-trabajo-futuro)
14. [Historia de la construcción](#14-historia-de-la-construcción)

---

## 1. Resumen

Aplicación **local** para asignar automáticamente turnos de mañana y tarde
(lunes a viernes, sin festivos) a un equipo de médicos. Se usa de dos formas
con el mismo núcleo y los mismos datos: como **aplicación de escritorio
GNOME** (Flatpak, `turnos-escritorio`) o como **web local** en el navegador
(`turnos`). Ver [diseno-escritorio.md](diseno-escritorio.md).

- Un solo proceso Python (FastAPI) sirve la API JSON y la interfaz React ya
  compilada, y guarda todo en un fichero SQLite.
- La asignación la calcula **OR-Tools CP-SAT** con varias pasadas
  lexicográficas: validez, equidad, preferencias y estabilidad.
- Un único usuario (el planificador) por cuenta del equipo, sin inicio de
  sesión; el servidor escucha solo en `127.0.0.1` y la API exige un token
  que se genera en cada arranque.
- Plataforma objetivo: **Linux (Fedora 43)**, Python ≥ 3.13 (3.14 en el
  sistema) y Node.js 22 (solo para compilar la interfaz).

Tamaño: unas 11.000 líneas entre Python, TypeScript y scripts, con 175
pruebas de Python (una de ellas abre la ventana GTK), 27 de la interfaz y 15
de flujo completo.

## 2. Instalación y arranque

Requisitos del sistema: `python3` (≥ 3.13), `nodejs` y `npm`, y, para las
pruebas de flujo completo, `chromium-browser`.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
(cd interfaz && npm ci && npm run build)
.venv/bin/turnos
```

Hay dos órdenes, que comparten `turnos.arranque.servidor.preparar`: crea o
actualiza la base de datos (con copia previa), reserva el puerto en
`127.0.0.1` y crea la aplicación con un token nuevo.

| Orden | Módulo | Qué hace |
|---|---|---|
| `turnos` | `turnos.arranque.web` (también `python -m turnos`) | Arranca en el puerto 8000 y abre el navegador con `?token=…` |
| `turnos-escritorio` | `turnos.arranque.escritorio` | Ventana GNOME con la interfaz en un WebView; puerto libre al azar |
| `turnos-gnome` | `turnos.arranque.gnome` | Interfaz nativa GTK/libadwaita completa, cliente de la misma API ([prototipo-gnome-nativo.md](prototipo-gnome-nativo.md)) |

| Variable de entorno | Por defecto | Uso |
|---|---|---|
| `TURNOS_DATOS` | `~/.local/share/turnosMedicos/turnos.sqlite` (respeta `XDG_DATA_HOME`; en Flatpak, siempre la carpeta personal) | Fichero de datos. |
| `TURNOS_PUERTO` | `8000` | Puerto del modo web (`0` = uno libre). |
| `TURNOS_SIN_NAVEGADOR` | — | Si tiene valor, no abre el navegador. |
| `TURNOS_SIN_TOKEN` | — | Desactiva el token (solo desarrollo y pruebas). |
| `TURNOS_INTERFAZ` | `interfaz/dist` | Carpeta de la interfaz compilada (el Flatpak la fija). |
| `TURNOS_DEPURAR` | — | Herramientas de desarrollo de WebKit en el modo escritorio. |

**Token de sesión.** La primera página se abre con `?token=…`; el servidor
lo guarda en la cookie `turnos_sesion_<puerto>` (HttpOnly, SameSite=Strict)
y redirige sin él. Las rutas `/api` responden 401 sin esa cookie o la
cabecera `X-Turnos-Token`. Así otra cuenta del mismo equipo no puede usar el
servidor aunque se conecte al puerto.

Desarrollo de la interfaz con recarga en caliente: arranca
`TURNOS_SIN_TOKEN=1 .venv/bin/turnos` y, en paralelo,
`cd interfaz && npm run dev`. Vite (puerto 5173) redirige `/api` al puerto
8000.

### Modo escritorio sin Flatpak

Necesita `python3-gobject`, `gtk4`, `libadwaita` y `webkitgtk6.0` del
sistema y que el `.venv` los vea: `include-system-site-packages = true` en
`.venv/pyvenv.cfg` (o crearlo con `--system-site-packages`). Después,
`.venv/bin/pip install -e .` y `.venv/bin/turnos-escritorio`.

### Paquete Flatpak

```sh
sudo dnf install flatpak-builder           # una vez
scripts/empaquetar-flatpak.sh              # → build/turnos-medicos-<versión>.flatpak
sudo flatpak install --system build/turnos-medicos-<versión>.flatpak
```

El guion compila la interfaz y la rueda de la aplicación en
`build/flatpak/fuentes`, ejecuta `flatpak-builder` con
`empaquetado/flatpak/io.oriol.TurnosMedicos.yml` (runtime GNOME 51) y crea el
paquete. La primera vez ofrece instalar el SDK de GNOME 51 para el usuario.
Con `--instalar` lo instala además solo para el usuario actual. Permisos del
paquete: `~/.local/share/turnosMedicos` y red (desde la v2.7, solo para buscar
los festivos oficiales).

## 3. Arquitectura y tecnologías

```
Navegador o ventana GNOME (WebView)
  └─ Interfaz (React) ──JSON──▶ FastAPI ── servicios/ ──▶ motor/ (OR-Tools)
                                   │                └─▶ exportar/ (XLSX)
                                   └── datos/ (SQLAlchemy) ──▶ turnos.sqlite
```

Las capas `dominio/` y `motor/` no dependen de la API ni de la base de datos
y se prueban de forma aislada. `servicios/` une la base de datos con el motor.

| Pieza | Tecnología y versión fijada |
|---|---|
| Motor | ortools 9.15 (CP-SAT) |
| Servidor | FastAPI 0.143, Uvicorn 0.54, Pydantic 2.14 |
| Datos | SQLAlchemy 2.1, Alembic 1.20, SQLite |
| Exportación | openpyxl 3.1.5 |
| Interfaz | React 19.3.0, React Router 7.18.4, TanStack Query 5.103.3, dnd-kit/core 6.3.1, IBM Plex (@fontsource 5.3.0) |
| Compilación | TypeScript 5.8.3, Vite 6.4.3; tipos de la API con openapi-typescript 7.13.0 |
| Pruebas | pytest 9, Vitest 4.1.11 + Testing Library + jsdom 29, Playwright 1.63.0 |

**Política de dependencias npm**: versiones **exactas** (sin `^`), con al
menos dos semanas desde su publicación y sin avisos en `npm audit`.
`interfaz/.npmrc` activa `legacy-peer-deps` para sortear un fallo de npm 10
con las dependencias opcionales de vite/vitest/jsdom (ver sección 14, fase
4); por eso las dependencias que normalmente se instalarían solas
(`@testing-library/dom`, `@types/node`) están declaradas explícitamente.

## 4. Estructura del repositorio

```
docs/                       especificaciones, diseño, esta documentación, guía, imágenes
                            y ejemplo/ (prototipo de interfaz usado como referencia)
src/turnos/
  __main__.py               `python -m turnos` (modo web)
  config.py                 ruta del fichero de datos
  arranque/                 servidor (compartido), web (`turnos`) y escritorio/
                            (`turnos-escritorio`: aplicación, ventana, descargas,
                            errores, estado de la ventana) y gnome/ (interfaz nativa)
  dominio/                  tipos y reglas puras: modelos, calendario, carga
  motor/                    entrada/preprocesado, diagnóstico, modelo CP-SAT,
                            validación, resultado y avisos, ejemplo ejecutable
  datos/                    tablas SQLAlchemy, bd (crear/migrar/datos iniciales),
                            migraciones Alembic, `python -m turnos.datos`
  servicios/                reglas (versionadas) y periodos (calendario del mes)
  api/                      app, esquemas Pydantic, rutas, exportación del OpenAPI
  exportar/                 xlsx
  recursos/festivos/        calendarios de festivos precargados (JSON)
tests/                      dominio, motor, datos, recursos, api, arranque, escritorio (pytest)
interfaz/
  src/api/                  cliente fetch, consultas TanStack Query, tipos generados
  src/calendario/           lógica pura del calendario e historial deshacer/rehacer
  src/componentes/          cabecera, panel lateral, cuadrícula de elegibilidad, campo de turnos, mensajes…
  src/medicos/              tarjeta de médico, panel «Más reglas», conversión del formulario
  src/paginas/              una página por pestaña + vista imprimible
  e2e/                      pruebas Playwright
  openapi.json              esquema de la API (generado, versionado)
empaquetado/flatpak/        manifiesto, .desktop, AppStream, iconos y dependencias (generadas)
scripts/e2e.sh              ejecuta las pruebas de flujo completo
scripts/empaquetar-flatpak.sh            crea el paquete Flatpak
scripts/generar-dependencias-flatpak.py  regenera python3-dependencias.json
```

## 5. Dominio

- **Medios turnos**: todas las cargas se guardan y calculan en enteros de
  medio turno (18,5 turnos = 37). Así no hay decimales en el motor ni en la
  base de datos; la interfaz convierte al mostrar y al leer.
- **Mitades**: cada turno tiene dos mitades (`M1`, `M2`, `T1`, `T2`). Una
  asignación es un médico en **una mitad**; un turno completo son dos filas.
  La cobertura se comprueba por mitad. Las jornadas de turno y medio usan la
  mitad contigua: mañana + `T1`, o `M2` + tarde.
- **Días de la semana**: 0 = lunes … 4 = viernes (`date.weekday()`).
- **Ajuste de carga por ausencias** (`dominio/carga.py`):
  `rango × (medios días disponibles / medios días laborables del mes)`. Una
  ausencia de un solo turno cuenta medio día; se redondea al medio turno más
  cercano (empates hacia arriba). Se calcula con `Fraction` para que sea
  exacto.
- **Reglas versionadas** (`servicios/reglas.py`): cada guardado escribe una
  «foto» completa de elegibilidad, jornadas especiales y carga con su
  `vigente_desde`. Para una fecha vale la última foto anterior o igual.
  Las preferencias no se versionan.

## 6. Motor de asignación

**Turnos rotativos** (`entrada.Rotacion`, `Problema.rotaciones`): en el
preprocesado, para cada turno de la rotación y cada día, el titular de esa
semana (`Rotacion.titular`: índice de semana desde el lunes de `desde`, módulo
el número de médicos) queda fijado como `FIJO` (salvo bloqueo del día,
ausencia o veto), y los demás del grupo se excluyen de ese turno: se quitan de
los candidatos y se anula su «Fijo» de tarjeta para él. Si el titular no
puede, no se excluye a nadie. La validación avisa si dos miembros coinciden y
no marca como «no disponible» al titular.

**Todos trabajan cada día** (`Problema.todos_trabajan`, ajuste general
`todos_trabajan`, activado por defecto): para cada médico y cada día en que ya
tiene algo fijado o tiene algún turno posible (`dias_obligatorios`),
`Σ x[m, d, ·] + falta_dia ≥ 1`. La pasada «todos trabajan cada día» va tras
la cobertura mínima y antes de la máxima y de la carga. El diagnóstico avisa
si, con todos trabajando, un día supera la cobertura máxima o un médico su
carga máxima; la validación avisa de médicos sin turno un día en que podían.

**Urgencias y domicilios** (`Rol`): en cada tarde con cobertura mínima ≥ 2
(`Problema.dias_con_roles`), variables `r[médico, día, rol]` solo para quien
hace la tarde completa (fijada o `x[m, d, TARDE]`). Cada médico tiene como
mucho un papel. Cada papel, exactamente uno por tarde, con holgura `falta_rol`.
Los papeles fijados a mano (`roles_fijados`) se imponen. El reparto se mide
por la salida de cada médico de la banda [⌊parte⌋, ⌈parte⌉], donde parte =
tardes con papel × tardes disponibles del médico / total
(`tardes_disponibles`). Pasadas: «urgencias y domicilios» (tras la cobertura),
«reparto… (mayor desviación)» y «reparto… (suma)» (tras la carga, antes de la
equidad de carga). La estabilidad incluye los cambios de papel.

Valores de la cuadrícula (`Elegibilidad`): `FIJO` (fijado de antemano todas
las semanas), `HABITUAL` (asignable y con preferencia +2 en la pasada de
preferencias: «si trabaja ese día, mejor este turno»), `DISPONIBLE`
(asignable) y `NO_DISPONIBLE`. La columna es texto sin restricción, así que
`HABITUAL` no necesitó migración.


Código en `src/turnos/motor/`. Punto de entrada:
`generar(problema, parametros) -> Resultado`.

1. **Preprocesado** (`entrada.preparar`): separa lo **fijado** (huecos
   *Fijo*, jornadas especiales de las reglas y asignaciones bloqueadas, salvo
   ausencias o vetos) de los **candidatos**: los turnos completos que el
   motor puede decidir, solo en días en que el médico no tiene nada fijado.
   El motor nunca crea jornadas de más de un turno (P16).
2. **Diagnóstico previo** (`diagnostico.py`): condiciones necesarias que, si
   fallan, impiden un calendario válido. Se explican como avisos `CAUSA`.
3. **Modelo** (`modelo_cpsat.py`): variables booleanas `x[médico, día,
   turno]`; como mucho un turno al día; cobertura por mitad y carga (total y
   por turno) con **holguras** (`falta`, `sobra`, `defecto`, `exceso`), de
   modo que siempre hay solución y las holguras dicen qué se incumple.
4. **Pasadas lexicográficas**: en cada una se minimiza un objetivo y su valor
   queda como restricción para las siguientes:
   1. huecos sin cubrir (`Σ falta`);
   2. exceso de personal (`Σ sobra`), de modo que es mejor un médico de más
      que un hueco;
   3. carga fuera de rango;
   4. equidad: mayor desviación respecto al objetivo de cada médico;
   5. equidad: suma de desviaciones;
   6. preferencias;
   7. estabilidad: cambios respecto al calendario anterior (solo al
      regenerar).
   
   El **objetivo** de cada médico reparte la demanda del mes en proporción al
   punto medio de su rango, menos su saldo de meses publicados (máximo ±1
   turno por mes), recortado al rango.
5. **Alternativa**: tras las pasadas de validez se exige cambiar al menos
   *k* turnos (`max(2, generados/20)`); si no es posible, `SinAlternativa`.
6. **Determinismo**: un solo hilo, semilla fija y límite de tiempo
   *determinista* (`max_deterministic_time`, 5 por pasada).
7. **Validación** (`validacion.py`): recalcula los incumplimientos de
   cualquier calendario (por ejemplo, tras cambios manuales) con los mismos
   textos que el motor, y añade avisos de asignaciones en huecos no
   disponibles, ausencias o días no laborables.

Rendimiento medido: 30 médicos × 25 días con 8–12 médicos por turno, en
menos de 1 s; el ejemplo de 12 médicos, en 0,2 s.
`python -m turnos.motor.ejemplo 2026 11` genera un mes de ejemplo en la
terminal.

## 7. Datos y migraciones

Tablas (`datos/tablas.py`):

| Grupo | Tablas |
|---|---|
| Configuración | `ajuste` (clave → valor JSON; migración 0004; `servicios/ajustes.py`), `horario_turno`, `festivo`, `carga_festivos`, `cobertura_semanal`, `cobertura_fecha` |
| Turnos rotativos | `rotacion`, `rotacion_medico` (con `orden`), `rotacion_hueco` (migración 0005; `servicios/rotaciones.py`) |
| Médicos | `medico` (con `color` `#rrggbb` opcional, migración 0002), `elegibilidad`, `jornada_semanal`, `carga`, `preferencia`, `ausencia` |
| Mes | `rol_tarde` (urgencias/domicilios por fecha, `manual`; migración 0003), `periodo` (`publicado_en` NULL = borrador), `carga_ajustada` (rango calculado, sobrescritura manual y objetivo), `asignacion`, `veto`, `aviso` (solo causas) |

- Los enumerados se guardan como texto; las claves ajenas se activan con
  `PRAGMA foreign_keys = ON` en cada conexión.
- Al arrancar (`datos/bd.inicializar`): se aplican las migraciones
  pendientes (antes se hace una **copia de seguridad** si el fichero tiene
  datos), se cargan los horarios por defecto si no hay y se vuelcan los
  festivos precargados de los años aún no cargados (`carga_festivos` evita
  deshacer cambios del planificador). Un año marcado incompleto que llega
  completo en una versión nueva solo añade sus festivos **locales**.

**Crear una migración** tras cambiar `tablas.py`:

```sh
.venv/bin/python - <<'EOF'
from pathlib import Path
from alembic import command
from turnos.datos.bd import _config_alembic, crear_motor
motor = crear_motor(Path("/tmp/esquema-actual.sqlite"))   # base al día (vacía o copia)
cfg = _config_alembic()
with motor.begin() as conexion:
    cfg.attributes["conexion"] = conexion
    command.upgrade(cfg, "head")
    command.revision(cfg, message="describe el cambio", autogenerate=True, rev_id="0002")
EOF
```

Revisa el fichero generado en `datos/migraciones/versions/`. Las migraciones
usan `render_as_batch` porque SQLite no admite `ALTER TABLE` completo.

## 8. API

Todas las rutas cuelgan de `/api` y usan JSON (cargas en medios turnos).
Documentación interactiva en `http://127.0.0.1:8000/docs`.

| Método | Ruta | Uso |
|---|---|---|
| GET/POST | `/medicos` | Listar / crear |
| GET/PUT/DELETE | `/medicos/{id}` | Ficha (DELETE da 409 si tiene turnos) |
| GET/PUT | `/medicos/{id}/reglas?fecha=` | Reglas vigentes / guardar versión `vigente_desde` |
| GET/POST, PUT/DELETE | `/ausencias`, `/ausencias/{id}` | Ausencias (filtros `medico_id`, `desde`, `hasta`) |
| GET/POST, DELETE | `/festivos?anio=`, `/festivos/{id}` | Festivos |
| GET | `/festivos/anios` | Años precargados y si están completos |
| POST | `/festivos/restaurar/{anio}` | Vuelve a añadir los precargados que falten |
| GET/PUT | `/cobertura/semanal` | 20 filas día × mitad |
| GET, PUT/DELETE | `/cobertura/fechas`, `/cobertura/fechas/{fecha}` | Excepciones por fecha (4 mitades) |
| GET/PUT | `/horarios` | Horario y corte de cada turno |
| GET/PUT | `/ajustes` | Ajustes generales (`todos_trabajan`) |
| GET/POST, PUT/DELETE | `/rotaciones`, `/rotaciones/{id}` | Turnos rotativos (`nombre`, `desde`, `activa`, `medicos` en orden, `huecos`) |
| GET | `/estado` | Avisos de configuración (para el mes siguiente) |
| GET | `/copia-de-seguridad` | Copia del fichero SQLite |
| GET | `/periodos/{a}/{m}` | Calendario del mes, con validación al vuelo |
| POST | `/periodos/{a}/{m}/generar` | `{"alternativa": bool}` (409 si publicado) |
| POST | `/periodos/{a}/{m}/cambios` | Lista de `{medico_id, fecha, mitades}`, `{…, bloqueada}` o `{…, rol}` (urgencias/domicilios; intercambia si hace falta) |
| POST | `/periodos/{a}/{m}/liberar` | «Volver a automático»: `{fecha?, turno?}` (sin fecha, todo el mes) |
| PUT | `/periodos/{a}/{m}/manual` | Restaura una foto de asignaciones y vetos (deshacer) |
| PUT | `/periodos/{a}/{m}/carga/{id}` | Rango manual del mes (`null` = calculado) |
| POST | `/periodos/{a}/{m}/publicar` · `/reabrir` | Estado del mes |
| GET | `/periodos/{a}/{m}/exportar.xlsx` | Hoja de cálculo |

Todas las modificaciones del calendario devuelven el **calendario completo**
ya validado.

**Tipos de la interfaz**: si cambia la API, regenera el esquema y los tipos:

```sh
.venv/bin/python -m turnos.api.openapi interfaz/openapi.json
(cd interfaz && npm run tipos)
```

## 9. Interfaz

El aspecto y el planteamiento de pantallas siguen el prototipo
[`docs/ejemplo/ejemplo.html`](ejemplo/ejemplo.html) (ver la fase 8 de la
historia):

- **Cabecera fija** (`componentes/Disposicion.tsx`) con el título, el **mes de
  trabajo** (‹ ›) y las pestañas *Calendario* (con el número de reglas
  incumplidas), *Médicos y reglas*, *Cobertura*, *Festivos* y
  *Configuración*. El mes vive en la URL (`?mes=AAAA-MM`, por defecto el
  siguiente; `util/mes.ts`) y lo comparten todas las pestañas.
- Rutas: `/` (calendario), `/medicos`, `/cobertura`, `/festivos`,
  `/configuracion` e `/imprimir?mes=…&auto=1` (sin cabecera). `/calendario` y
  `/ausencias`, de la versión anterior, redirigen. FastAPI devuelve
  `index.html` para cualquier ruta que no sea de `/api` ni un fichero.
- **Calendario** (`paginas/Calendario.tsx`):
  - Panel de resumen con cifras, acciones y leyenda.
  - Cuadrícula mensual de lunes a viernes; cada día es una tarjeta con las
    franjas MAÑANA y TARDE, la cifra «asignados / mínimo–máximo», `BLOQ.` y
    fichas (fijo, ½, doble).
  - Paneles *Problemas a resolver* (avisos de configuración del endpoint
    `/estado`, incumplimientos con su causa y causas sueltas) y *Carga por
    médico* (con ajuste del rango del mes), y panel *Exportar*.
  - Dos vistas, con un selector **Cuadrícula / Lista** (`calendario/useVista.ts`):
    la cuadrícula mensual y una lista con un día por fila (mañana y tarde lado
    a lado, apiladas en pantallas estrechas). Ambas usan el mismo componente
    `Franja`, así que comparten edición, arrastre y colores. La elección se
    guarda en `localStorage` del navegador (con *fallback* a la cuadrícula si
    no está disponible).
  - Al pulsar una franja se abre un **panel lateral** (`componentes/Cajon.tsx`)
    con todos los médicos y un selector **No / ½ / 1**. El ½ solo se permite
    junto a un turno completo el mismo día (`admiteMedio`) y es siempre la
    mitad contigua (`MITAD_CONTIGUA`).
- **Turnos rotativos** (`/medicos/rotaciones`, subpestaña de «Médicos y
  reglas»; `rotaciones/`): una tarjeta por grupo, con autoguardado, médicos
  ordenables, cuadrícula de turnos, semana de inicio y vista previa de a quién
  le toca cada semana del mes (`rotaciones/semanas.ts`, mismo cálculo que el
  motor).
- **Generar y leer el calendario esperan a los guardados pendientes** de
  cualquier pestaña (`esperarTodosLosGuardados`), para no generar con
  cambios a medio guardar.
- **Color de cada médico** (`util/colores.ts`, `medicos/SelectorColor.tsx`):
  paleta de 16 colores, o uno libre, elegido junto al nombre. Las fichas del
  calendario, de la tabla de carga y del arrastre usan ese fondo con texto
  oscuro o blanco según la luminancia (`textoSobre`). Los médicos nuevos
  reciben el primer color libre de la paleta.
- **Médicos y reglas** (`medicos/`): una tarjeta por médico con color, nombre, código,
  activo, cuadrícula, carga y ausencias; el resto de reglas, en el panel
  *Más reglas…*. Las reglas se guardan solas 450 ms después del último
  cambio, como versión `vigente_desde` = primer día del mes de trabajo; sin
  carga válida se guarda todo lo demás (`carga` es opcional en
  `PUT /reglas`). El formulario solo se carga del servidor al abrir la
  tarjeta o cambiar de mes, y siempre con una lectura fresca, no la copia en
  caché, para no pisar lo que se está escribiendo.
- **Autoguardado sin pérdidas** (`util/useAutoguardado.ts` y
  `useGuardadoSeguro` en `api/consultas.ts`; lo usan las tarjetas y la
  cobertura semanal):
  - Si el componente se cierra con un cambio pendiente (cambio de pestaña o
    de mes), se envía en ese momento; al cerrar la página, con
    `fetch(..., {keepalive})`.
  - Los guardados de una misma clave van en orden, y las lecturas esperan a
    los que estén en curso.
- **Urgencias y domicilios**: insignias con iconos SVG propios
  (`componentes/Iconos.tsx`: luz de emergencia roja y casa azul, con nombre
  accesible) en las fichas de la tarde y en la leyenda; selector Urg./Dom.
  con los mismos iconos en el panel de la tarde para quien la hace completa,
  columnas *Urg.* y *Dom.* en la tabla de carga; las fotos de deshacer
  incluyen los papeles.
- **Cambios manuales** (`calendario/logica.ts`): cada gesto se traduce en
  operaciones «dejar a este médico, este día, en exactamente estas mitades»
  (`FijarDia` en el servidor). Lo que queda se **bloquea**; los turnos que
  pierde se **vetan**. Las otras operaciones son bloquear o desbloquear y
  **volver a automático** (`POST /liberar`), que desbloquea y retira vetos de
  un turno, de un día o del mes.
- **Arrastrar y soltar** con dnd-kit: el contexto (`ZonaArrastre`) abarca la
  cuadrícula y la tabla de carga, de modo que se arrastra entre franjas y
  desde la tabla. Soltar fuera de una franja quita; Ctrl al soltar copia.
- **Deshacer / rehacer** (`calendario/useHistorial.ts`): antes de cada cambio,
  regeneración o «volver a automático» se guarda una foto (asignaciones y
  vetos); deshacer la restaura con `PUT /manual`. Atajos Ctrl+Z / Ctrl+Y /
  Ctrl+Mayús+Z, con un máximo de 50 pasos y reinicio al cambiar de mes.
- Cualquier cambio de configuración invalida las consultas del calendario y
  del estado. Sin actualizaciones optimistas: el servidor es local y responde
  al instante con el calendario validado. Los avisos breves («Guardado»…) se
  muestran con `ProveedorTostadas`.
- **Estilo** (`estilos/global.css`): variables CSS con la paleta del
  prototipo (acento verde azulado, color propio para mañana y tarde, rojo,
  ámbar y verde para el estado), tema claro y oscuro (también forzable con
  `data-theme`) y tipografía **IBM Plex Sans/Mono** incluida con
  `@fontsource` (solo el subconjunto latino), sin depender de internet.
  CSS Modules por componente y estilos de impresión en A4 horizontal.

## 10. Exportación

- `exportar/xlsx.py`: hojas *Calendario* (nombres, horario, festivos,
  incumplimientos), *Por médico* (matriz M/T/M+½T…) y *Resumen* (números).
  Configuradas para imprimir en A4 horizontal ajustado al ancho.
- Página `/imprimir`: dos páginas A4 horizontal (calendario y tabla por
  médico); el PDF se obtiene con «Guardar como PDF» del navegador.
- Urgencias y domicilios (v2.9): `exportar_roles_xlsx` en `exportar/xlsx.py`
  (`GET /api/periodos/{año}/{mes}/urgencias-domicilios.xlsx`, hojas
  *Urgencias y domicilios* y *Por médico*, A4 vertical) y la página
  `/imprimir/urgencias-domicilios`, que mientras está abierta añade una regla
  `@page { size: A4 portrait }` (el resto de vistas imprimen en horizontal).

## 11. Pruebas

| Conjunto | Comando | Contenido |
|---|---|---|
| Python (175) | `.venv/bin/pytest` | Dominio, festivos, base de datos y migraciones (también datos de una versión más nueva), motor (restricciones, inviabilidad, equidad, determinismo, alternativa, rendimiento), validación, API completa y exportación; arranque (puerto libre, token y cookie, parada) |
| Interfaz nativa (3, incluidas arriba) | `.venv/bin/pytest -m escritorio` | `tests/escritorio/test_gnome.py`: con Xvfb y desde los widgets, todas las funciones (generar, alternativa, deshacer, arrastrar, rango, imprimir a PDF, diálogo del turno, reglas, ausencias, más reglas, turnos rotativos, cobertura, horarios, festivos), comprobadas después en la API; y la lógica de soltar con los casos de la web |
| Ventana GTK (1, incluida arriba) | `.venv/bin/pytest -m escritorio` | Abre `turnos-escritorio` con Xvfb, espera a la interfaz, cierra y comprueba que el guardado de `pagehide` llega y que el servidor se detiene. Se salta si faltan GTK/WebKitGTK, `xvfb-run` o la interfaz compilada |
| Interfaz (27) | `cd interfaz && npm test` | Cuadrícula de elegibilidad (clic, arrastre, teclado), campo de turnos, lógica del calendario (arrastres, selector No/½/1), utilidades |
| Tipos | `cd interfaz && npm run comprobar` | TypeScript estricto |
| Flujo completo (19) | `scripts/e2e.sh` | Generar, arrastrar (quitar y añadir desde la tabla), deshacer/rehacer, regenerar con bloqueos, publicar; panel de un turno (½ y volver a automático); vista en lista; persistencia al cambiar de pestaña enseguida (reglas, nombre, médico nuevo sin carga, cobertura); aviso de médicos sin carga junto a «Generar»; turno habitual en el panel; color de cada médico de la tarjeta al calendario; urgencias y domicilios (intercambio y recuento); opción «todos trabajan cada día»; turnos rotativos (subpestaña, vista previa y alternancia en el calendario); tarjetas de médicos (autoguardado, ausencias, más reglas); exportar, imprimir y copia; mes compartido entre pestañas y redirecciones |

`scripts/e2e.sh` compila la interfaz, arranca la aplicación (sin token) con
una base de datos temporal vacía y ejecuta Playwright con el Chromium del sistema
(`CHROMIUM` para otra ruta). Comprobación estática de Python:
`.venv/bin/python -m pyflakes src tests`.

## 12. Operación y mantenimiento

### Festivos de un año nuevo

Cada año la Comunidad de Madrid publica sus fiestas en otoño (decreto en el
BOCM) y los ayuntamientos sus dos fiestas locales, normalmente en diciembre
(resolución en el BOCM).

- **Desde la aplicación** (lo habitual): *Configuración → Festivos
  oficiales* busca los del municipio del centro en línea; o se añaden a mano
  en *Festivos*.
- **Para precargarlos en una versión nueva**: crea
  `src/turnos/recursos/festivos/madrid-AAAA.json` con el formato de los
  existentes (`completo: false` y un texto en `pendiente` si faltan los
  locales) y comprueba las fechas en el BOCM. `tests/recursos` valida su
  coherencia.

Fuentes usadas para 2026–2027: Decreto 75/2025 (BOCM 25/09/2025),
Resolución de fiestas locales de 2026 (BOCM-20251212-34) y Decreto 82/2026
(BOCM 01/10/2026). Los locales de Madrid de 2027 estaban pendientes de
publicar al crear la aplicación.

### Festivos oficiales en línea

`servicios/festivos_oficiales.py`, desde *Configuración → Festivos oficiales*
(`GET /api/festivos/oficiales/{año}` compara; `POST` añade los que faltan y
marca el año en `carga_festivos` como `oficial:<INE>`, completo si hay dos
locales). El municipio es el ajuste `municipio` (código INE); la relación de
municipios va en `recursos/municipios.json` (INE, `diccionario26.xlsx`,
generada a partir de la de festivos.io).

| Fuente | Qué da | Uso |
|---|---|---|
| [festivos.io](https://festivos.io) (`/v1/{año}/municipio/{INE}.json`, CC BY 4.0) | Nacionales, autonómicos y locales de cualquier municipio, con la referencia oficial (BOE, boletín autonómico, datos abiertos) y su enlace | Principal |
| [Comunidad de Madrid, datos abiertos](https://datos.comunidad.madrid/dataset/f160eb6c-6715-471e-9bc0-38497aae950f) («Festivos regionales y locales año en curso») | Locales de cada municipio madrileño, solo del año en curso | Locales que falten en municipios de Madrid |

Las direcciones se cambian con `TURNOS_FUENTE_FESTIVOS_IO` (plantilla con
`{anio}` e `{ine}`) y `TURNOS_FUENTE_MADRID`; `scripts/e2e.sh` las apunta a
ficheros de `interfaz/e2e/datos`. Si una fuente no responde, se avisa y se usa
la otra; si no responde ninguna, la API devuelve 502. Los precargados (de
Madrid, el municipio por defecto) solo se vuelcan al arrancar si el municipio es Madrid.

### Copias de seguridad y restauración

- Copia manual: *Configuración → Exportar copia de los datos*, o copiar el
  fichero de datos con la aplicación cerrada.
- **Importar** (*Configuración → Importar una copia…*, `POST /api/importar`
  con el fichero como cuerpo): `servicios/importar.py` comprueba la copia
  (SQLite, `integrity_check`, tablas de turnosMedicos, versión no más nueva),
  la migra en una carpeta temporal, guarda los datos actuales en
  `turnos-antes-de-importar-AAAAMMDD-HHMMSS.sqlite.bak` y copia su contenido
  sobre el fichero de datos con la API de copia de SQLite.
- Copias automáticas: antes de cada migración, junto al fichero de datos
  (`turnos-AAAAMMDD-HHMMSS.sqlite.bak`).
- **Restaurar**: cierra la aplicación y sustituye el fichero de
  `TURNOS_DATOS` por la copia (renombrándola a `turnos.sqlite`). Al arrancar
  se aplicarán las migraciones que le falten.

### Actualizar dependencias

- Python: actualiza `pyproject.toml` si hace falta subir el mínimo y ejecuta
  las pruebas.
- npm: elige versiones con al menos dos semanas de antigüedad
  (`npm view <paquete> time`), instálalas con `--save-exact`, ejecuta
  `npm audit`, las pruebas, `npm run comprobar` y `scripts/e2e.sh`.

### Nueva versión del paquete Flatpak

1. Sube `version` en `pyproject.toml` y añade un `<release>` en
   `empaquetado/flatpak/io.oriol.TurnosMedicos.metainfo.xml`.
2. Si han cambiado las dependencias de Python:
   `.venv/bin/python scripts/generar-dependencias-flatpak.py` (necesita red).
3. `scripts/empaquetar-flatpak.sh` y, en cada equipo,
   `sudo flatpak install --system build/turnos-medicos-<versión>.flatpak`.
   Al abrirla, las migraciones actualizan los datos de cada usuario con copia
   previa. Si alguien abre datos con una versión **más antigua**, la
   aplicación lo avisa y no los toca.

Para validar los metadatos: `desktop-file-validate` y
`appstreamcli validate --no-net` sobre los ficheros de `empaquetado/flatpak`.

### Entorno de desarrollo con VS Code en flatpak

Si VS Code está instalado como flatpak, su terminal es un entorno aislado:
no tiene Node, su Python no es el del sistema y su `/tmp` es distinto. El
`.venv` del proyecto está creado con el **Python del sistema**, así que hay
que trabajar desde una terminal del sistema o anteponer
`flatpak-spawn --host` a los comandos (`python`, `npm`, `scripts/e2e.sh`,
`chromium-browser`).

## 13. Limitaciones conocidas y trabajo futuro

- Un único usuario por cuenta y sin autenticación (solo `127.0.0.1`, con
  token por arranque). Compartir con los médicos se hace mediante la
  exportación.
- El paquete Flatpak se distribuye como fichero: las actualizaciones no
  aparecen en GNOME Software (haría falta un repositorio propio).
- AppStream sin capturas ni página web (el proyecto no está publicado).
- Fuera de alcance (especificaciones, 2): fines de semana y guardias,
  solicitudes de cambio de los médicos, varios servicios, rotaciones
  alternas, notificaciones, iCal.
- La «alternativa» busca el calendario válido más parecido con al menos *k*
  cambios; no explora repartos radicalmente distintos.
- Un médico inactivo con turnos bloqueados en un mes sigue apareciendo en
  ese mes, pero el motor no lo tiene en cuenta para la carga.
- Aviso de deprecación de Starlette en las pruebas (`httpx` → `httpx2`): no
  afecta al funcionamiento.
- Festivos locales de Madrid de 2027 pendientes de publicación.

## 14. Historia de la construcción

La aplicación se construyó el 14/10/2026 en sesiones de trabajo con Claude
(Claude Code), en fases que se validaban con el usuario antes de continuar.
Cada fase está en su propia rama y commit, encadenadas a partir de `main`:

```
main
└─ docs/especificaciones   ff9ecc7 especificaciones v1.0 · c3f74e3 diseño v1.0
   └─ fase-1-dominio       1d80201 fase 1 · dcd6f28 diseño v1.1 (React)
      └─ fase-2-motor      af20fdc
         └─ fase-3-datos   82097d8
            └─ fase-4-configuracion   286683a
               └─ fase-5-calendario   ffc9b45
                  └─ fase-6-exportacion   cae4e5a
                     └─ fase-7-documentacion   573dbf5  (fusionadas en main)
                        └─ interfaz-nuevo-estilo
```

### Fase 0 — Especificaciones

1. Petición inicial: una herramienta que asigne turnos de mañana y tarde en
   días laborables a un equipo de médicos, con un subconjunto configurable de
   turnos por médico. Se pidió primero un borrador de especificaciones en
   `docs/`.
2. Borrador v0.1 en inglés, con 14 preguntas abiertas y una propuesta para
   cada una. El usuario pidió **todo en castellano**: se tradujo a
   `docs/especificaciones.md`.
3. Decisiones del usuario (v0.2):
   - carga **mensual**;
   - un médico puede hacer **1, 1,5 o 2 turnos** al día;
   - festivos configurables, empezando por los de un municipio de la
     **Comunidad de Madrid** (en la versión publicada, Madrid capital);
   - **web local**.
   
   Surgieron preguntas nuevas sobre el medio turno.
4. v0.3:
   - el medio turno es la **mitad contigua** (mañana + primeras horas de la
     tarde, o últimas de la mañana + tarde);
   - las jornadas de 1,5 y 2 turnos **solo las pone el planificador**;
   - las ausencias **reducen la carga proporcionalmente**.
5. v1.0: cuadrícula de turnos, cobertura y horarios **configurables**; el
   resto de propuestas aceptadas. Se añadieron la tabla de parámetros
   configurables y el registro de decisiones.

### Diseño

6. `docs/diseno.md` v1.0: Python + FastAPI + htmx + SQLite + OR-Tools, con el
   modelo CP-SAT, el modelo de datos y un plan en 7 fases. El usuario
   confirmó **Fedora**, el límite de compensación entre meses (±1 turno) y
   dejó a elección el idioma del código (castellano, sin tildes ni ñ en los
   identificadores).
7. v1.1: el usuario pidió usar Node para tener una interfaz más rica
   (**arrastrar y soltar**). Se cambió htmx por React + TypeScript + Vite con
   dnd-kit; FastAPI pasó a ser solo API más los ficheros estáticos.

### Fase 1 — Dominio

8. `pyproject.toml`, entorno virtual y paquete `turnos.dominio`: turnos y
   mitades, jornadas especiales, rangos en medios turnos, ausencias, días
   laborables y ajuste de carga con fracciones exactas. 21 pruebas; una
   falló por comparar una `Fraction` con un `float` y se corrigió la prueba.

### Fase 2 — Motor

9. Preprocesado, diagnóstico, modelo CP-SAT, resultado con avisos legibles
   y un ejemplo ejecutable. Problemas encontrados y resueltos:
   - El modo paralelo determinista (`interleave_search`) era ~30 veces más
     lento: se pasó a **un solo hilo** (0,15 s frente a 4,6 s).
   - La equidad con **desviación al cuadrado** no demostraba el óptimo en
     10 s con 30 médicos: se sustituyó por dos pasadas lineales (mayor
     desviación y suma), con lo que pasó a menos de 1 s.
   - La «alternativa» encontraba calendarios **peores** (dejando huecos): la
     restricción de cambios se añade ahora después de las pasadas de validez.
   - Un empate entre «falta» y «sobra» se resolvía al azar: se separó en dos
     pasadas, de modo que es mejor un médico de más que un hueco.
   - Una prueba de compensación entre meses tenía dos soluciones igual de
     justas: se reescribió sobre un caso inequívoco.

### Fase 3 — Datos

10. Tablas SQLAlchemy, migración inicial de Alembic, copia de seguridad antes
    de migrar y datos iniciales.
11. Festivos verificados en fuentes oficiales: los locales de 2026 se
    comprobaron leyendo el PDF del BOCM-20251212-34 (en la versión publicada,
    los de Madrid: 15 de mayo y 9 de noviembre); 2027 se cargó con el Decreto 82/2026 y marcado
    **incompleto** (faltan los locales).
12. Se retiró un `alembic.ini` sobrante que había generado `alembic init`.

### Fase 4 — API e interfaz de configuración

13. VS Code se ejecutaba como **flatpak**: Node solo estaba en el sistema, así
    que se usó a través de `flatpak-spawn --host`.
14. Dependencias npm:
    - La versión de Vitest que se instalaba tenía vulnerabilidades críticas
      (tinypool): se fijó la 4.1.11.
    - npm 10 fallaba («Cannot read properties of null (reading
      'edgesOut')») con las dependencias opcionales: se resolvió con
      `legacy-peer-deps` en `.npmrc`.
    - React 19.3.1 se había publicado el mismo día: se fijó la 19.3.0, y lo
      mismo con otros paquetes demasiado recientes.
    - Todas las versiones quedaron **exactas**.
15. Reglas **versionadas** por fecha. El máximo de carga por tipo de turno
    pasó a admitir «sin límite»: como aún no había datos reales, se regeneró
    la migración inicial en lugar de añadir otra.
16. La aplicación se arrancó con datos de ejemplo y se revisó con capturas
    del Chromium del sistema. Así se corrigieron dos problemas:
    - El aviso de «médico sin carga» y la ficha del médico miraban el mes
      actual en lugar del siguiente (el que se planifica).
    - Una celda de la cuadrícula partía el texto en dos líneas.

### Fase 5 — Calendario del mes

17. Validación al vuelo (`motor/validacion.py`) con los mismos textos que el
    motor, para lo cual se extrajeron funciones de avisos compartidas.
18. Servicio de periodos:
    - construye el problema desde la base de datos (reglas vigentes,
      ausencias, rangos ajustados y manuales, saldo de meses publicados);
    - genera, aplica cambios (una única operación, `FijarDia`, más
      bloquear), restaura fotos y publica.
19. Interfaz del calendario con dnd-kit, panel de detalle, panel de médicos
    con ajuste de rango, deshacer y rehacer. Pruebas Playwright con el
    **Chromium del sistema**, sin descargar navegadores.
20. Se descubrió que el `.venv` creado dentro del flatpak (Python 3.13) **no
    funcionaba fuera**: el sistema tiene Python 3.14. Se recreó con el Python
    del sistema; las 95 pruebas y el flujo completo pasaron ahí. Se añadió
    `scripts/e2e.sh`.

### Fase 6 — Exportación

21. XLSX con tres hojas, página `/imprimir` y descarga de la copia de
    seguridad. El XLSX se revisó convirtiéndolo a PDF con el LibreOffice del
    sistema, y la página de impresión, imprimiéndola a PDF con Chromium; se
    corrigieron los anchos de la tabla por médico.

### Fase 7 — Documentación

22. A petición del usuario se **omitió el acceso directo** del escritorio. Se
    escribieron esta documentación técnica y la guía de uso, con capturas
    reales generadas con Playwright sobre el equipo de ejemplo.
23. Esas capturas revelaron que el **panel de detalle no mostraba los nombres
    de los médicos** (la columna del nombre se quedaba sin ancho): se
    rediseñó la fila con el nombre en su propia línea.

### Fase 8 — Nueva interfaz a partir de un prototipo

24. El usuario aportó `docs/ejemplo/ejemplo.html`, un prototipo autónomo, y
    pidió recrear las pantallas principales con su estilo y su planteamiento.
    El primer intento de leerlo encontró el fichero vacío (sin guardar); se
    pidió y, ya con contenido, se renderizó con Playwright para estudiarlo.
25. Del prototipo se tomaron:
    - la cabecera fija con el mes y las pestañas;
    - el calendario en cuadrícula de lunes a viernes, con franjas de
      mañana y tarde y fichas fijo/½/doble;
    - el panel de resumen con cifras y leyenda;
    - el panel lateral con el selector No/½/1 y «Volver a automático»;
    - los paneles *Problemas a resolver* y *Carga por médico*;
    - las tarjetas de médicos con las ausencias dentro;
    - la paleta, IBM Plex y el modo oscuro.
26. Adaptaciones respecto al prototipo:
    - Textos en castellano.
    - La aplicación conserva su lógica: carga **mensual** (no semanal),
      cobertura mínimo/máximo (sin «objetivo»), preferencias por turno y
      reglas versionadas.
    - Se mantienen arrastrar y soltar y deshacer, que el prototipo no
      tenía.
    - Inicio y Ausencias dejan de ser pantallas: sus avisos pasan a
      *Problemas a resolver* y las ausencias, a las tarjetas.
    - La ficha de médico se sustituye por la tarjeta y el panel *Más reglas*.
    - Las fuentes se incluyen con `@fontsource` en lugar de Google Fonts,
      porque la aplicación funciona sin internet.
    - Se añadió en el servidor la operación «volver a automático»
      (`POST /liberar`).
27. Las capturas sobre el equipo de ejemplo destaparon tres detalles, ya
    corregidos: un margen inferior de más en la cabecera, campos de carga a
    todo el ancho y huecos dentro de las tarjetas.
28. La prueba de flujo completo encontró que las fichas de la tabla de carga
    no se podían arrastrar: quedaban fuera del contexto de dnd-kit, que solo
    envolvía la cuadrícula. Se subió el contexto (`ZonaArrastre`) para que
    abarque ambas.
29. Se reescribieron las pruebas de flujo completo (de 3 a 5), se rehicieron
    las capturas y se actualizó la guía de uso.

### Fase 9 — Vista en lista del calendario

30. El usuario planteó añadir un «turno por defecto» en las tarjetas de los
    médicos; tras aclarar el significado, decidió que marcar **Fijo** en la
    cuadrícula basta y no se cambió nada.
31. A petición del usuario, el calendario puede verse también **en lista**
    (un día por fila con desplazamiento vertical), alternando con un botón.
    Se reutilizó la franja de cada turno para no duplicar lógica, la elección
    se recuerda en el navegador y se añadió una prueba de flujo completo. Las
    capturas detectaron que el festivo de la lista no tenía fondo gris
    (corregido).

### Fase 10 — Reglas que no persistían

32. El usuario dio de alta varios médicos, configuró su disponibilidad y vio
    que, al cambiar de pestaña y volver, los cambios no estaban. Se
    reprodujo con pruebas de flujo completo y aparecieron tres causas:
    - El autoguardado esperaba 450 ms y, si la tarjeta se cerraba antes, el
      temporizador se cancelaba y el cambio se perdía.
    - Al volver, la tarjeta se rellenaba con la copia en caché, anterior al
      guardado, y no volvía a leer.
    - Un médico nuevo sin carga mensual no guardaba ninguna regla, porque la
      carga era obligatoria.
    
    La cobertura semanal tenía el mismo problema de temporizador.
33. Arreglo: autoguardado que envía lo pendiente al cerrarse (y con
    `keepalive` al cerrar la página), guardados en orden y lecturas que los
    esperan, formularios que se cargan con lectura fresca, y `carga` opcional
    al guardar reglas (sin ella se conserva la anterior o queda sin definir).
    Cuatro pruebas nuevas cubren el caso.

### Fase 11 — «Generar» no asignaba nada; turno habitual

34. El usuario pulsaba «Generar calendario» y no aparecía nada. Analizando
    una copia de solo lectura de su base de datos:
    - Ninguno de los 8 médicos tenía **carga mensual**, así que ninguno
      entraba en el reparto. La aplicación lo decía solo en las tarjetas y
      en un panel bajo el calendario.
    - Cada médico tenía un turno **Fijo** cada día, usado como «turno por
      defecto», tal como se le había sugerido. Con la carga puesta, una
      simulación mostró que todos trabajarían los 20 días, con 3–6 médicos
      por turno frente a un máximo de 2.
35. Cambios:
    - Avisos junto al botón de generar (médicos sin carga, generación sin
      resultado) y campos de carga resaltados en las tarjetas.
    - A elección del usuario, un nuevo valor **Habitual** en la cuadrícula
      («si trabaja ese día, mejor este turno», preferencia +2), con su
      indicación en el panel de un turno.
    - Tras una copia de seguridad, los 40 «Fijo» del usuario se convirtieron
      en «Habitual». Con su configuración y una carga de ejemplo, la
      simulación da un calendario válido, con los 80 turnos en el habitual y
      10 turnos por médico.

### Fase 12 — Color de cada médico

36. A petición del usuario, cada médico tiene un color que se elige en su
    tarjeta, junto al nombre, y que colorea su nombre en el calendario. Es
    la primera migración de esquema tras la versión inicial (`0002`, columna
    `medico.color`). Se probó sobre una copia de los datos reales del
    usuario: hace la copia de seguridad automática, sube a 0002 y conserva
    todo.

### Fase 13 — Urgencias y domicilios por la tarde

37. Nuevo requisito: cada tarde, un médico de urgencias en el centro y otro
    de domicilios, distintos, repartidos uniformemente entre quienes pueden
    hacer tardes. Supuestos tomados (y documentados en las especificaciones,
    5.6 y P19):
    - solo con la tarde completa;
    - solo las tardes con al menos 2 médicos;
    - reparto proporcional a las tardes disponibles;
    - prioridad sobre la equidad de carga y las preferencias.
38. Primera versión del reparto con desviaciones escaladas: 12 pruebas
    fallaban (cobertura de 1 por la tarde) y el mes de ejemplo tardaba 8,4 s
    sin llegar al óptimo. Exigirlo solo con ≥ 2 médicos y medir la salida de
    una banda entera dejó el ejemplo en 0,7 s y óptimo.
39. Tabla `rol_tarde` (migración 0003), operación manual con intercambio,
    «volver a automático» y deshacer incluyen los papeles, validación al
    vuelo, XLSX e impresión. Simulado con una copia de los datos reales: 20
    de 20 tardes cubiertas y 2–3 de cada papel por médico.

### Fase 14 — Iconos de urgencias y domicilios (v2.3.1)

40. Las etiquetas URG/DOM pasaron a ser iconos SVG propios (luz de emergencia
    y casa), con nombre accesible, revisados con capturas ampliadas.

### Fase 15 — Todos trabajan cada día (v2.4)

41. Nueva regla general, activada por defecto y desactivable en
    Configuración (tabla `ajuste`, migración 0004): cada médico tiene algún
    turno cada día laborable en que puede. Va por delante de la cobertura
    máxima y de la carga, con avisos claros si chocan.
42. Las pruebas existentes de la API y de flujo completo usan 4 médicos con 1
    por turno, así que la desactivan de forma explícita; pruebas nuevas
    cubren la opción. La casilla de Configuración se actualiza al instante
    (antes esperaba al servidor y Playwright lo detectó). Con una copia de los
    datos reales del usuario (10 médicos, cargas de 20–25 turnos), la opción
    da un calendario sin avisos.

### Fase 16 — Turnos rotativos (v2.5)

43. Nueva regla: grupos de médicos que comparten unos turnos fijos por
    semanas alternas sin coincidir, en una subpestaña de «Médicos y reglas»
    (tablas `rotacion`*, migración 0005). Decisiones:
    - los demás miembros quedan excluidos la semana que no les toca;
    - la rotación manda sobre el «Fijo» de sus tarjetas (lo destapó una
      prueba con un médico que tenía ese turno como Fijo);
    - si el titular no puede, el turno queda libre.
44. Las capturas mostraron que la semana de inicio por defecto se calculaba
    desde el día 1 del mes (domingo en noviembre de 2026), así que empezaba en
    octubre; ahora es la primera semana con días laborables.
45. Una prueba de flujo completo fallaba de forma reproducible: tras pulsar
    «Regenerar» leía el calendario sin esperar a que terminase (el estado
    «Borrador» ya se veía antes). Se reprodujo la lógica aparte con la API
    (correcta) y se depuró la prueba hasta encontrar la causa. De paso, generar
    y leer el calendario esperan ahora a cualquier guardado pendiente.

### Fase 17 — Aplicación de escritorio GNOME (v2.6)

46. Se estudiaron las opciones para tenerla en el menú de aplicaciones de
    todos los usuarios y se eligió un **Flatpak** con una ventana GTK que
    envuelve la misma interfaz web, con datos locales por usuario y sin
    dejar el modo web. Antes de implementar se escribió y aprobó
    [diseno-escritorio.md](diseno-escritorio.md) (identificador
    `io.oriol.TurnosMedicos`).
47. **Núcleo común**: el arranque se separó en `arranque/servidor.py` (datos,
    puerto, aplicación) y dos envoltorios, web y escritorio. La API exige un
    token por arranque (cookie por puerto); `TURNOS_SIN_TOKEN` para
    desarrollo. Los datos de una versión más reciente se rechazan sin
    tocarlos, y SQLite espera si el otro modo está escribiendo
    (`busy_timeout`).
48. **Envoltorio GTK** con Adw.Application y WebKitGTK 6.0: pantallas de
    carga y error, descargas con «Guardar como», impresión, zoom, enlaces
    externos al navegador y tamaño de ventana recordado.
49. La prueba de humo con Xvfb demostró que cerrar con `try_close()` **no**
    ejecuta `pagehide`: se perdían los guardados pendientes. Ahora la vista
    navega a `about:blank` antes de salir y se espera a que el servidor
    termine esas peticiones. La prueba queda en `tests/escritorio`.
50. Icono (calendario con cruz médica, en el verde azulado de la interfaz),
    `.desktop` y AppStream, validados con `desktop-file-validate` y
    `appstreamcli`.
51. Manifiesto para GNOME 51 sin permiso de red, guion de empaquetado y un
    generador propio de dependencias (ruedas cp314 con sha256). Sin
    `flatpak-builder` en el equipo, se comprobó primero dentro del runtime
    GNOME 51 sin red que las dependencias, el servidor y la ventana
    funcionan.
52. Con el paquete ya instalado aparecieron tres problemas: pip intentaba
    desinstalar el MarkupSafe del SDK (`--ignore-installed`); el montaje
    `rofiles-fuse` de `flatpak-builder` fallaba en la carpeta del proyecto
    (`--disable-rofiles-fuse`); y la página no cargaba porque, sin permiso de
    red, el portal de proxy de GNOME rechaza la consulta de WebKit. Se
    resolvió sin dar permiso de red: el WebView no usa proxy (solo habla con
    127.0.0.1). La prueba de humo, ejecutada dentro de la aplicación
    instalada, pasa entera.

### Fase 18 — Reparto igualado de urgencias y domicilios (v2.6.1)

53. El usuario observó repartos como 3, 2 y 1 urgencias en un mes. La causa:
    la parte de cada médico era proporcional a sus tardes disponibles (17
    frente a 20 por ausencias), y la banda [⌊parte⌋, ⌈parte⌉] de cada uno
    admitía 3 para unos y 1 para otros sin penalizar nada. Ahora la parte se
    calcula **por niveles** (`partes_iguales`): todos lo mismo, salvo quien no
    tiene tardes suficientes, para cada papel y para los dos juntos.
54. Se probaron antes dos objetivos globales (suma de cuadrados y su versión
    lineal por tramos): reparten bien, pero en el caso de tamaño real (30
    médicos) pasaban de 4 s a más de 20 s y dejaban sin resolver las pasadas
    de equidad. Las bandas por médico conservan el tiempo de antes. Con una
    copia de los datos reales, noviembre pasó de 3/2/1 a 2 para todos.
55. La prueba de la ventana se ejecuta en su propia sesión de D-Bus: con la
    aplicación abierta en el escritorio, la prueba le pasaba el control en
    lugar de abrir su ventana.

### Fase 19 — Datos y festivos oficiales en Configuración (v2.7)

56. Petición: exportar e importar los datos, y buscar los festivos en las
    fuentes oficiales fijando el municipio del centro. Se buscaron fuentes
    consultables por programa: no hay una oficial única para los locales de
    toda España. **festivos.io** (en el catálogo de datos.gob.es) los
    recopila del BOE y de los boletines y datos abiertos autonómicos, por
    código INE y con la referencia oficial de cada festivo; para el municipio
    de prueba de 2026 coincidió al 100 % con lo verificado a mano en el BOCM. Para
    Madrid se añadió como respaldo el conjunto oficial de la Comunidad.
57. Cargar nunca borra ni cambia festivos del planificador: añade los que
    faltan y señala los distintos y los que solo están en sus datos.
58. Importar sustituye todo, con validación y copia previa, sin dependencias
    nuevas (el fichero va como cuerpo de la petición). Exportar es la copia
    de seguridad de siempre.
59. El paquete Flatpak necesita ahora permiso de red (solo para esta
    búsqueda). Las pruebas de flujo completo usan fuentes locales (`file://`).

### Fase 20 — Urgencias y domicilios según la presencia (v2.8)

60. Los usuarios confirmaron que las ausencias deben reducir la parte de
    urgencias y domicilios, pero como puede cambiar, es el ajuste
    `roles_segun_presencia` (activado por defecto). El peso de cada médico es
    `presencia()`: tardes con papel en que no está ausente (sus reglas no
    cuentan). `partes()` reparte por niveles con esos pesos, sin pasar de las
    tardes que puede hacer cada uno.
61. Minimizar la distancia a la parte exacta (fraccionaria) repartía bien,
    pero CP-SAT no podía demostrar el óptimo (la relajación lineal da 0) y el
    caso de tamaño real pasó de 4 a 32 s. Se volvió a las bandas, calculadas
    por **restos mayores** (`bandas()`): las unidades sobrantes van a los
    restos más altos, y solo los empates quedan abiertos. Así 2,06 y 1,75
    dan 2 a todos.
62. La banda del total (los dos papeles) se cruza con la suma de las de cada
    papel: calculadas por separado podían contradecirse (p. ej. 2 + 2 frente
    a 5), y entonces el óptimo dejaba de ser 0 y la resolución volvía a ser
    lenta (26 s → 7 s con 10 de 30 médicos con ausencias).
63. Una prueba de flujo completo falló una vez con el equipo cargado (justo
    tras las pruebas de Python) y no se reprodujo en 12 ejecuciones seguidas.

### Fase 21 — Informe de urgencias y domicilios (v2.9)

64. Nueva opción de exportar e imprimir: las urgencias y domicilios del mes,
    día a día y con el recuento por médico. Se comprobó el PDF que genera el
    navegador: una página A4 vertical, sin cambiar la orientación del
    calendario general.

### Fase 22 — Prototipo de interfaz nativa GNOME (v2.10)

65. El usuario pidió ver la aplicación como aplicación GNOME nativa, como
    alternativa y sin sustituir lo que hay. Se hizo un prototipo funcional en
    lugar de rehacerlo todo (la web tiene unas 4.200 líneas): calendario con
    generar, publicar, exportar y el diálogo de cada turno (No / ½ / 1,
    urgencias y domicilios), médicos y reglas, festivos y configuración. Unas
    1.300 líneas en `arranque/gnome`.
66. Es cliente de la misma API (servidor en un hilo, token), así no duplica
    reglas ni validaciones. Va en el mismo Flatpak como segunda entrada del
    menú (`io.oriol.TurnosMedicos.Nativa.desktop`, `turnos-gnome`).
67. Las capturas con Xvfb mostraron dos fallos de maquetación (la cuadrícula
    semanal de un médico aplastaba su título y las cinco columnas no cabían en
    ventanas estrechas): se corrigieron con una fila propia y una lista de días
    para ventanas estrechas. La prueba automática espera a condiciones y no a
    tiempos fijos (35 s → 7 s). La comparación y lo que falta, en
    [prototipo-gnome-nativo.md](prototipo-gnome-nativo.md).

### Fase 23 — Interfaz nativa completa (v2.11)

68. A petición del usuario se migró el resto de funciones a la interfaz
    nativa: arrastrar y soltar (`Gtk.DragSource` / `Gtk.DropTarget`, con la
    misma lógica que la web: mover, Ctrl copia, soltar fuera quita, desde la
    tabla de carga añade), deshacer y rehacer (fotos del estado manual y
    `PUT /manual`), generar alternativa, volver a automático todo el mes,
    problemas a resolver, ajuste del rango del mes, cuadrícula o lista,
    ausencias, «Más reglas», turnos rotativos, cobertura con excepciones,
    horarios, restaurar festivos e imprimir (informes dibujados con Cairo y
    Pango en un `Gtk.PrintOperation`, con PDF por «Imprimir a archivo»).
69. Las capturas con Xvfb (tema claro, oscuro y ventana estrecha) llevaron a
    tres ajustes: marcas ✓ en los turnos rotativos, botones de la barra que
    saltan de línea en ventanas estrechas y colores de mañana y tarde para el
    tema oscuro (libadwaita no pasa `prefers-color-scheme` al CSS propio: la
    ventana añade la clase `oscuro` según `Adw.StyleManager`).
70. Una prueba nueva recorre desde los widgets todas las funciones y comprueba
    el resultado en la API (21 s con las otras dos). Las diferencias que
    quedan con la web, en [prototipo-gnome-nativo.md](prototipo-gnome-nativo.md).

### Fase 24 — Tarjetas de médicos en paralelo en la interfaz nativa

71. A petición del usuario, los médicos de la interfaz nativa pasan de filas
    desplegables a **tarjetas abiertas en paralelo**, como en la web: un
    `Gtk.FlowBox` de 1 a 4 columnas, con las reglas de todos cargadas al abrir
    la pestaña. Con capturas a 1.800, 1.300 y 420 px se ajustó el ancho de la
    tarjeta: el `FlowBox` reparte según el ancho natural, que fijaban la fila de
    la carga y la de cada ausencia (ahora salta de línea con
    `natural-line-length`).

### Fase 25 — Mañana y tarde diferenciadas, y monitores anchos

72. En el calendario nativo, la tarde lleva un fondo ligeramente azulado (y
    la mañana uno cálido muy suave), también en tema oscuro; los avisos de
    cobertura siguen mandando. En monitores anchos (`Adw.Breakpoint` desde
    1.700 sp) problemas y carga por médico pasan a una columna al lado del
    calendario, que usa todo el ancho; las tarjetas de médicos ya no tienen
    ancho máximo (hasta 8 columnas). Comprobado con capturas a 2.400 y
    1.300 px, en claro y oscuro.

73. La carga por médico de la interfaz nativa pasa de lista a **tabla**, con
    las mismas columnas que la web (Total, M, T, Rango, Días 1½, Dobles,
    Urg., Dom.); el nombre es una ficha que se arrastra a un turno. La columna
    lateral de los monitores anchos se ensancha a 600 px para que quepa, con
    48 px de separación respecto al calendario.

74. Tarjetas de médicos de la interfaz nativa: turnos/mes sin decimales salvo
    los medios («15», «18,5») con «mín.» y «máx.», también en «Más reglas» y
    en el rango del mes; y la cuadrícula semanal con los colores de la web
    (fijo relleno, habitual con borde grueso, disponible con borde fino, «—»
    rayado), en tema claro y oscuro.

75. Interfaz nativa: arriba a la izquierda, el icono y el nombre de la
    aplicación (el icono va también en el paquete de Python, para verse sin
    Flatpak). El selector de mes pasa a la barra de botones del calendario y a
    las cabeceras de médicos y festivos, que también dependen del mes; los
    tres están sincronizados (`Ventana.selector_mes`). Las capturas en
    ventana estrecha mostraron que la cabecera de médicos imponía un ancho
    mínimo a toda la ventana (las pestañas se miden juntas): pasa a dos
    líneas en ventanas estrechas.

76. En el calendario nativo, urgencias y domicilios se marcan con los mismos
    iconos que la web (luz de emergencia y casa, `arranque/gnome/iconos`) en
    lugar de los textos URG y DOM.

### Fase 26 — Asignados frente a necesarios, opcional (v2.12)

77. Ajuste nuevo `mostrar_cobertura` (desactivado por defecto), en
    *Configuración → Vista del calendario* de las dos interfaces: muestra u
    oculta en cada turno la cifra «asignados/necesarios» (p. ej. «6/0–7»). El
    resaltado de los turnos incompletos o sobrecargados no depende de él. La
    interfaz nativa pide los ajustes antes que el calendario, para no dibujarlo
    con el valor anterior. Prueba de flujo completo nueva (19).

### Lecciones para futuras sesiones

- Revisar la interfaz con capturas reales encontró fallos que las pruebas no
  veían (ancho cero, textos partidos, mes por defecto equivocado).
- En entornos flatpak, comprobar desde el principio qué intérprete y qué
  herramientas existen en el sistema, que es donde se usará la aplicación.
- No usar `pkill -f` con un patrón que también aparezca en la misma línea de
  órdenes: se mata a sí mismo.
- En CP-SAT, preferir objetivos cuyo óptimo suele ser 0 (bandas) a los que
  tienen un óptimo positivo que la relajación lineal no acota: encuentra la
  solución enseguida pero no puede demostrar que es la mejor y agota el tiempo.
- Dentro de Flatpak, un mensaje de WebKit «This call is not available inside
  the sandbox» puede venir de un portal (aquí, el de proxy) y no del
  aislamiento de WebKit: mirar qué permisos exige cada portal.
- Las ventanas GTK se pueden probar sin pantalla con `xvfb-run`, y capturar
  con `Gtk.WidgetPaintable` + `render_texture`. Con `GDK_DEBUG=no-portals`
  los diálogos no salen en la sesión real del usuario.
