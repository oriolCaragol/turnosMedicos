# turnosMedicos — Arquitectura

| | |
|---|---|
| Versión de la aplicación | 2.12 |
| Fecha | 2026-10-17 |
| Para quién | Quien quiera entender cómo está construida la aplicación, sea para mantenerla o para aprender |
| Documentos relacionados | [mantenimiento.md](mantenimiento.md) (cada componente en detalle y cómo modificarlo), [especificaciones.md](especificaciones.md) (qué debe hacer), [diseno.md](diseno.md) (diseño inicial), [diseno-escritorio.md](diseno-escritorio.md) (modo escritorio), [prototipo-gnome-nativo.md](prototipo-gnome-nativo.md) (interfaz nativa), [documentacion-tecnica.md](documentacion-tecnica.md) (referencia e historia) |

Este documento explica **cómo encajan las piezas** y **por qué** están así. El
detalle de cada pieza, con ejemplos de código y recetas para cambiarla, está en
[mantenimiento.md](mantenimiento.md).

## Índice

1. [Qué problema resuelve](#1-qué-problema-resuelve)
2. [Vista general](#2-vista-general)
3. [Principios de diseño](#3-principios-de-diseño)
4. [Capas del núcleo](#4-capas-del-núcleo)
5. [Las tres formas de usar la aplicación](#5-las-tres-formas-de-usar-la-aplicación)
6. [Recorridos completos](#6-recorridos-completos)
7. [Modelo de datos](#7-modelo-de-datos)
8. [El motor de asignación](#8-el-motor-de-asignación)
9. [API](#9-api)
10. [Interfaces de usuario](#10-interfaces-de-usuario)
11. [Seguridad](#11-seguridad)
12. [Empaquetado y distribución](#12-empaquetado-y-distribución)
13. [Pruebas](#13-pruebas)
14. [Decisiones de arquitectura](#14-decisiones-de-arquitectura)
15. [Límites conocidos](#15-límites-conocidos)

---

## 1. Qué problema resuelve

Un equipo de médicos de un centro de salud trabaja de lunes a viernes en dos
turnos, mañana y tarde. Cada mes alguien (el **planificador**) tiene que decidir
quién trabaja cada turno respetando muchas reglas a la vez:

- cuántos médicos hacen falta en cada turno (**cobertura**);
- qué turnos puede, prefiere o debe hacer cada médico (**reglas**);
- cuántos turnos al mes le corresponden (**carga**), reducida si tiene **ausencias**;
- festivos, turnos rotativos entre grupos, quién hace **urgencias** y quién
  **domicilios** cada tarde, y que el reparto sea **equitativo**.

Hacerlo a mano lleva horas y casi siempre deja alguna regla sin cumplir. La
aplicación lo convierte en un **problema de optimización** que resuelve un
motor matemático en segundos, y deja al planificador retocar el resultado.

## 2. Vista general

```
                     ┌──────────────────────────── Equipo del usuario ─────────────────────────────┐
                     │                                                                              │
  Navegador ─────────┼──▶ ┌────────────────────────────┐                                            │
  (modo web)         │    │  Interfaz web (React)      │  interfaz/dist: HTML + JS compilados        │
                     │    └────────────┬───────────────┘                                            │
  Ventana GNOME ─────┼──▶ (la misma interfaz web en un WebView: modo escritorio)                     │
  (WebKitGTK)        │                 │ JSON por HTTP (127.0.0.1 + token)                          │
                     │    ┌────────────▼───────────────┐   ┌──────────────────────────────┐         │
  Ventana GNOME ─────┼──▶ │  API (FastAPI)             │◀──│ Interfaz nativa (GTK 4 /     │         │
  (nativa)           │    │  turnos.api                │   │ libadwaita) turnos.arranque  │         │
                     │    └────────────┬───────────────┘   │ .gnome — también cliente JSON│         │
                     │                 │                   └──────────────────────────────┘         │
                     │    ┌────────────▼───────────────┐                                            │
                     │    │  Servicios                 │  casos de uso: construir el mes, generar,  │
                     │    │  turnos.servicios          │  cambios manuales, reglas, festivos…       │
                     │    └─────┬──────────────┬───────┘                                            │
                     │          │              │                                                    │
                     │ ┌────────▼──────┐ ┌─────▼──────────────┐   ┌────────────────────────────┐    │
                     │ │ Motor         │ │ Datos              │──▶│ turnos.sqlite              │    │
                     │ │ OR-Tools      │ │ SQLAlchemy+Alembic │   │ ~/.local/share/turnosMedicos│   │
                     │ │ turnos.motor  │ │ turnos.datos       │   └────────────────────────────┘    │
                     │ └────────┬──────┘ └────────────────────┘                                     │
                     │ ┌────────▼──────────────────────────────┐                                    │
                     │ │ Dominio (tipos y reglas puras)        │  turnos.dominio                    │
                     │ └───────────────────────────────────────┘                                    │
                     └──────────────────────────────────────────────────────────────────────────────┘
                                    (opcional, solo al buscar festivos oficiales)
                                                    │
                                                    ▼  festivos.io, datos abiertos de la Comunidad de Madrid
```

Todo se ejecuta **en el equipo del usuario**: no hay servidor en internet ni
cuentas. Un solo proceso Python sirve la API y, en el modo web, también los
ficheros de la interfaz. La única conexión externa es opcional: consultar los
festivos oficiales.

| Pieza | Tecnología | Tamaño aproximado |
|---|---|---|
| Núcleo (dominio, motor, datos, servicios, API, exportación) | Python 3.14, OR-Tools, SQLAlchemy, Alembic, FastAPI | 5.000 líneas |
| Interfaz web | React 19 + TypeScript, Vite, TanStack Query, dnd-kit | 4.400 líneas |
| Arranque (servidor, modo escritorio, interfaz nativa) | Uvicorn, PyGObject (GTK 4, libadwaita, WebKitGTK) | 3.400 líneas |
| Pruebas | pytest, Vitest, Playwright | 175 + 27 + 19 pruebas |

## 3. Principios de diseño

Estas ideas explican casi todas las decisiones posteriores:

1. **El núcleo no sabe quién lo usa.** El motor no conoce la base de datos; la
   base de datos no conoce la API; la API no conoce la interfaz. Así cada capa
   se prueba sola y se puede cambiar sin tocar las demás.
2. **Una sola fuente de verdad: la API.** Las tres formas de usar la aplicación
   (navegador, ventana con WebView, ventana nativa) hablan con la misma API.
   Ninguna interfaz repite reglas de negocio ni validaciones.
3. **Lo que decide el usuario manda.** Las asignaciones puestas a mano se
   bloquean y el motor las respeta al regenerar. Los turnos quitados a mano
   quedan **vetados**. Regenerar cambia lo mínimo.
4. **Mejor un calendario con avisos que ninguno.** Si las reglas son
   imposibles, el motor entrega el mejor calendario posible y explica qué no
   se cumple y por qué, en lugar de fallar.
5. **Datos locales, sencillos y recuperables.** Un único fichero SQLite por
   usuario, con copia automática antes de cada migración y exportación e
   importación desde la propia aplicación.
6. **Números enteros siempre.** Las cargas se guardan en **medios turnos**
   (18,5 turnos = 37). Así no hay decimales en el motor ni en la base de datos;
   solo se convierte al mostrar.

## 4. Capas del núcleo

```
src/turnos/
  dominio/     tipos y reglas puras (sin dependencias)
  motor/       el problema de optimización (depende solo de dominio)
  datos/       tablas, migraciones, creación de la base (depende de dominio)
  servicios/   casos de uso que unen datos y motor
  api/         rutas HTTP, esquemas de entrada y salida
  exportar/    hoja de cálculo XLSX
  recursos/    datos que se distribuyen: festivos precargados, municipios del INE
  arranque/    cómo se pone en marcha: web, escritorio (WebView) y nativa (GTK)
```

La regla de dependencias es estricta: **cada capa solo importa las de abajo**.

```
arranque ──▶ api ──▶ servicios ──▶ motor ──▶ dominio
                         │                      ▲
                         └──────▶ datos ────────┘
```

| Capa | Responsabilidad | Ejemplo |
|---|---|---|
| `dominio` | Conceptos del problema y cálculos que no dependen de nada: turnos y sus mitades, elegibilidad, ausencias, ajuste de la carga por ausencias | `ajustar_rango(rango, dias, ausencias)` reduce la carga en proporción a los días ausentes |
| `motor` | Traducir un mes a un modelo matemático, resolverlo y explicar el resultado | `generar(problema) -> Resultado` |
| `datos` | Guardar y leer: tablas SQLAlchemy, migraciones Alembic, datos iniciales | `inicializar(ruta) -> Engine` crea o actualiza la base |
| `servicios` | Casos de uso: construir el problema de un mes desde la base, guardar el resultado, aplicar cambios manuales, reglas versionadas por fecha, importar, festivos oficiales | `generar_mes(sesion, año, mes)` |
| `api` | Exponer los servicios por HTTP con validación de entrada y salida | `POST /api/periodos/2026/11/generar` |
| `arranque` | Arrancar el servidor y la interfaz adecuada | `turnos`, `turnos-escritorio`, `turnos-gnome` |

## 5. Las tres formas de usar la aplicación

Las tres comparten el arranque del servidor (`arranque/servidor.py`): preparar
los datos, reservar un puerto en `127.0.0.1`, crear la aplicación FastAPI con un
**token** nuevo y arrancar Uvicorn.

| Modo | Orden | Interfaz | Para qué |
|---|---|---|---|
| Web | `turnos` | La interfaz React en el navegador del sistema | Desarrollo y uso desde el navegador |
| Escritorio | `turnos-escritorio` | La misma interfaz React dentro de una ventana GNOME (WebKitGTK) | Aplicación de escritorio con la interfaz completa |
| Nativa | `turnos-gnome` | Pantallas GTK 4 y libadwaita escritas en Python | Alternativa con el aspecto y la accesibilidad de GNOME |

```
              arranque/servidor.preparar(puerto, con_token)
                 │  inicializar datos (migraciones con copia previa)
                 │  reservar puerto en 127.0.0.1
                 │  crear_app(motor, token)
                 ▼
            Servidor  ──ejecutar()──▶ modo web: bloquea, abre el navegador con ?token=…
                      ──iniciar_en_hilo()──▶ modo escritorio / nativo: la ventana GTK
                                              usa el servidor desde el mismo proceso
```

El paquete Flatpak lleva los tres; el menú de aplicaciones muestra dos
entradas: «Turnos médicos» (escritorio) y «Turnos médicos (nativa)».

## 6. Recorridos completos

Seguir una operación de principio a fin es la mejor forma de entender cómo
colaboran las capas.

### 6.1 Generar el calendario de un mes

```
Usuario pulsa «Generar»
  │
  ▼ Interfaz ── POST /api/periodos/2026/11/generar {"alternativa": false}
  │
  ▼ api/rutas/periodos.generar ── abre una sesión de base de datos (una transacción por petición)
  │
  ▼ servicios/periodos.generar_mes
  │   1. obtener_periodo(crear=True): la fila del mes en `periodo`
  │   2. construir(): lee de la base todo lo del mes y crea un `Problema` del motor:
  │        días laborables (sin festivos), cobertura de cada día y mitad,
  │        reglas vigentes de cada médico, carga ajustada por ausencias,
  │        saldo de meses publicados, rotaciones, lo bloqueado y vetado a mano,
  │        el calendario anterior (para cambiar lo mínimo) y los ajustes generales
  │   3. motor.generar(problema)
  │        preparar(): separa lo ya decidido (fijos, bloqueados, rotaciones) de los candidatos
  │        diagnostico.comprobar(): detecta causas de imposibilidad antes de resolver
  │        _Modelo: variables, restricciones y pasadas de optimización (sección 8)
  │        validar(): comprueba el resultado y genera los avisos
  │   4. guarda asignaciones, urgencias/domicilios, causas y la carga objetivo
  │
  ▼ La ruta devuelve el calendario completo (leer_calendario) como JSON
  │
  ▼ La interfaz lo dibuja: cuadrícula, avisos, tabla de carga
```

Puntos clave:

- El motor **no toca la base de datos**: recibe un `Problema` (objetos de
  Python inmutables) y devuelve un `Resultado`. Por eso se prueba con datos
  inventados en milisegundos.
- La transacción es **una por petición**: si algo falla a mitad, no se guarda
  nada a medias.
- Los avisos de incumplimiento **no se guardan**: se recalculan al leer el
  calendario, así reflejan siempre los datos actuales.

### 6.2 Un cambio manual (arrastrar a un médico)

```
Interfaz calcula los cambios (cambiosAlSoltar en la web, cambios_al_soltar en la nativa)
  │  p. ej. [{medico_id: 3, fecha: "2026-11-04", mitades: []},
  │          {medico_id: 3, fecha: "2026-11-05", mitades: ["T1","T2"]}]
  ▼ POST /api/periodos/2026/11/cambios
  ▼ servicios/periodos.aplicar_cambios
  │   deja a ese médico ese día exactamente en esas mitades, marca lo puesto como
  │   bloqueado (origen MANUAL) y lo quitado como veto, para que el motor lo respete
  ▼ devuelve el calendario; la interfaz guarda una «foto» previa para Deshacer
```

**Deshacer** no es una operación inversa: la interfaz guarda la foto del estado
manual (asignaciones, vetos, papeles) antes de cada cambio y, al deshacer, pide
al servidor que la restaure (`PUT /manual`).

### 6.3 Guardar las reglas de un médico

Las reglas tienen **versiones por fecha**. Guardar con `vigente_desde =
2026-11-01` escribe una «foto» completa que vale desde noviembre en adelante;
los meses anteriores siguen con la versión que tenían. Así, cambiar las reglas
no altera calendarios ya publicados.

```
PUT /api/medicos/3/reglas {vigente_desde, elegibilidad, jornadas, carga, carga_por_turno, preferencias}
  ▼ servicios/reglas.guardar_reglas: borra la versión de esa fecha (si existía) y escribe la nueva
  ▼ al construir un mes, leer_reglas(médico, fecha) toma la última versión con vigente_desde ≤ fecha
```

### 6.4 Arranque del modo escritorio

```
turnos-escritorio
  ▼ Adw.Application (una sola instancia: abrirla otra vez enfoca la ventana)
  ▼ ventana con pantalla «Abriendo turnos…»
  ▼ hilo: preparar(puerto=0) + iniciar_en_hilo()  ── migraciones, puerto libre, token
  ▼ el WebView carga http://127.0.0.1:<puerto>/?token=…
  ▼ el servidor guarda el token en una cookie y redirige; la interfaz web funciona igual que en el navegador
Al cerrar: la vista sale de la página (pagehide envía guardados pendientes),
se espera a que el servidor termine esas peticiones y se detiene.
```

## 7. Modelo de datos

Un fichero SQLite, `~/.local/share/turnosMedicos/turnos.sqlite`, con 21 tablas.

```
Configuración            Médicos y reglas                         Calendario de cada mes
─────────────            ────────────────                         ──────────────────────
ajuste                   medico ──┬── elegibilidad  (versionada)   periodo ──┬── asignacion
horario_turno                     ├── jornada_semanal (versionada)           ├── rol_tarde
festivo                           ├── carga        (versionada)              ├── veto
carga_festivos                    ├── preferencia                            ├── aviso (solo causas)
cobertura_semanal                 └── ausencia                               └── carga_ajustada
cobertura_fecha          rotacion ──┬── rotacion_medico
                                    └── rotacion_hueco
```

| Grupo | Tablas | Notas |
|---|---|---|
| Configuración | `ajuste` (clave → valor JSON), `horario_turno`, `festivo`, `carga_festivos` (qué años se cargaron y si están completos), `cobertura_semanal`, `cobertura_fecha` (excepciones) | La cobertura se guarda **por mitad de turno** (M1, M2, T1, T2) para admitir jornadas de turno y medio |
| Médicos | `medico`, `elegibilidad`, `jornada_semanal`, `carga`, `preferencia`, `ausencia` | Las tres primeras de reglas llevan `vigente_desde` (versiones) |
| Rotaciones | `rotacion`, `rotacion_medico` (orden), `rotacion_hueco` (turnos que comparten) | |
| Mes | `periodo`, `asignacion` (médico, fecha, **mitad**, origen, bloqueada), `rol_tarde`, `veto`, `aviso`, `carga_ajustada` (rango calculado, manual y objetivo de equidad) | Una asignación es **un médico en una mitad**: un turno completo son dos filas |

El esquema evoluciona con **migraciones Alembic** (`datos/migraciones/versions`,
de 0001 a 0005). Al arrancar, la aplicación aplica las pendientes y hace antes
una copia del fichero. Si el fichero viene de una versión **más reciente**, se
niega a abrirlo sin tocar nada.

## 8. El motor de asignación

Es el corazón de la aplicación. Usa **CP-SAT** de Google OR-Tools, un
resolvedor de programación con restricciones.

### 8.1 Variables

Una variable booleana por cada **candidato** (médico, día, turno) que el motor
puede decidir: `x[(médico, día, turno)] = 1` si lo hace. Lo ya decidido (fijos,
bloqueados, rotaciones) no son variables: entran como constantes. Para
urgencias y domicilios, otra variable booleana por (médico, día, papel).

### 8.2 Restricciones duras y blandas

- **Duras** (siempre se cumplen): como mucho un turno por médico y día (el motor
  nunca crea jornadas largas), solo candidatos elegibles, un papel por médico y
  solo si hace la tarde completa.
- **Blandas** (se cumplen si se puede): cobertura mínima y máxima, carga, todos
  trabajan cada día, urgencias y domicilios cubiertos. Se modelan con variables
  de **holgura** (`falta`, `sobra`, `defecto`, `exceso`) que se minimizan.
  Gracias a esto siempre hay solución y se sabe exactamente qué no se cumple.

### 8.3 Optimización lexicográfica por pasadas

En vez de una suma ponderada de objetivos (difícil de ajustar), el motor
optimiza **por orden de prioridad**: resuelve el primer objetivo, fija su valor
como restricción y pasa al siguiente.

| Orden | Pasada | Qué minimiza |
|---|---|---|
| 1 | cobertura mínima | médicos que faltan en cada mitad |
| 2 | todos trabajan cada día | días sin turno (si la opción está activa) |
| 3 | cobertura máxima | médicos de más |
| 4 | urgencias y domicilios | tardes sin alguno de los papeles |
| 5 | carga | turnos fuera del rango de cada médico |
| 6–7 | reparto de urgencias y domicilios | desviación respecto a la parte de cada uno (la mayor y la suma) |
| 8–9 | equidad | desviación respecto al objetivo de carga de cada uno (la mayor y la suma) |
| 10 | preferencias | maximiza turnos preferidos y habituales, minimiza los evitados |
| 11 | estabilidad | cambios respecto al calendario anterior (al regenerar) |

Cada pasada usa la solución anterior como punto de partida (*hints*). Con un
solo hilo y semilla fija, el resultado es **reproducible**: los mismos datos dan
el mismo calendario.

### 8.4 Antes y después de resolver

- **Diagnóstico** (`motor/diagnostico.py`): antes de resolver, comprueba
  imposibilidades evidentes (un día sin médicos suficientes disponibles, una
  carga inalcanzable) y genera **causas** legibles.
- **Validación** (`motor/validacion.py`): después, comprueba el calendario
  contra todas las reglas y genera los **incumplimientos** que ve el usuario,
  emparejados con su causa si la hay.

## 9. API

FastAPI expone 32 rutas (46 operaciones) bajo `/api`, agrupadas por recurso. Los esquemas
de entrada y salida son modelos Pydantic (`api/esquemas.py`): FastAPI valida
cada petición, rechaza lo incorrecto con un 422 y genera automáticamente la
especificación **OpenAPI**, de la que la interfaz web obtiene sus tipos
TypeScript.

| Recurso | Rutas principales |
|---|---|
| Médicos y reglas | `/api/medicos`, `/api/medicos/{id}`, `/api/medicos/{id}/reglas` |
| Ausencias | `/api/ausencias`, `/api/ausencias/{id}` |
| Festivos | `/api/festivos`, `/api/festivos/anios`, `/restaurar/{año}`, `/municipios`, `/oficiales/{año}` |
| Cobertura | `/api/cobertura/semanal`, `/api/cobertura/fechas/{fecha}` |
| Configuración | `/api/horarios`, `/api/ajustes`, `/api/estado`, `/api/copia-de-seguridad`, `/api/importar` |
| Turnos rotativos | `/api/rotaciones`, `/api/rotaciones/{id}` |
| Calendario del mes | `/api/periodos/{año}/{mes}` y `/generar`, `/cambios`, `/liberar`, `/manual`, `/carga/{médico}`, `/publicar`, `/reabrir`, `/exportar.xlsx`, `/urgencias-domicilios.xlsx` |

Casi todas las operaciones sobre el mes **devuelven el calendario completo**:
la interfaz no tiene que adivinar cómo ha quedado tras un cambio.

## 10. Interfaces de usuario

### 10.1 Interfaz web (React)

```
interfaz/src/
  api/          cliente fetch, consultas TanStack Query, tipos generados del OpenAPI
  calendario/   lógica pura del calendario (soltar, jornadas, estados) y deshacer/rehacer
  componentes/  piezas reutilizables: cabecera, cajón lateral, cuadrícula de elegibilidad…
  medicos/      tarjeta de médico, «Más reglas», selector de color
  rotaciones/   tarjeta de turno rotativo y cálculo de semanas
  paginas/      una página por pestaña, más las vistas para imprimir
  util/         fechas, textos, colores, mes compartido, guardado automático
```

- **Estado del servidor con TanStack Query**: cada dato es una consulta con
  clave (`["calendario", 2026, 11]`); tras un cambio se invalidan las claves
  afectadas y se vuelven a pedir. No hay un almacén global propio.
- **Guardado automático seguro** (`useAutoguardado`): las tarjetas guardan solas
  tras una pausa; si el usuario cambia de pestaña o cierra, lo pendiente se
  envía igualmente (incluso al cerrar, con `fetch keepalive`), y las lecturas
  esperan a los guardados en curso.
- **Arrastrar y soltar** con dnd-kit, con la lógica separada en
  `calendario/logica.ts` y probada con Vitest.

### 10.2 Interfaz nativa (GTK 4 / libadwaita)

```
src/turnos/arranque/gnome/
  aplicacion.py  ventana.py  cliente.py  comun.py  estilos.css  iconos/
  calendario.py  imprimir.py  medicos.py  rotaciones.py  cobertura.py  festivos.py  configuracion.py
```

- Es **cliente JSON de la misma API** (`ClienteApi`), con las peticiones en un
  hilo para no congelar la ventana.
- Cada pantalla se recarga al mostrarse si algo cambió (`invalidar`).
- Se adapta al ancho con `Adw.Breakpoint`: pestañas abajo y lista de días en
  ventanas estrechas; problemas y carga al lado del calendario en monitores
  anchos.
- Imprime con `Gtk.PrintOperation`, dibujando los informes con Cairo y Pango.

## 11. Seguridad

La aplicación no tiene cuentas de usuario porque es **local y de un solo
usuario por cuenta del sistema**. Las medidas son proporcionadas a ese uso:

| Riesgo | Medida |
|---|---|
| Acceso desde otro equipo de la red | El servidor escucha **solo en 127.0.0.1** |
| Otra cuenta del mismo equipo se conecta al puerto | **Token aleatorio por arranque**: la primera página lo trae en la dirección, el servidor lo guarda en una cookie `HttpOnly`, `SameSite=Strict` y exclusiva de ese puerto; la API responde 401 sin ella |
| Datos de un usuario visibles para otro | Cada cuenta tiene su propio fichero en su carpeta personal |
| Aplicación de escritorio con más permisos de los necesarios | El Flatpak solo puede acceder a `~/.local/share/turnosMedicos` y a la red (esta, solo para buscar festivos) |
| Pérdida de datos al actualizar | Copia automática antes de cada migración; rechazo de datos de una versión más nueva |
| Importar un fichero cualquiera | Se valida (SQLite, integridad, tablas, versión), se migra en una carpeta temporal y se guarda una copia de los datos actuales antes de sustituirlos |

## 12. Empaquetado y distribución

```
scripts/empaquetar-flatpak.sh
  1. compila la interfaz web (npm run build → interfaz/dist)
  2. construye la rueda de Python de la aplicación
  3. flatpak-builder con empaquetado/flatpak/io.oriol.TurnosMedicos.yml
       runtime org.gnome.Platform 51 (Python 3.14, GTK 4, libadwaita, WebKitGTK)
       dependencias de Python como ruedas ya compiladas (python3-dependencias.json)
  4. build/turnos-medicos-<versión>.flatpak
sudo flatpak install --system build/turnos-medicos-<versión>.flatpak   → menú de todos los usuarios
```

Las dependencias de Python se fijan a las mismas versiones del entorno de
desarrollo con un generador propio (`scripts/generar-dependencias-flatpak.py`),
así el paquete se construye sin compilar nada ni descargar durante el proceso.

## 13. Pruebas

| Nivel | Herramienta | Qué cubre |
|---|---|---|
| Unidad e integración del núcleo | pytest (175) | dominio, festivos, base de datos y migraciones, motor (restricciones, imposibilidad, equidad, reparto de papeles, rotaciones, rendimiento), validación, toda la API, exportación, importación, arranque y token |
| Lógica de la interfaz web | Vitest (27) | cuadrícula de elegibilidad, campo de turnos, lógica de soltar y del calendario |
| Flujo completo de la web | Playwright (19) | la aplicación real en un navegador: generar, arrastrar, deshacer, publicar, tarjetas, configuración, importar… |
| Ventanas GTK | pytest con Xvfb (dentro de los 175) | el modo escritorio (carga, guardado al cerrar) y la interfaz nativa (todas sus funciones desde los widgets) |

La sección 7 de [mantenimiento.md](mantenimiento.md) explica cómo ejecutarlas
y cómo añadir pruebas.

## 14. Decisiones de arquitectura

| # | Decisión | Alternativas consideradas | Por qué |
|---|---|---|---|
| A1 | Aplicación **local** con servidor en 127.0.0.1 | Servicio en internet; aplicación sin servidor | Datos sensibles que no deben salir del equipo, sin infraestructura que mantener; un servidor local permite usar tecnología web para la interfaz |
| A2 | **Python** para el núcleo | Java, TypeScript | OR-Tools tiene su mejor interfaz en Python; FastAPI y SQLAlchemy son maduros y legibles |
| A3 | **OR-Tools CP-SAT** con pasadas lexicográficas | Heurísticas a mano, programación lineal entera, una suma ponderada de objetivos | Encuentra calendarios óptimos en segundos; las pasadas evitan ajustar pesos y hacen explícitas las prioridades |
| A4 | Restricciones **blandas con holguras** | Restricciones duras | Siempre hay un calendario y se puede explicar qué falla |
| A5 | **SQLite** + SQLAlchemy + Alembic | Ficheros JSON, PostgreSQL | Un fichero, transacciones, sin instalar nada; Alembic actualiza los datos entre versiones con seguridad |
| A6 | **Medios turnos** como unidad | Decimales | Sin errores de redondeo en el motor ni en la base |
| A7 | Reglas **versionadas** por fecha | Reglas únicas | Cambiar reglas no altera los meses ya planificados |
| A8 | Interfaz **web (React)** servida por el propio servidor | Interfaz nativa desde el principio | Arrastrar y soltar y vistas ricas con poco código; se ve igual en navegador y escritorio |
| A9 | **API como única fuente de verdad** para todas las interfaces | Que la interfaz nativa llame directamente a los servicios | No duplicar reglas ni validaciones; todo lo probado en la API vale para las tres |
| A10 | Modo escritorio con **WebView** dentro de GTK, empaquetado en **Flatpak** | Electron; paquetes RPM | Ligero (usa el WebKit del runtime de GNOME), aislado, instalable para todos los usuarios |
| A11 | **Token por arranque** en vez de usuarios | Inicio de sesión | Un solo usuario por cuenta; el token basta para aislar cuentas del mismo equipo |
| A12 | Festivos oficiales de **festivos.io** y datos abiertos de Madrid | Leer el BOE y los boletines directamente | No hay una fuente oficial única y legible por programa para los festivos locales de toda España; festivos.io conserva la referencia oficial de cada festivo |

## 15. Límites conocidos

- Un solo planificador a la vez por cuenta; no hay edición simultánea.
- Fines de semana, guardias y solicitudes de cambio de los médicos están fuera
  de alcance (ver [especificaciones.md](especificaciones.md)).
- La «alternativa» busca el calendario válido más parecido con unos cuantos
  cambios, no repartos radicalmente distintos.
- Dos interfaces completas (web y nativa) duplican el trabajo de cada cambio
  visual mientras convivan.
