# turnosMedicos — Diseño técnico (BORRADOR)

| | |
|---|---|
| Estado | v1.1 — interfaz con Node (React) |
| Última actualización | 2026-10-14 |
| Basado en | [especificaciones.md](especificaciones.md) v1.0 |

Las referencias del tipo *(E-5.2)* apuntan a secciones de las
especificaciones. Las decisiones de diseño están en la
[sección 11](#11-decisiones-de-diseño).

---

## 1. Visión general

Aplicación web local: un único proceso Python que expone una API JSON, sirve
la interfaz (una aplicación React ya compilada) y guarda los datos en un
fichero SQLite. Node solo se usa para compilar la interfaz, no en ejecución. El planificador lo arranca en su PC y
lo usa desde el navegador en `http://localhost:8000`. No necesita internet.

```
┌──────────────────────────── PC del planificador ────────────────────────────┐
│                                                                             │
│  Navegador            Aplicación (FastAPI)                                  │
│  (React) ──JSON/HTTP─▶ ├── api/       rutas JSON + ficheros de la interfaz  │
│                        ├── servicios/ casos de uso (generar, publicar…)     │
│                        ├── motor/     modelo de asignación (OR-Tools)       │
│                        ├── exportar/  XLSX                                  │
│                        └── datos/     acceso a SQLite (SQLAlchemy)          │
│                                          │                                  │
│                                          ▼                                  │
│                                   turnos.sqlite                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Tecnologías

| Pieza | Elección | Motivo |
|---|---|---|
| Lenguaje | Python ≥ 3.13 (el del sistema: 3.14 en Fedora 43) | OR-Tools tiene su mejor interfaz en Python; un solo lenguaje para todo. |
| Motor de asignación | Google OR-Tools, resolvedor **CP-SAT** | Resolvedor de restricciones gratuito y muy eficiente; el problema (≈30 médicos × 23 días × 4 mitades) es pequeño para él. |
| Servidor web | FastAPI + Uvicorn | Ligero, tipado, fácil de probar. |
| Interfaz | **React + TypeScript**, compilado con **Vite** (Node) | Permite una interfaz rica: arrastrar y soltar en el calendario, validación al instante, edición de cuadrículas sin recargar. |
| Arrastrar y soltar | dnd-kit | Librería React mantenida, accesible (también funciona con teclado). |
| Datos en la interfaz | TanStack Query | Caché y recarga de los datos de la API. Cada cambio del calendario devuelve el calendario completo ya validado; al ser un servidor local la respuesta es inmediata y no hacen falta actualizaciones optimistas. |
| Estilos | CSS Modules + variables CSS | Sin dependencias extra; estilos de impresión con `@media print`. |
| Base de datos | SQLite + SQLAlchemy 2 + Alembic (migraciones) | Un único fichero, fácil de copiar (E-8). Las migraciones permiten actualizar la aplicación sin perder datos. |
| Exportación XLSX | openpyxl | Estándar, sin dependencias nativas. |
| Exportación PDF | Vista imprimible con CSS `@media print` → "Imprimir / Guardar como PDF" del navegador | Evita dependencias nativas (WeasyPrint necesita librerías del sistema). |
| Gestión del proyecto | `pyproject.toml` + entorno virtual (`venv` + `pip`) | Usa el Python del sistema; no requiere instalar nada más. |
| Pruebas | pytest (Python); Vitest + Testing Library (interfaz); Playwright con el Chromium del sistema (flujo completo, `scripts/e2e.sh`) | — |

FastAPI genera un esquema OpenAPI; a partir de él se generan los tipos
TypeScript de la interfaz (`openapi-typescript`), para que el contrato entre
ambas partes se compruebe al compilar.

## 3. Estructura del proyecto

```
turnosMedicos/
├── pyproject.toml
├── src/turnos/
│   ├── __main__.py          # arranque: crea la BD si no existe, abre el navegador
│   ├── config.py            # ruta del fichero de datos, puerto
│   ├── dominio/             # tipos puros, sin BD ni web
│   │   ├── modelos.py       # Medico, Turno, Mitad, Hueco, Asignacion…
│   │   ├── calendario.py    # días laborables, festivos
│   │   └── carga.py         # ajuste proporcional por ausencias (E-5.2)
│   ├── motor/
│   │   ├── entrada.py       # construye el problema a partir del dominio
│   │   ├── diagnostico.py   # comprobaciones previas de viabilidad (6.4)
│   │   ├── modelo_cpsat.py  # variables, restricciones, objetivos
│   │   └── resultado.py     # solución + avisos legibles
│   ├── datos/
│   │   ├── tablas.py        # modelos SQLAlchemy
│   │   ├── repositorios.py
│   │   └── migraciones/     # Alembic
│   ├── servicios/           # generar, ajustar, bloquear, publicar, exportar
│   ├── exportar/            # xlsx.py (la vista imprimible es una página de la interfaz)
│   ├── api/
│   │   ├── rutas/           # medicos, cobertura, festivos, periodos…
│   │   └── esquemas.py      # modelos Pydantic de entrada/salida
│   └── recursos/festivos/   # madrid-2026.json, madrid-2027.json
├── tests/
│   ├── dominio/
│   ├── motor/               # casos pequeños con solución conocida
│   └── api/
└── interfaz/                # aplicación React (Node)
    ├── package.json
    ├── vite.config.ts       # en desarrollo, redirige /api al servidor Python
    ├── src/
    │   ├── api/             # cliente y tipos generados desde OpenAPI
    │   ├── paginas/         # Inicio, Medicos, Cobertura, Festivos, Ausencias, Calendario…
    │   ├── componentes/
    │   └── estilos/
    └── e2e/                 # pruebas Playwright
```

La interfaz compilada (`interfaz/dist/`) la sirve FastAPI en la raíz; la API
vive bajo `/api`.

El paquete `dominio` y el `motor` no dependen de la API ni de la base de
datos, para poder probarlos de forma aislada.

## 4. Modelo de datos

Todas las tablas tienen `id` entero autoincremental. Las fechas se guardan como
`DATE` ISO.

### 4.1 Configuración

| Tabla | Campos | Notas |
|---|---|---|
| `horario_turno` | `turno` (MAÑANA/TARDE), `inicio`, `corte`, `fin` | `corte` = hora que separa las dos mitades (E-4.1). 2 filas. |
| `festivo` | `fecha`, `descripcion`, `ambito` (NACIONAL/AUTONOMICO/LOCAL/OTRO) | Se precarga desde `recursos/festivos/` (E-4.2). |
| `carga_festivos` | `anio`, `calendario`, `completo`, `cargado_en` | Años ya precargados: no se vuelven a cargar en cada arranque, para respetar los cambios del planificador. Si un año estaba incompleto (faltaban los locales) y llega completo con una nueva versión, solo se añaden los festivos locales. |
| `cobertura_semanal` | `dia_semana` (0 = lunes … 4 = viernes), `mitad` (M1/M2/T1/T2), `minimo`, `maximo` | 20 filas. En la interfaz se edita por turno y se copia a sus dos mitades; se puede afinar por mitad. |
| `cobertura_fecha` | `fecha`, `mitad`, `minimo`, `maximo` | Excepciones por fecha (E-4.4). |

### 4.2 Médicos y reglas

| Tabla | Campos | Notas |
|---|---|---|
| `medico` | `nombre`, `codigo`, `activo` | E-4.3 |
| `elegibilidad` | `medico_id`, `dia_semana`, `turno`, `valor` (FIJO/DISPONIBLE/NO_DISPONIBLE) | 10 filas por médico (E-5.1). |
| `jornada_semanal` | `medico_id`, `dia_semana`, `tipo` (MANANA_MAS_MEDIA/TARDE_MAS_MEDIA/DOBLE o NULL) | Jornadas de 1,5 / 2 fijadas por el planificador (E-5.3). NULL anula desde esa fecha una jornada anterior. |
| `carga` | `medico_id`, `turno` (NULL = total), `minimo`, `maximo` | En **medios turnos** (enteros): 16–18,5 turnos se guarda como 32–37. |
| `preferencia` | `medico_id`, `dia_semana`, `turno`, `valor` (PREFIERE/EVITA) | E-5.4 |
| `ausencia` | `medico_id`, `desde`, `hasta`, `turno` (NULL = día completo) | Sin motivo (E-8). |

Las reglas se guardan con la fecha desde la que son válidas (`vigente_desde`)
en `elegibilidad`, `jornada_semanal` y `carga`, para que cambiar las reglas de
un médico no altere cómo se interpretan los meses ya publicados.

### 4.3 Periodos y asignaciones

| Tabla | Campos | Notas |
|---|---|---|
| `periodo` | `anio`, `mes`, `publicado_en` | Un periodo = un mes natural. `publicado_en` NULL = borrador. |
| `carga_ajustada` | `periodo_id`, `medico_id`, `turno`, `minimo_calc`, `maximo_calc`, `minimo_manual`, `maximo_manual`, `objetivo` | Resultado del ajuste por ausencias + sobrescritura (E-5.2). `objetivo` es la carga objetivo usada al generar; con ella se calcula el saldo de equidad de los meses siguientes (6.5). |
| `asignacion` | `periodo_id`, `medico_id`, `fecha`, `mitad`, `origen` (GENERADOR/MANUAL/FIJO), `bloqueada` | **Una fila por mitad**: un turno completo son 2 filas. Así la cobertura y los medios turnos se tratan igual. |
| `veto` | `periodo_id`, `medico_id`, `fecha`, `turno` | Turnos que el planificador ha quitado a mano; el motor no los vuelve a asignar. |
| `aviso` | `periodo_id`, `tipo` (CAUSA/INCUMPLIMIENTO), `mensaje`, `fecha`, `medico_id` | Conflictos de la última generación (E-6.4). |

## 5. Ajuste de la carga por ausencias

Implementa E-5.2 en `dominio/carga.py`:

1. `dias_mes` = días laborables del mes (sin festivos).
2. `dias_ausente` = suma, por cada día laborable del mes con ausencia, de 1
   (día completo) o 0,5 (un solo turno).
3. `factor = (dias_mes − dias_ausente) / dias_mes`.
4. `minimo_calc = redondear(minimo × factor)`, igual para el máximo, donde
   `redondear` lleva al medio turno más cercano (en medios turnos: entero
   más cercano; los empates, hacia arriba).
5. Si el planificador ha puesto `minimo_manual` / `maximo_manual`, prevalecen.

## 6. Motor de asignación

### 6.1 Entrada

Una estructura inmutable con: días laborables del mes, cobertura por día y
mitad, y para cada médico: huecos elegibles, fijos, jornadas especiales,
ausencias, carga ajustada, preferencias, histórico de carga y asignaciones
bloqueadas.

### 6.2 Preprocesado: lo que ya está decidido

Antes de construir el modelo se calculan las asignaciones **fijas** de cada
médico y día, que no son variables:

- Huecos *Fijo* de la cuadrícula (E-5.1).
- Jornadas de 1,5 / 2 de `jornada_semanal` (E-5.3).
- Asignaciones bloqueadas del periodo (E-6.1).

Se descartan las que caen en festivo o ausencia. Si un médico ya tiene algo
fijado un día, ese día el generador no le añade nada (el generador solo crea
jornadas de 1 turno, E-5.3 R-D1).

### 6.3 Variables

Sólo para los pares médico-día libres:

- `x[m,d,t]` ∈ {0,1}: el médico *m* hace el turno completo *t* (MAÑANA o
  TARDE) el día *d*. Solo existe si el turno es *Disponible* para *m*, no hay
  ausencia que lo cubra y no es festivo.

Los medios turnos nunca son variables: solo los crea el planificador.

### 6.4 Restricciones estrictas

Trabajando en **medios turnos** para que todo sea entero:

| # | Restricción | Formulación |
|---|---|---|
| R1 | Un turno al día como máximo (generador) | `x[m,d,M] + x[m,d,T] ≤ 1` |
| R2 | Cobertura mínima por mitad | `fijos[d,h] + Σ_m x[m,d,turno(h)] + falta[d,h] ≥ minimo[d,h]` |
| R3 | Cobertura máxima por mitad | `fijos[d,h] + Σ_m x[m,d,turno(h)] ≤ maximo[d,h]` |
| R4 | Carga mensual total | `cmin[m] − def[m] ≤ fijos[m] + 2·Σ x[m,·,·] ≤ cmax[m] + exc[m]` |
| R5 | Carga por tipo de turno (si existe) | Igual que R4, sumando solo el turno correspondiente. |

`falta`, `def` y `exc` son variables de holgura ≥ 0. En una solución
**válida** valen 0; si el problema no tiene solución sin ellas, sus valores
indican exactamente qué regla no se ha podido cumplir y por cuánto (6.6).

### 6.5 Objetivos (resolución lexicográfica)

Se resuelve en varias pasadas. En cada una se optimiza un objetivo y se
fija su valor óptimo como restricción para la siguiente:

1. **Validez**, en tres pasadas: minimizar `Σ falta` (huecos sin cubrir),
   después `Σ sobra` (personal por encima del máximo) y después
   `Σ def + Σ exc` (carga fuera de rango). Mejor un médico de más que un
   hueco sin cubrir. Si las tres valen 0, el calendario es válido.
2. **Equidad**, en dos pasadas: primero minimizar la mayor desviación
   `max_m |carga[m] − objetivo[m]|` y después la suma `Σ_m |carga[m] −
   objetivo[m]|`. Solo con la suma hay empates entre repartos muy
   desiguales y repartos equilibrados; la desviación al cuadrado los evita
   pero CP-SAT no llega a demostrar el óptimo en un tiempo razonable.
   - `objetivo[m]`: la demanda total del mes (suma de mínimos de cobertura,
     menos lo ya fijado) se reparte entre los médicos en proporción a sus
     rangos de carga ajustados, y se recorta a `[cmin, cmax]`.
   - Arrastre entre meses (E-6.3.4): a `objetivo[m]` se le resta parte del
     saldo acumulado de los meses publicados (lo que el médico hizo de más o
     de menos respecto a su objetivo), con un límite de ±1 turno (2 medios
     turnos) por mes para no desestabilizar.
3. **Preferencias**: maximizar huecos *PREFIERE* asignados − huecos *EVITA*
   asignados.
4. **Estabilidad** (solo al regenerar): minimizar el número de asignaciones
   que cambian respecto al calendario anterior del periodo.

### 6.6 Diagnóstico de inviabilidad (E-6.4)

Dos capas:

1. **Comprobaciones previas** (`motor/diagnostico.py`), rápidas y con
   mensajes muy concretos:
   - Mitad de un día con menos médicos posibles que su mínimo.
   - Mitad de un día donde los fijos ya superan el máximo.
   - Médico cuyos huecos posibles no alcanzan su carga mínima.
   - Médico cuyos fijos ya superan su carga máxima.
   - Capacidad total del equipo inferior a la demanda total del mes.
2. **Holguras del modelo**: si tras la pasada 1 alguna holgura es > 0, cada
   una se traduce en un aviso, p. ej. `falta[mar 11-nov, M1] = 1` →
   *"El martes 11/11 por la mañana falta 1 médico"*.

En ambos casos se guarda el calendario de **mejor esfuerzo** (el de la
pasada 1 y siguientes) con los huecos sin cubrir resaltados, y los avisos en
la tabla `aviso`.

### 6.7 Determinismo y alternativas (E-6.5)

- Semilla fija (`random_seed`), un solo hilo de búsqueda y límite de tiempo
  determinista (`max_deterministic_time`) en lugar de tiempo real, para que
  las mismas entradas den el mismo calendario en cualquier PC. (La búsqueda
  paralela determinista, `interleave_search`, resultó ~30 veces más lenta
  en un mes de ejemplo.)
- "Generar alternativa": se añade una restricción que obliga a cambiar al
  menos *k* turnos respecto al calendario actual. Se añade después de las
  pasadas de validez, para que la alternativa no sea peor (no deje huecos
  que el original cubría); si no existe, se informa.
- Una prueba automática genera dos veces el mismo mes y compara resultados.

### 6.8 Rendimiento (E-6.6)

Tamaño orientativo: 30 médicos × 23 días × 2 turnos ≈ 1.400 variables
booleanas. CP-SAT resuelve problemas de este tamaño en segundos. Cada pasada
tiene un límite de tiempo; si se alcanza, se usa la mejor solución encontrada
y se indica en pantalla que puede no ser óptima.

## 7. Interfaz

> **Nota (v1.2).** La interfaz se rediseñó a partir del prototipo
> `docs/ejemplo/ejemplo.html`: cabecera con el mes y pestañas, calendario en
> cuadrícula mensual, panel lateral por turno y tarjetas de médicos con sus
> ausencias. Las páginas Inicio, Ausencias y la ficha de médico ya no existen.
> La descripción actualizada está en
> [documentacion-tecnica.md, sección 9](documentacion-tecnica.md#9-interfaz);
> lo que sigue es el diseño original.

| Página | Contenido |
|---|---|
| **Inicio** | Mes en curso y siguiente, con su estado; acceso rápido a generar. |
| **Médicos** | Lista; ficha con selector "aplicar a partir de" (mes; por defecto el siguiente, que es el que se planifica), cuadrícula de elegibilidad (clic para alternar Fijo/Disponible/No disponible, o arrastrar sobre varias celdas para pintarlas de una vez; botones "solo mañanas", "solo tardes", "cualquiera"), jornadas especiales, carga mensual, preferencias. |
| **Cobertura** | Cuadrícula día de la semana × turno con mínimo/máximo; excepciones por fecha. |
| **Festivos** | Lista por año; añadir/quitar; cargar el calendario precargado (Madrid) de un año. |
| **Ausencias** | Lista por mes y por médico; alta rápida (médico, desde, hasta, turno). |
| **Calendario del mes** | Vista principal (abajo). |
| **Configuración** | Horario de los turnos y de sus mitades; copia de seguridad del fichero de datos. |

**Calendario del mes**:

- Una fila por día laborable; columnas MAÑANA y TARDE, cada una con los
  códigos de los médicos asignados. Los medios turnos se marcan con "½".
- Colores: verde = cubierto, rojo = falta personal, ámbar = sobra personal.
  Candado en las asignaciones bloqueadas.
- **Arrastrar y soltar**:
  - Arrastrar un médico de una celda a otra lo mueve; con Ctrl lo copia.
  - Arrastrar un médico desde el panel de resumen a una celda lo añade.
  - Soltar fuera del calendario lo quita de la celda.
  - Mientras se arrastra, las celdas se colorean según si el médico puede ir
    ahí (elegible y sin ausencia) o no; se puede soltar igualmente en una
    celda no válida, con aviso (el planificador tiene la última palabra,
    E-7).
  - Cada cambio hecho a mano queda **bloqueado** automáticamente.
- Clic en una celda → panel lateral con el detalle: añadir/quitar médicos,
  bloquear/desbloquear y convertir una asignación en jornada de 1,5 o 2
  turnos.
- Tras cada cambio, la API valida el calendario y la interfaz muestra al
  momento los avisos de reglas incumplidas, sin recargar la página.
- Deshacer / rehacer (Ctrl+Z / Ctrl+Y) de los cambios manuales y de las
  regeneraciones: antes de cada cambio la interfaz guarda una foto de
  asignaciones y vetos; deshacer pide al servidor que restaure esa foto.
- Todos los cambios manuales se reducen a una operación: "dejar a este médico,
  este día, exactamente en estas mitades" (más bloquear/desbloquear). Lo
  que el médico pierde queda vetado para el generador.
- Los incumplimientos se calculan siempre al vuelo sobre el calendario
  actual (`motor/validacion.py`, con los mismos textos que el motor); de la
  última generación solo se guardan las causas.
- Panel de resumen: turnos asignados frente al rango del mes, con opción de
  ajustar el rango a mano para ese mes (E-5.2).
- Panel de resumen por médico: turnos asignados frente a su rango ajustado,
  por total y por tipo, con el desvío marcado.
- Botones: *Generar*, *Generar alternativa*, *Publicar*, *Reabrir*,
  *Exportar XLSX*, *Imprimir / PDF*.
- Un periodo publicado se muestra en solo lectura hasta que se reabre.

## 8. Exportación

- **XLSX** (`GET /api/periodos/{año}/{mes}/exportar.xlsx`, `exportar/xlsx.py`),
  preparado para imprimirse en A4 horizontal, con tres hojas:
  - *Calendario*: un día por fila con los nombres de mañana y de tarde
    (horario en la cabecera, "(½)" en los medios turnos, festivos en gris) y,
    al final, las reglas que no se cumplen si las hay.
  - *Por médico*: un médico por fila y un día por columna (M, T, M+½T…),
    para que cada uno vea sus turnos.
  - *Resumen*: turnos, mañanas y tardes de cada médico frente a su rango,
    como números para poder operar con ellos.
- **Imprimible** (página `/imprimir?mes=AAAA-MM`, sin menús): el calendario
  con nombres en la primera página y la tabla por médico en la segunda, en A4
  horizontal; se imprime o se guarda como PDF desde el diálogo del
  navegador. Indica si el mes está publicado (y cuándo) o si es un borrador.
- **Copia de seguridad** (`GET /api/copia-de-seguridad`, botón en
  Configuración): copia consistente del fichero SQLite.

## 9. Arranque y distribución

La aplicación se ejecuta en **Linux (Fedora)**.

- Requisito: Node.js (`sudo dnf install nodejs`), solo para compilar la
  interfaz. Las dependencias npm se fijan a versiones exactas con al menos
  dos semanas de antigüedad.
- Instalación: `python3 -m venv .venv && .venv/bin/pip install -e .` y
  `cd interfaz && npm ci && npm run build`.
- Desarrollo: servidor Python con recarga automática + `npm run dev` (Vite)
  en paralelo.
- Arranque: `.venv/bin/turnos` arranca el servidor y abre el navegador.
  Opcionalmente, un acceso directo `.desktop` para lanzarla desde el menú.
- El fichero de datos se guarda en `~/.local/share/turnosMedicos/turnos.sqlite`
  (configurable).
- Copia de seguridad: botón que descarga una copia del fichero SQLite, y
  copia automática antes de cada migración de esquema.
- El servidor escucha solo en `127.0.0.1` (no accesible desde otros equipos).

## 10. Pruebas

- **Dominio**: días laborables, festivos, ajuste proporcional de la carga
  (incluido el redondeo y las ausencias de medio día).
- **Motor**: casos pequeños con solución conocida (3–4 médicos, 1 semana) para
  cada restricción; casos inviables que deben producir avisos concretos;
  determinismo; un caso de tamaño real (30 médicos, 1 mes) con límite de
  tiempo.
- **API**: pruebas de las rutas principales con el cliente de pruebas de
  FastAPI y una base de datos temporal.
- **Interfaz**: componentes con Vitest + Testing Library (cuadrícula de
  elegibilidad, celda del calendario, resumen por médico).
- **Flujo completo**: Playwright sobre la aplicación arrancada — configurar un
  equipo pequeño, generar un mes, mover un médico arrastrando y publicar.

## 11. Decisiones de diseño

| # | Pregunta | Decisión |
|---|---|---|
| D1 | Tecnologías | Python + FastAPI + SQLite + OR-Tools en el servidor; React + TypeScript + Vite en la interfaz, con arrastrar y soltar (sección 2). |
| D2 | Sistema operativo del planificador | Linux (Fedora); sin empaquetado (sección 9). |
| D3 | Orden de los objetivos | Validez → equidad → preferencias → estabilidad (6.5). |
| D4 | Arrastre de equidad entre meses | Limitado a ±1 turno por mes (6.5). |
| D5 | Idioma del código | Castellano, sin tildes ni ñ en los identificadores (p. ej. `Turno.MANANA`). Interfaz y documentación en castellano. |

## 12. Plan de implementación

| Fase | Contenido | Resultado verificable |
|---|---|---|
| 1 | Esqueleto del proyecto, dominio (calendario, festivos, carga) y pruebas | Pruebas del dominio en verde. |
| 2 | Motor CP-SAT con diagnóstico, sobre datos en memoria | Genera un mes de ejemplo desde un script; pruebas del motor en verde. |
| 3 | Base de datos, migraciones y carga de festivos precargados | La BD se crea al arrancar con los festivos cargados. |
| 4 | API de configuración + esqueleto de la interfaz React + páginas de médicos, cobertura, festivos y ausencias | Se puede configurar un equipo completo desde el navegador. |
| 5 | Calendario del mes: generar, arrastrar y soltar, bloquear, deshacer, publicar | Flujo completo de E-7 desde el navegador (prueba Playwright). |
| 6 | Exportación XLSX e imprimible | Ficheros correctos para un mes de ejemplo. |
| 7 | Guía de uso y documentación técnica (el acceso directo se descartó) | [guia-de-uso.md](guia-de-uso.md) y [documentacion-tecnica.md](documentacion-tecnica.md). |
