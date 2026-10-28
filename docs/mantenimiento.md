# turnosMedicos — Manual de mantenimiento

| | |
|---|---|
| Versión de la aplicación | 2.12 |
| Fecha | 2026-10-17 |
| Para quién | Quien vaya a mantener, modificar o estudiar el código |
| Leer antes | [arquitectura.md](arquitectura.md): la visión de conjunto (capas, recorridos, decisiones) |

Este manual recorre **cada componente** de la aplicación. Para cada uno explica
cuatro cosas:

- **Qué es**: su papel y dónde está el código.
- **Cómo se usa**: los conceptos y llamadas que hay que conocer, con ejemplos
  sacados del propio código.
- **Por qué se eligió**: qué alternativas había y qué se ganaba.
- **Cómo se mantiene y modifica**: qué tocar para cambiarlo, qué cuidar y cómo
  comprobar que sigue funcionando.

Al final hay **recetas** paso a paso para los cambios más habituales y una
sección de **solución de problemas** con los que ya han aparecido.

## Índice

1. [Mapa del repositorio](#1-mapa-del-repositorio)
2. [Entorno de desarrollo](#2-entorno-de-desarrollo)
3. [El núcleo en Python](#3-el-núcleo-en-python)
   - 3.1 [Paquete y dependencias](#31-paquete-y-dependencias) · 3.2 [Dominio](#32-dominio) · 3.3 [Motor (OR-Tools)](#33-motor-or-tools) · 3.4 [Datos (SQLAlchemy y Alembic)](#34-datos-sqlalchemy-y-alembic) · 3.5 [Servicios](#35-servicios) · 3.6 [Recursos](#36-recursos) · 3.7 [API (FastAPI y Pydantic)](#37-api-fastapi-y-pydantic) · 3.8 [Exportación (openpyxl)](#38-exportación-openpyxl)
4. [Interfaz web](#4-interfaz-web)
5. [Arranque y modo escritorio](#5-arranque-y-modo-escritorio)
6. [Interfaz nativa GNOME](#6-interfaz-nativa-gnome)
7. [Pruebas](#7-pruebas)
8. [Empaquetado Flatpak](#8-empaquetado-flatpak)
9. [Recetas](#9-recetas)
10. [Solución de problemas](#10-solución-de-problemas)
11. [Glosario](#11-glosario)

---

## 1. Mapa del repositorio

```
pyproject.toml              paquete Python: dependencias, órdenes, ficheros de datos incluidos
src/turnos/                 núcleo y arranque (Python)
  config.py                 ruta del fichero de datos
  dominio/                  modelos.py (tipos), calendario.py (festivos), carga.py (ajuste por ausencias)
  motor/                    entrada.py (problema y preprocesado), modelo_cpsat.py (resolución),
                            diagnostico.py (causas previas), validacion.py (incumplimientos),
                            resultado.py (avisos y textos), ejemplo.py (ejecutable de prueba)
  datos/                    tablas.py (esquema), bd.py (crear, migrar, copias), migraciones/ (Alembic)
  servicios/                periodos.py (el mes), reglas.py (versionadas), ajustes.py, rotaciones.py,
                            festivos_oficiales.py, importar.py
  recursos/                 festivos/*.json (precargados), municipios.json (INE)
  api/                      app.py (aplicación y token), esquemas.py (Pydantic), dependencias.py,
                            rutas/ (una por recurso), openapi.py (exporta el esquema)
  exportar/xlsx.py          hojas de cálculo
  arranque/                 servidor.py (común), web.py (turnos), escritorio/ (turnos-escritorio),
                            gnome/ (turnos-gnome, interfaz nativa)
  red/                      modo servidor (turnos servidor): orden.py, configuracion.py,
                            certificados.py, anuncio.py (mDNS), copias.py
interfaz/                   interfaz web (React + TypeScript)
  src/                      código (ver sección 4)
  e2e/                      pruebas de flujo completo (Playwright) y sus datos
  openapi.json              esquema de la API (generado, versionado)
tests/                      pruebas de Python, por capa
empaquetado/flatpak/        manifiesto, .desktop, AppStream, iconos, dependencias generadas
scripts/                    e2e.sh, empaquetar-flatpak.sh, generar-dependencias-flatpak.py
docs/                       documentación (este manual, arquitectura, especificaciones, guía…)
```

## 2. Entorno de desarrollo

### Requisitos

| Herramienta | Para qué | En Fedora |
|---|---|---|
| Python ≥ 3.13 (se usa 3.14) | El núcleo | `python3` |
| Node.js 22 y npm | Compilar la interfaz web | `nodejs npm` |
| Chromium | Pruebas de flujo completo | `chromium` |
| PyGObject, GTK 4, libadwaita, WebKitGTK 6.0 | Modo escritorio e interfaz nativa sin Flatpak | `python3-gobject gtk4 libadwaita webkitgtk6.0` |
| Xvfb, dbus-run-session | Pruebas de las ventanas sin pantalla | `xorg-x11-server-Xvfb dbus-daemon` |
| flatpak-builder | Crear el paquete | `flatpak-builder` |

### Puesta en marcha

```sh
python3 -m venv --system-site-packages .venv   # ve el PyGObject del sistema
.venv/bin/pip install -e '.[dev]'               # el paquete en modo editable + pytest, httpx, pyflakes
(cd interfaz && npm ci && npm run build)        # dependencias exactas y compilación
.venv/bin/turnos                                # modo web en http://127.0.0.1:8000
```

`pip install -e` instala el paquete «editable»: los cambios en `src/` se ven sin
reinstalar. Solo hay que reinstalar si cambia `pyproject.toml` (versión, órdenes
o ficheros de datos).

### Órdenes del día a día

| Qué | Orden |
|---|---|
| Modo web | `.venv/bin/turnos` |
| Interfaz web con recarga en caliente | `TURNOS_SIN_TOKEN=1 .venv/bin/turnos` y en otra terminal `cd interfaz && npm run dev` (Vite en el puerto 5173 redirige `/api` al 8000) |
| Modo escritorio sin Flatpak | `.venv/bin/turnos-escritorio` |
| Interfaz nativa sin Flatpak | `.venv/bin/turnos-gnome` |
| Probar con otros datos | `TURNOS_DATOS=/ruta/prueba.sqlite .venv/bin/turnos` |
| Ejecutar el motor con un ejemplo | `.venv/bin/python -m turnos.motor.ejemplo` |
| Crear o revisar la base de datos | `.venv/bin/python -m turnos.datos` |
| Comprobación estática | `.venv/bin/python -m pyflakes src tests` y `cd interfaz && npm run comprobar` |

> **VS Code instalado como Flatpak.** Su terminal es un entorno aislado sin Node
> ni el Python del sistema, y con otro `/tmp`. Hay que usar una terminal del
> sistema o anteponer `flatpak-spawn --host` a las órdenes.

---

## 3. El núcleo en Python

### 3.1 Paquete y dependencias

**Qué es.** `pyproject.toml` describe el paquete `turnos`: dependencias, las tres
órdenes y los ficheros que no son Python pero deben ir dentro (festivos,
municipios, plantilla de migraciones, CSS e iconos de la interfaz nativa).

```toml
[project.scripts]
turnos = "turnos.arranque.web:main"
turnos-escritorio = "turnos.arranque.escritorio:main"
turnos-gnome = "turnos.arranque.gnome:main"

[tool.setuptools.package-data]
turnos = ["recursos/festivos/*.json", "recursos/municipios.json", "datos/migraciones/script.py.mako",
          "arranque/gnome/estilos.css", "arranque/gnome/iconos/*.svg"]
```

| Dependencia | Versión en uso | Para qué |
|---|---|---|
| ortools | 9.15 | Resolver el problema de asignación (CP-SAT) |
| sqlalchemy | 2.1 | Acceso a la base de datos |
| alembic | 1.20 | Migraciones del esquema |
| fastapi (+ pydantic 2.14, starlette) | 0.143 | API HTTP con validación |
| uvicorn | 0.54 | Servidor HTTP |
| openpyxl | 3.1.5 | Hojas de cálculo |
| pytest, httpx, pyflakes (dev) | | Pruebas y comprobación |

PyGObject **no** está en las dependencias de pip: lo aporta el runtime de GNOME
en Flatpak o el paquete del sistema en desarrollo.

**Por qué.** Un paquete estándar con `src/` evita importar por accidente el
código sin instalar y permite generar una rueda (`.whl`) para el Flatpak.

**Cómo se mantiene.**

- **Añadir un fichero de datos** (un JSON, un icono): añádelo a `package-data`,
  o no estará en la rueda ni en el Flatpak (pasó con `municipios.json`).
- **Subir una dependencia**: cambia la versión mínima si hace falta, instálala en
  el `.venv`, ejecuta todas las pruebas y regenera las dependencias del Flatpak
  (sección 8).
- **Versión**: `version` en `pyproject.toml`; la aplicación la lee con
  `importlib.metadata` (`turnos.__version__`).

### 3.2 Dominio

**Qué es.** `src/turnos/dominio/`: los conceptos del problema y los cálculos que
no dependen de nada más (ni de la base de datos ni del motor).

| Fichero | Contenido |
|---|---|
| `modelos.py` | `Turno` (MANANA, TARDE) y sus `Mitad` (M1, M2, T1, T2); `Elegibilidad` (FIJO, HABITUAL, DISPONIBLE, NO_DISPONIBLE); `TipoJornada` (jornadas de turno y medio o dobles); `Rol` (URGENCIAS, DOMICILIOS); `Preferencia`; `OrigenAsignacion` (GENERADOR, FIJO, MANUAL); `Asignacion`, `RangoCarga`, `Ausencia` |
| `calendario.py` | `Festivo` y `AmbitoFestivo` |
| `carga.py` | Ajuste de la carga por ausencias |

**Cómo se usa.** Son clases inmutables (`@dataclass(frozen=True)`) y
enumerados. Ejemplo, el ajuste por ausencias:

```python
# rango ajustado = rango × (días laborables disponibles / días laborables del mes)
# Una ausencia de un solo turno cuenta como medio día; se redondea al medio turno.
ajustar_rango(RangoCarga(30, 40), dias_del_mes, ausencias_del_medico)
```

La unidad de carga es siempre el **medio turno**: `turnos_a_medios(18.5) == 37`
y `formatear_medios(37) == "18,5"`.

**Por qué.** Tener los conceptos aislados hace que todo lo demás hable el mismo
idioma y que las reglas puras se prueben sin preparar nada
(`tests/dominio`).

**Cómo se mantiene.** Un concepto nuevo del negocio (un tercer turno, otro
papel) empieza aquí. Al añadir un valor a un enumerado:

1. Añádelo en `modelos.py`.
2. Si se guarda en la base: las columnas de enumerados son texto, no hace falta
   migración, pero revisa los datos existentes.
3. Busca dónde se recorren sus valores (`for t in Turno`, diccionarios de textos
   en las interfaces) y complétalos.
4. Regenera los tipos de la interfaz web (sección 3.7).

### 3.3 Motor (OR-Tools)

**Qué es.** `src/turnos/motor/`: recibe un `Problema` y devuelve un `Resultado`
con las asignaciones, los papeles de la tarde y los avisos. Es la pieza más
delicada; conviene leer antes la sección 8 de [arquitectura.md](arquitectura.md).

#### Conceptos de CP-SAT que hay que conocer

CP-SAT (Google OR-Tools) resuelve problemas con **variables enteras o
booleanas**, **restricciones lineales** y un **objetivo** a minimizar.

```python
from ortools.sat.python import cp_model

m = cp_model.CpModel()
x = m.new_bool_var("ana_lunes_tarde")            # 0 o 1
falta = m.new_int_var(0, 3, "falta_lunes_T1")    # entero entre 0 y 3
m.add(x + otros + falta >= 2)                     # cobertura mínima 2, con holgura «falta»
m.add_at_most_one([x, y])                         # como mucho uno de los dos
m.minimize(falta)                                 # objetivo
solver = cp_model.CpSolver()
estado = solver.solve(m)                          # OPTIMAL, FEASIBLE, INFEASIBLE…
solver.boolean_value(x), solver.value(falta)
```

#### Piezas del motor

| Fichero | Qué hace |
|---|---|
| `entrada.py` | `Problema` (todo lo del mes: días, cobertura, reglas de cada médico ya ajustadas, lo bloqueado y vetado, el calendario anterior, rotaciones, ajustes) y `preparar()`, que separa lo ya decidido (`fijadas`: fijos, bloqueados, rotaciones) de los **candidatos** que decide el motor |
| `diagnostico.py` | Antes de resolver: causas de imposibilidad (no hay médicos suficientes un día, una carga inalcanzable…) |
| `modelo_cpsat.py` | `generar()`: crea el modelo (`_Modelo`), sus restricciones y las **pasadas** de optimización |
| `validacion.py` | Después: comprueba el calendario contra todas las reglas y produce los incumplimientos |
| `resultado.py` | `Aviso`, `Resultado` y los textos de los avisos («El martes 3/11 por la mañana falta 1 médico.») |
| `ejemplo.py` | Un mes de ejemplo para probar el motor desde la terminal |

#### Las pasadas

`_Modelo._objetivos()` devuelve la lista ordenada; `resolver()` las recorre:

```python
for nombre, objetivo in self._objetivos():
    self.m.minimize(objetivo)
    estado = solver.solve(self.m)
    # Fija el valor alcanzado y usa la solución como punto de partida.
    self.m.add(objetivo <= round(solver.objective_value))
    for var in [...]:
        self.m.add_hint(var, solver.boolean_value(var))
```

Cada pasada tiene un límite de tiempo determinista (`Parametros.tiempo_por_pasada`,
5 «segundos» de CP-SAT). El resolvedor usa un hilo y una semilla fija: los mismos
datos dan siempre el mismo calendario, lo que facilita las pruebas.

**Por qué CP-SAT y por qué pasadas.** CP-SAT es de los mejores resolvedores
gratuitos para problemas de horarios y tiene una interfaz Python cómoda. Las
pasadas (optimización lexicográfica) evitan el problema clásico de una suma
ponderada: con pesos, una pequeña mejora en un objetivo poco importante puede
«comprar» un empeoramiento en uno importante. Con pasadas, la cobertura mínima
siempre va primero y la estabilidad siempre al final.

#### Cómo se mantiene y modifica

- **Añadir una regla nueva** (ver la receta 9.3): decide si es dura o blanda. Si
  es blanda, crea una variable de holgura, añádela como pasada en el lugar de
  prioridad que le corresponda, compruébala en `validacion.py` para que genere
  avisos, y si puede ser imposible, añade su causa en `diagnostico.py`.
- **Rendimiento.** Lección aprendida (fases 18 y 20 de la documentación técnica):
  prefiere objetivos cuyo óptimo **suele ser 0**, como desviaciones respecto a
  una **banda** de valores aceptables. Un objetivo con óptimo positivo que la
  relajación lineal no acota (por ejemplo, la distancia a una parte fraccionaria)
  hace que CP-SAT encuentre la solución enseguida pero no pueda demostrar que es
  la mejor, y agote el tiempo de cada pasada. Hay una prueba de rendimiento con
  un mes real (30 médicos) que debe tardar menos de 10 s:
  `tests/motor/test_modelo.py::test_tamano_real_en_menos_de_10_segundos`.
- **Probar**: `tests/motor/` construye problemas pequeños a mano, sin base de
  datos (`problema(medicos, semanas=2, …)`), y comprueba el resultado. Es el
  sitio para reproducir un caso raro.
- **Depurar una pasada lenta**: mide cada pasada (como en la fase 18):
  envuelve `CpSolver.solve` para imprimir tiempo, estado y valor; una pasada que
  acaba en `FEASIBLE` en lugar de `OPTIMAL` es la sospechosa.

### 3.4 Datos (SQLAlchemy y Alembic)

**Qué es.** `src/turnos/datos/`: el esquema (`tablas.py`), la creación y
actualización de la base (`bd.py`) y las migraciones (`migraciones/`).

#### SQLAlchemy 2

Las tablas se declaran como clases con anotaciones de tipo:

```python
class Medico(Base):
    __tablename__ = "medico"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    codigo: Mapped[str] = mapped_column(unique=True)
    activo: Mapped[bool] = mapped_column(default=True)
    color: Mapped[str | None] = mapped_column(String(7))  # "#rrggbb" para el calendario

    elegibilidad: Mapped[list["ReglaElegibilidad"]] = relationship(cascade="all, delete-orphan")
    ausencias: Mapped[list["AusenciaMedico"]] = relationship(cascade="all, delete-orphan")
    # … también jornadas, cargas y preferencias
```

Se consulta con `select()` dentro de una sesión:

```python
with Session(motor) as sesion, sesion.begin():           # una transacción
    medicos = sesion.scalars(select(Medico).where(Medico.activo)).all()
    sesion.add(Medico(nombre="Dra. Ruiz", codigo="RUI"))
```

En la API, cada petición recibe su propia sesión y transacción
(`api/dependencias.py`): si la ruta termina bien se confirma; si lanza una
excepción, se deshace todo.

Cada conexión activa dos ajustes de SQLite (`bd.crear_motor`):
`PRAGMA foreign_keys = ON` (SQLite no comprueba las claves ajenas si no se le
pide) y `PRAGMA busy_timeout = 5000` (si otra instancia está escribiendo, espera
en lugar de fallar).

#### Alembic

Cada cambio de esquema es una **migración** numerada en
`datos/migraciones/versions/`: `0001_esquema_inicial` … `0005_turnos_rotativos`.
Una migración tiene `upgrade()` y `downgrade()`:

```python
revision = '0004'
down_revision = '0003'

def upgrade() -> None:
    op.create_table('ajuste',
        sa.Column('clave', sa.String(), nullable=False),
        sa.Column('valor', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('clave'))

def downgrade() -> None:
    op.drop_table('ajuste')
```

`bd.inicializar(ruta)`, que se llama en cada arranque:

1. crea la carpeta y el motor;
2. `migrar()`: si hay migraciones pendientes, **copia el fichero** a
   `turnos-AAAAMMDD-HHMMSS.sqlite.bak` y las aplica; si la base es de una
   versión **más nueva** (revisión desconocida), lanza `DatosMasNuevos` sin
   tocar nada;
3. carga los horarios por defecto si no hay y vuelca los festivos precargados
   de los años aún no cargados.

**Por qué.** SQLite es un fichero: nada que instalar ni administrar, copiar el
fichero es hacer una copia de seguridad, y aun así hay transacciones y claves
ajenas. Alembic permite que una versión nueva actualice los datos de quien ya
usaba la anterior sin perder nada.

#### Cómo se mantiene y modifica

- **Cambiar el esquema** (receta 9.2): cambia `tablas.py`, genera la migración
  con autogeneración (el procedimiento está en la sección 7 de la documentación
  técnica), **revisa** el fichero generado (la autogeneración no detecta todo,
  por ejemplo los cambios de tipo o de nombre) y añade una prueba en
  `tests/datos/test_bd.py` que migre una base de la versión anterior con datos.
- SQLite no admite `ALTER TABLE` completo: las migraciones usan
  `render_as_batch` (Alembic recrea la tabla por debajo).
- **Nunca edites una migración ya publicada**: los usuarios ya la tienen
  aplicada. Haz una nueva.
- **Restaurar una copia**: con la aplicación cerrada, sustituye el fichero por
  la copia, o usa *Configuración → Importar una copia*.

### 3.5 Servicios

**Qué es.** `src/turnos/servicios/`: los **casos de uso**. Son el puente entre la
base de datos y el motor, y es donde vive la lógica de negocio que no es
optimización.

| Módulo | Funciones principales |
|---|---|
| `periodos.py` | `construir(sesion, año, mes) -> DatosMes`: reúne todo lo del mes y crea el `Problema`. `generar_mes()`: llama al motor y guarda el resultado. `aplicar_cambios()`: cambios manuales (fija un día, bloquea, asigna un papel). `liberar()`: vuelve a automático un turno, un día o el mes. `restaurar()`: deshacer. `fijar_carga_manual()`: rango solo para ese mes. `publicar()`. `leer_calendario()`: lo que devuelve la API, con los avisos recalculados |
| `reglas.py` | `leer_reglas(sesion, médico, fecha)` y `guardar_reglas(...)`: reglas **versionadas** por `vigente_desde` |
| `ajustes.py` | `Ajustes` (dataclass) y su lectura y guardado en la tabla `ajuste` |
| `rotaciones.py` | Turnos rotativos y su conversión a lo que entiende el motor |
| `festivos_oficiales.py` | Búsqueda de festivos en festivos.io y en los datos abiertos de Madrid |
| `importar.py` | Validar, migrar y sustituir los datos por una copia |

Detalles que conviene conocer:

- **Equidad entre meses.** `_saldo()` suma, para cada médico, cuántos turnos de
  más o de menos tuvo respecto a su objetivo en los meses **publicados**. El
  motor compensa parte de ese saldo (`objetivos_equidad`), hasta
  `limite_saldo` medios turnos.
- **Cambios manuales.** Poner a alguien en un turno crea asignaciones con origen
  `MANUAL` y `bloqueada=True`; quitarlo crea un **veto** para ese día y turno.
  Al regenerar, el motor respeta ambos.
- **Ajustes generales** se guardan como clave → valor JSON. Un ajuste que no está
  en la tabla toma el valor por defecto de la dataclass, así que añadir uno no
  necesita migración:

```python
@dataclass
class Ajustes:
    todos_trabajan: bool = True
    roles_segun_presencia: bool = True
    mostrar_cobertura: bool = False
    municipio: str = MUNICIPIO_POR_DEFECTO  # "28079", Madrid
```

**Por qué.** Separar los casos de uso de la API permite usarlos desde otros
sitios (pruebas, `python -m turnos.datos`) y mantener las rutas finas.

**Cómo se mantiene.** Una funcionalidad nueva que toca datos y motor casi
siempre se implementa aquí: añade la función, llámala desde una ruta y pruébala
en `tests/api/` (las pruebas de la API recorren servicio y base de datos de
verdad, con una base temporal).

### 3.6 Recursos

**Qué es.** `src/turnos/recursos/`: datos que viajan con la aplicación.

- `festivos/madrid-AAAA.json`: festivos precargados (nacionales,
  autonómicos y locales de Madrid, el municipio por defecto) con su fuente.
  `CALENDARIO_PRECARGADO` y `MUNICIPIO_POR_DEFECTO` (en `recursos/__init__.py`)
  dicen cuáles son: para otro municipio por defecto, cambia los dos y crea sus
  ficheros. `completo: false` si faltan los locales.
- `municipios.json`: los 8.132 municipios del INE (código, nombre, provincia,
  comunidad) para el buscador del municipio del centro.

**Cómo se mantiene.**

- **Festivos de un año nuevo**: lo normal es que el planificador los busque en
  *Configuración → Festivos oficiales*. Para precargarlos en una versión nueva,
  crea el JSON con el formato de los existentes y comprueba las fechas en el
  boletín oficial; `tests/recursos/test_festivos.py` valida su coherencia.
- **Municipios**: cambian poco (altas o fusiones). Se regeneran desde la
  relación oficial del INE (o la de festivos.io, que la reproduce) con el mismo
  formato compacto.

### 3.7 API (FastAPI y Pydantic)

**Qué es.** `src/turnos/api/`: `app.py` crea la aplicación (rutas, token,
errores y, en el modo web, la interfaz compilada); `esquemas.py` define la forma
de los datos de entrada y salida; `rutas/` tiene un fichero por recurso.

**Cómo se usa.** Una ruta es una función con anotaciones de tipo; FastAPI valida
la entrada con el esquema Pydantic y convierte la salida con `response_model`:

```python
router = APIRouter(prefix="/api/medicos", tags=["médicos"])

@router.put("/{medico_id}", response_model=e.Medico)
def modificar(medico_id: int, datos: e.MedicoEntrada, sesion: SesionBD):
    medico = obtener_o_404(sesion, Medico, medico_id, "Médico")
    for campo, valor in datos.model_dump().items():
        setattr(medico, campo, valor)
    sesion.flush()
    return medico
```

```python
class MedicoEntrada(_Base):
    nombre: str = Field(min_length=1, max_length=80)
    codigo: str = Field(min_length=1, max_length=6)
    activo: bool = True
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
```

- `SesionBD` (en `dependencias.py`) inyecta la sesión de la petición.
- Errores: se lanza `HTTPException(código, "mensaje para el usuario")`; las
  interfaces muestran ese mensaje tal cual. Las violaciones de integridad de la
  base se convierten en un 409.
- **Token** (`app.py`, `_proteger_con_token`): un middleware que, si la petición
  trae `?token=…` correcto, guarda la cookie `turnos_sesion_<puerto>` y redirige,
  y que responde 401 a cualquier `/api` sin cookie ni cabecera `X-Turnos-Token`.
  `TURNOS_SIN_TOKEN=1` lo desactiva (solo para desarrollo y pruebas).
- Documentación interactiva: `http://127.0.0.1:8000/docs` con
  `TURNOS_SIN_TOKEN=1`.

**Por qué.** FastAPI da validación, documentación y esquema OpenAPI a partir de
los propios tipos de Python, con muy poco código. El esquema OpenAPI permite
**generar los tipos TypeScript** de la interfaz web: si cambia la API, el
compilador de TypeScript señala qué hay que adaptar.

**Cómo se mantiene.**

- **Añadir una ruta** (receta 9.4): función en `rutas/`, esquema en
  `esquemas.py`, prueba en `tests/api/`.
- **Tras cambiar cualquier esquema o ruta**, regenera el contrato:

```sh
.venv/bin/python -m turnos.api.openapi interfaz/openapi.json
(cd interfaz && npm run tipos && npm run comprobar)
```

### 3.7.1 Varios clientes a la vez

**Qué es.** Lo necesario para que varias ventanas (o, en el modo servidor, varias
personas) trabajen a la vez sin pisarse (docs/diseno-servidor.md, 8 y 9):

- **Cerrojo de escritura** (`dependencias.py`, `_sesion`): las peticiones que no
  son GET/HEAD/OPTIONS toman `app.state.cerrojo_escritura` durante toda la
  transacción. Dentro de ella se añade la fila de `registro_cambio`
  (`eventos.registrar`); tras confirmarla, se publica el evento.
- **Versión del mes** (`periodo.version`; `rutas/periodos.py`, `_ejecutar`):
  cada cambio del mes la sube; si el cliente envía `X-Version-Mes` y no coincide,
  409 con la versión actual en la misma cabecera.
- **Bloqueo al generar** (`servicios/periodos.py`, `GENERANDO`): un segundo
  «Generar» del mismo mes recibe 409 sin esperar al cerrojo.
- **Eventos** (`api/eventos.py`): `Difusor` reparte cada evento a las colas de
  los clientes conectados a `GET /api/eventos`; `clasificar` decide, por la ruta,
  el tipo de evento y el texto del registro. **Una ruta nueva que escriba** debe
  aparecer en `clasificar` (si no, se registra con un texto genérico y no avisa
  a nadie).
- **Clientes**: la web (`interfaz/src/api/eventos.ts`) invalida las consultas
  de TanStack Query según el tipo; la nativa (`gnome/cliente.py`, `escuchar`)
  avisa a la ventana (`ventana.py`, `_evento`). Las dos encolan los cambios del
  mes y vacían el historial de deshacer si el mes lo cambió otro.
- **WAL** solo en el modo servidor (`crear_motor(ruta, wal=True)`).

**Cómo se prueba.** `tests/api/test_varios_clientes.py` (con un servidor real
para la concurrencia y los eventos), `interfaz/e2e/varios-clientes.spec.ts`
(dos navegadores) y `tests/escritorio/gnome_varios.py` (la ventana nativa con
otro cliente cambiando el mes).

### 3.8 Exportación (openpyxl)

**Qué es.** `src/turnos/exportar/xlsx.py`: dos libros. `exportar_xlsx` (hojas
*Calendario*, *Por médico* y *Resumen*, A4 horizontal) y `exportar_roles_xlsx`
(urgencias y domicilios, A4 vertical). Las rutas `/exportar.xlsx` y
`/urgencias-domicilios.xlsx` los devuelven como descarga.

**Cómo se mantiene.** Cada hoja es una función `_hoja_…` que escribe celdas,
estilos y la configuración de impresión (`_preparar_impresion`). Las pruebas
(`tests/api/test_exportar.py`) abren el fichero con openpyxl y comprueban
celdas concretas: añade una comprobación al cambiar una hoja.

---

## 4. Interfaz web

**Qué es.** `interfaz/`: una aplicación React de una sola página, compilada a
`interfaz/dist`, que sirve el propio servidor en el modo web y que carga el
WebView en el modo escritorio.

| Tecnología | Versión | Para qué | Por qué |
|---|---|---|---|
| React | 19.3 | Componentes de la interfaz | Estándar, mucho conocimiento disponible |
| TypeScript | 5.8 | Tipos | Los errores aparecen al compilar; los tipos de la API se generan |
| Vite | 6.4 | Compilación y servidor de desarrollo | Rápido y sin configuración compleja |
| TanStack Query | 5.103 | Datos del servidor (caché, recarga, estados de carga) | Evita escribir un almacén de estado propio |
| React Router | 7.18 | Pestañas como rutas (`/medicos`, `/cobertura`…) | Direcciones enlazables y botón atrás |
| dnd-kit | 6.3 | Arrastrar y soltar | Accesible (también con teclado) y ligero |
| IBM Plex (@fontsource) | 5.3 | Tipografía | Legible para tablas y cifras; incluida, sin depender de internet |
| Vitest + Testing Library | 4.1 | Pruebas de componentes y lógica | Se integra con Vite |
| Playwright | 1.63 | Flujo completo en un navegador real | Fiable y con buen diagnóstico |

### 4.1 Estructura

```
src/
  main.tsx, App.tsx          arranque y rutas
  api/cliente.ts             api(metodo, ruta, cuerpo): fetch con manejo de errores
  api/consultas.ts           un hook por dato o acción: useCalendario, useGuardarReglas…
  api/esquema.d.ts           tipos generados del OpenAPI (no se edita a mano)
  api/tipos.ts               alias legibles de esos tipos
  calendario/logica.ts       funciones puras: cambiosAlSoltar, mitadesConValor, estadoCelda…
  calendario/useHistorial.ts deshacer / rehacer
  componentes/               Disposicion (cabecera y pestañas), Cajon (panel lateral),
                             CuadriculaElegibilidad, CampoTurnos, Mensajes, Iconos
  medicos/                   TarjetaMedico, CajonReglas («Más reglas»), formulario.ts
  rotaciones/                TarjetaRotacion, semanas.ts
  paginas/                   Calendario, Medicos, Rotaciones, Cobertura, Festivos,
                             Configuracion (+ ConfiguracionDatos, ConfiguracionFestivos),
                             Imprimir, ImprimirRoles
  util/                      fechas, textos, colores, mes (mes compartido en la URL),
                             useAutoguardado
  estilos/global.css         variables de color, tema oscuro, impresión
```

### 4.2 Conceptos clave

**Datos del servidor con TanStack Query.** Cada dato es una consulta con una
clave; las modificaciones invalidan las claves afectadas y la interfaz se
actualiza sola:

```ts
export const useAjustes = () =>
  useQuery({ queryKey: ["ajustes"], queryFn: () => api<T.Ajustes>("GET", "/ajustes") });

export const useGuardarAjustes = () =>
  useModificacion((a: T.Ajustes) => api<T.Ajustes>("PUT", "/ajustes", a), [["ajustes"]]);
```

`useModificacion` invalida además `["calendario"]` y `["estado"]`, porque casi
cualquier cambio afecta al calendario.

**Guardado automático seguro** (`util/useAutoguardado.ts`). Las tarjetas de
médicos, la cobertura y los turnos rotativos se guardan solos:

- `programar(datos)` espera 450 ms sin cambios y guarda;
- si el componente se desmonta (cambio de pestaña) o la página se cierra
  (`pagehide`), lo pendiente se envía en ese momento, con `fetch keepalive` para
  que llegue aunque la página se esté cerrando;
- las lecturas esperan a los guardados en curso (`esperarGuardado`), para no
  mostrar datos de antes de guardar.

Esta pieza nació de un fallo real: se perdían reglas al cambiar de pestaña
(fase 10 de la documentación técnica). Cualquier formulario nuevo que se guarde
solo debe usarla.

**Lógica pura separada.** Lo que decide qué cambios produce soltar a un médico,
qué mitades quedan al poner «½» o el estado de un turno está en
`calendario/logica.ts`, sin React, y se prueba con Vitest. La interfaz nativa
reproduce las mismas reglas (sección 6).

**Estilos.** `estilos/global.css` define variables (`--acento`, `--manana`,
`--tarde`, `--critico`…) y su versión oscura; cada componente tiene su
`.module.css` con clases locales. La impresión usa `@media print` y `@page`.

### 4.3 Cómo se mantiene y modifica

- **Política de dependencias npm**: versiones **exactas**, con al menos dos
  semanas desde su publicación, `npm audit` sin avisos. `interfaz/.npmrc` activa
  `legacy-peer-deps` por un fallo de npm 10 con dependencias opcionales.

```sh
npm view <paquete> time            # comprobar la fecha de publicación
npm install --save-exact <paquete>@<versión>
npm audit && npm test && npm run comprobar && ../scripts/e2e.sh
```

- **Añadir un campo que viene de la API**: cambia el esquema en Python,
  regenera los tipos (sección 3.7) y TypeScript señalará dónde usarlo.
- **Añadir una página** (receta 9.5).
- **Pruebas**: `npm test` (Vitest) y `scripts/e2e.sh` (Playwright). Las pruebas
  de flujo completo usan textos y roles accesibles (`getByRole`, `getByLabel`):
  si cambias un texto visible, actualiza la prueba.

---

## 5. Arranque y modo escritorio

### 5.1 Arranque común (`arranque/servidor.py`)

```python
servidor = preparar(puerto=0, con_token=True)   # datos, puerto libre en 127.0.0.1, token
servidor.ejecutar()                             # modo web: bloquea hasta Ctrl+C
servidor.iniciar_en_hilo()                      # escritorio / nativa: vuelve cuando acepta conexiones
servidor.esperar_peticiones(); servidor.detener()
```

`preparar` reserva el puerto **antes** de arrancar, así la dirección se conoce
desde el principio y un puerto ocupado falla pronto con un mensaje claro.

Variables de entorno: `TURNOS_DATOS` (fichero de datos), `TURNOS_PUERTO` (modo
web, 8000; 0 = libre), `TURNOS_SIN_NAVEGADOR`, `TURNOS_SIN_TOKEN`,
`TURNOS_INTERFAZ` (carpeta de la interfaz compilada; la fija el Flatpak),
`TURNOS_DEPURAR` (herramientas de WebKit), `TURNOS_FUENTE_FESTIVOS_IO` y
`TURNOS_FUENTE_MADRID` (fuentes de festivos; las pruebas las apuntan a ficheros
locales).

### 5.1.1 Modo servidor (`red/`, `api/acceso.py`)

**Qué es.** `turnos servidor` (docs/guia-servidor.md): el núcleo escuchando en la
red local con HTTPS, cuentas y roles. `turnos.arranque.web.main` pasa la orden a
`red/orden.py`.

| Pieza | Qué hace |
|---|---|
| `red/configuracion.py` | Lee `servidor.toml` (`/etc/turnos` o `~/.config/turnosMedicos`) en `ConfigServidor` |
| `red/certificados.py` | Autoridad propia (10 años, restricciones de nombre: `.local`, `localhost`, redes privadas) y certificado del servidor (1 año, se renueva solo) con `cryptography`; perfil `.mobileconfig` |
| `red/anuncio.py` | mDNS con `zeroconf`: `_https._tcp` y `_turnosmedicos._tcp`, y el nombre `turnos.local` |
| `red/copias.py` | Copia diaria (conserva N días) y a mano; el hilo `Tareas` la hace cada hora si falta y renueva el certificado |
| `red/orden.py` | La orden: arranca uvicorn con TLS, WAL, las tareas y el anuncio; `handle_exit` cierra los eventos para parar enseguida |
| `servicios/usuarios.py` | scrypt, cuentas, sesiones (se guarda el SHA-256 del token), límite de intentos |
| `api/acceso.py` | Middleware de sesión, CSRF y permisos (tabla `_permitido`); rutas `/api/sesion`, `/api/yo`, `/api/usuarios`, `/api/sesiones` |
| `api/rutas/servidor.py` | `/api/servidor` (direcciones, QR, copias) y `/certificado/*` (sin sesión) |
| `interfaz/src/api/sesion.ts`, `paginas/Acceso.tsx`, `paginas/Administracion.tsx` | Entrada, contraseña, certificado y administración en la web |

**Cómo se mantiene.**

- **Una ruta nueva** queda abierta a planificador y administrador y cerrada a los
  médicos. Si un médico debe poder **leerla**, añádela a `_LECTURAS_MEDICO` (o a
  una regla propia, como `_FICHA`) y prueba en `tests/api/test_acceso.py` que no
  ve lo de otros.
- **Solo administrador**: añádela a `_ADMINISTRACION`.
- `api/openapi.py` genera el esquema **en el modo servidor**, para que la
  interfaz tenga también los tipos de cuentas y servidor.
- En el modo personal no se instala nada de esto: `/api/yo` responde un
  administrador sin cuenta y la web no muestra la entrada.

### 5.1.2 Las aplicaciones como clientes de un servidor

| Pieza | Qué hace |
|---|---|
| `arranque/conexion.py` | `Conexion` (personal o servidor), `leer`/`guardar` en `~/.config/turnosMedicos/conexion.json`, `descargar_autoridad` (sin verificar, para confirmar la huella), `contexto_ssl` (solo esa autoridad), `entrar`, `buscar_servidores` y `resolver` (mDNS con zeroconf) |
| `arranque/dialogos.py` | `SelectorInicio` (la pantalla «¿Dónde quieres trabajar?» al abrir, si `conexion.preguntar`), `DialogoConexion` (cambiarlo después; «Preguntar al abrir»), `confirmar_servidor` (la huella, como SSH), `DialogoEntrar` y `reiniciar` (la aplicación se cierra y `volver_a_abrir_si_hace_falta` la vuelve a lanzar con `os.execv`) |
| `arranque/llavero.py` | La sesión de la nativa en el llavero de GNOME (libsecret); sin llavero, no se guarda |
| `gnome/aplicacion.py` | Sin servidor interno si `conexion.en_servidor`: sesión del llavero o `DialogoEntrar`; médicos y contraseñas temporales, a la web |
| `escritorio/ventana.py` | `cargar_servidor`: resuelve, descarga el certificado del servidor, lo acepta si lo firma la autoridad confirmada y carga; sesión de WebKit persistente |

**Cómo se prueba**: `tests/red/test_cliente.py` (contra un servidor real),
`tests/escritorio/gnome_cliente.py` y `humo_cliente.py`. El fixture
`servidor_red` (`tests/conftest.py`) arranca un `turnos servidor` con HTTPS, un
administrador, un planificador, una médica con cuenta y un equipo de 4.

### 5.1.3 Solicitudes de los médicos

| Pieza | Qué hace |
|---|---|
| `servicios/solicitudes.py` | Los tres tipos (DISPONIBILIDAD, AUSENCIA, CALENDARIO), su validación, `describir`, `efectos` (punto de guardado y deshacer), `aprobar`, `rechazar`, `retirar`, `responder_companero` |
| `api/rutas/solicitudes.py` | `/api/solicitudes` (lista, crear) y `/{id}/retirar`, `/aceptar`, `/efectos`, `/aprobar`, `/rechazar`. Comprueba de quién es cada una; los roles, `api/acceso.py` |
| `interfaz/src/medico/` | `ProponerCambio` (desde un turno), `ProponerFicha` (disponibilidad y ausencias) y `MisSolicitudes` |
| `interfaz/src/paginas/Solicitudes.tsx` | La bandeja del planificador, con efectos y contador en la pestaña |
| `gnome/solicitudes.py` | La bandeja en la aplicación nativa (solo conectada a un servidor) |

**Añadir un tipo de solicitud**: su `Propuesta…` en `esquemas.py` (con `tipo`
como discriminador), su validación en `crear`, su texto en `describir`, cómo se
aplica en `_aplicar` y qué meses toca en `meses_afectados`; después, el
formulario en la web y una prueba en `tests/api/test_solicitudes.py`.

### 5.1.4 Raspberry Pi

`empaquetado/raspberry/` (instalador, servicio, configuración) y
`scripts/desplegar-raspberry.sh`; guía en docs/instalacion-raspberry.md. Al
cambiar las dependencias o el arranque, prueba la instalación completa en un
Debian arm64 emulado: `scripts/probar-raspberry-contenedor.sh` (necesita podman y
qemu-user-static; tarda unos minutos).

### 5.1.5 Windows

`arranque/windows/` (lanzador Tkinter, instancia única con `abierto.json`, y la
autoprueba `--prueba`), `empaquetado/windows/` (`turnos-medicos.spec` de
PyInstaller, `Containerfile` con Wine de WineHQ y el Python oficial, `turnos.ico`)
y `scripts/construir-windows.sh`; en GitHub, `.github/workflows/windows.yml`.
`config.py` da las rutas de Windows (`%LOCALAPPDATA%`, `%APPDATA%`). Si se añade
un módulo con datos o una dependencia con bibliotecas nativas, revisa el spec y
comprueba que la autoprueba sigue diciendo `BIEN`. Guía: docs/windows.md.

### 5.2 Modo escritorio (`arranque/escritorio/`)

**Qué es.** Una aplicación GNOME (`Adw.Application`, identificador
`io.oriol.TurnosMedicos`) cuya ventana contiene un `WebKit.WebView` con la
interfaz web.

| Fichero | Qué hace |
|---|---|
| `aplicacion.py` | Una sola instancia, arranque del servidor en un hilo, atajos (Ctrl+Q, Ctrl+R, Ctrl+P, zoom), «Acerca de» |
| `ventana.py` | Ventana con pantallas de carga y error, WebView, enlaces externos al navegador, menú contextual reducido, **cierre seguro** |
| `descargas.py` | Las descargas de la página abren el «Guardar como» de GNOME y avisan al terminar |
| `errores.py` | Textos de los errores de arranque |
| `estado.py` | Tamaño de la ventana entre sesiones (`~/.config/turnosMedicos/ventana.json`) |

**Detalles que han costado encontrar** (no los cambies sin entenderlos):

- **Cierre seguro.** `try_close()` de WebKit **no** descarga la página, así que
  los guardados pendientes se perdían. Al cerrar, la vista navega a
  `about:blank` (lo que dispara `pagehide` y los envíos `keepalive`), espera a
  que el servidor termine esas peticiones y entonces se detiene. Lo comprueba
  `tests/escritorio/test_humo.py`.
- **Sin proxy.** En Flatpak sin permiso de red, el portal de proxy de GNOME
  rechazaba la consulta de WebKit y la página no cargaba. La sesión del WebView
  usa `NetworkProxyMode.NO_PROXY` (solo habla con 127.0.0.1).
- **Sesión efímera**: sin caché ni cookies en disco; la cookie del token vale
  solo para ese arranque.

**Por qué.** Un WebView dentro de GTK da una aplicación de escritorio con la
interfaz completa sin reescribirla, y mucho más ligera que Electron porque usa
el WebKit que ya trae el runtime de GNOME.

---

## 6. Interfaz nativa GNOME

**Qué es.** `src/turnos/arranque/gnome/`: las mismas funciones que la interfaz
web, con widgets GTK 4 y libadwaita escritos en Python (PyGObject).
Identificador `io.oriol.TurnosMedicos.Nativa`, orden `turnos-gnome`.

### 6.1 Conceptos de GTK 4, libadwaita y PyGObject

```python
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib

fila = Adw.SwitchRow(title="Todos los médicos trabajan cada día laborable")
fila.connect("notify::active", lambda fila, _param: guardar(fila.get_active()))   # señales
grupo = Adw.PreferencesGroup(title="Reglas generales"); grupo.add(fila)
```

- **Señales**: `connect("clicked", función)`; las propiedades avisan con
  `notify::nombre`.
- **El hilo de la interfaz es sagrado**: nada lento (peticiones, ficheros
  grandes) en él. Desde otro hilo, se vuelve con `GLib.idle_add(función, …)`.
- **libadwaita** aporta los patrones de GNOME: `Adw.ViewStack` (pestañas),
  `Adw.PreferencesPage/Group` y sus filas, `Adw.Dialog`, `Adw.AlertDialog`,
  `Adw.Toast` (avisos breves), `Adw.ToggleGroup` (botones segmentados),
  `Adw.Breakpoint` (adaptarse al ancho), `Adw.WrapBox` (contenido que salta de
  línea).
- **CSS de GTK** (`estilos.css`): parecido al de la web, con colores del tema
  como `@accent_bg_color` o `@error_color`.

### 6.2 Piezas

| Fichero | Qué hace |
|---|---|
| `aplicacion.py` | `Adw.Application`, carga de estilos e iconos, servidor en un hilo |
| `ventana.py` | Cabecera (icono y nombre, pestañas, menú), `selector_mes()` (común a las pantallas), puntos de ruptura (estrecho < 760 sp, ancho ≥ 1.700 sp), clase `oscuro` según el tema, avisos |
| `cliente.py` | `ClienteApi.pedir()` y `en_segundo_plano(metodo, ruta, cuerpo, hecho=…, fallo=…)` |
| `comun.py` | Textos, conversiones (medios turnos, mitades), colores de los médicos (CSS generado), widgets: `SelectorFecha`, `Numero`, `Diferido` (guardado diferido) |
| `calendario.py` | Calendario: cuadrícula o lista, fichas, arrastrar y soltar, deshacer, problemas, tabla de carga, diálogo del turno |
| `imprimir.py` | Informes dibujados con Cairo y Pango en un `Gtk.PrintOperation` |
| `medicos.py` | Tarjetas de médicos en un `Gtk.FlowBox`, «Más reglas», ausencias, subpestaña de rotaciones |
| `rotaciones.py`, `cobertura.py`, `festivos.py`, `configuracion.py` | El resto de pantallas |

**Patrón de una pantalla**: tiene `pendiente` (si hay que recargarla) y
`cargar()`. La ventana llama a `cargar()` al mostrarla si está pendiente; tras
guardar algo, `ventana.invalidar(self)` marca las demás como pendientes.

```python
def cargar(self) -> None:
    self.ventana.cliente.en_segundo_plano("GET", "/festivos?anio=2026",
                                          hecho=self._mostrar, fallo=self.ventana.error)
```

**Por qué cliente de la API y no llamadas directas a los servicios**: así no se
duplican reglas ni validaciones, y todo lo que prueban las pruebas de la API vale
también para esta interfaz.

### 6.3 Cómo se mantiene y modifica

- **Mantenerla alineada con la web**: las reglas de interacción deben coincidir.
  La lógica de soltar está en `calendario.cambios_al_soltar` (igual que
  `cambiosAlSoltar` de la web), con una prueba que usa los mismos casos.
- **Revisar visualmente con capturas**: las pruebas no ven la maquetación. Se
  puede arrancar la ventana con Xvfb y guardar una captura con
  `Gtk.WidgetPaintable` + `render_texture` (como en las fases 23 a 26); usa
  `GSK_RENDERER=cairo` si las capturas salen en blanco, y comprueba los temas
  claro y oscuro (`ADW_DEBUG_COLOR_SCHEME=prefer-dark`) y la ventana estrecha.
- **Colores dependientes del tema**: libadwaita no pasa `prefers-color-scheme`
  al CSS propio; usa reglas `.oscuro .clase { … }`.
- **Anchos**: un `Gtk.FlowBox` reparte según el ancho **natural** de los hijos, y
  las pestañas de un `Adw.ViewStack` se miden juntas (una pantalla ancha impone
  su ancho mínimo a la ventana). Si algo se desborda en ventana estrecha, busca
  la fila más ancha y hazla saltar de línea.

---

## 7. Pruebas

> El detalle completo (cómo se desarrollaron, cómo ejecutar una sola prueba o
> depurar una que falla, cobertura y cómo ampliarlas) está en
> [pruebas.md](pruebas.md).

| Conjunto | Orden | Dónde |
|---|---|---|
| Python (175) | `.venv/bin/pytest` | `tests/` por capa: `dominio`, `motor`, `datos`, `recursos`, `api`, `arranque`, `escritorio` |
| Solo las ventanas | `.venv/bin/pytest -m escritorio` | `tests/escritorio/` |
| Interfaz web (27) | `cd interfaz && npm test` | `*.test.ts(x)` junto al código |
| Tipos | `cd interfaz && npm run comprobar` | |
| Flujo completo (19) | `scripts/e2e.sh` | `interfaz/e2e/` |
| Comprobación estática | `.venv/bin/python -m pyflakes src tests scripts/*.py` | |

**Cómo están hechas.**

- **API**: `tests/api/conftest.py` crea una base temporal y un `TestClient` de
  FastAPI; las pruebas hacen peticiones reales (`cliente.post("/api/medicos", …)`)
  y comprueban la respuesta y el estado.
- **Motor**: problemas construidos a mano, sin base de datos.
- **Fuentes externas** (festivos): se sustituye `descargar_json` con
  `monkeypatch`; en las pruebas de flujo completo, las direcciones apuntan a
  ficheros de `interfaz/e2e/datos` (`file://`).
- **Flujo completo**: `scripts/e2e.sh` compila la interfaz, arranca la aplicación
  con una base temporal vacía y sin token, y ejecuta Playwright con el Chromium
  del sistema. Las pruebas se ejecutan en orden y comparten base: deja los datos
  como estaban al terminar una prueba.
- **Ventanas GTK**: un programa auxiliar (`humo.py`, `gnome_humo.py`,
  `gnome_completa.py`) abre la aplicación con Xvfb, en una sesión de D-Bus propia
  y sin servicios (para no interferir con la aplicación abierta en el escritorio
  ni esperar a portales), recorre las acciones **esperando a condiciones** (no a
  tiempos fijos) y escribe un JSON que la prueba comprueba contra la API.

**Al añadir una funcionalidad**, añade al menos una prueba en la capa donde vive
la lógica (motor, servicio o API) y, si cambia la interacción, una de flujo
completo o de la interfaz nativa.

---

## 8. Empaquetado Flatpak

**Qué es.** `empaquetado/flatpak/` y `scripts/empaquetar-flatpak.sh` crean
`build/turnos-medicos-<versión>.flatpak`, que se instala para todos los usuarios
con `sudo flatpak install --system …`.

| Fichero | Qué es |
|---|---|
| `io.oriol.TurnosMedicos.yml` | Manifiesto: runtime `org.gnome.Platform//51`, permisos (pantalla, `~/.local/share/turnosMedicos`, red), módulos (dependencias de Python y la aplicación) |
| `python3-dependencias.json` | Módulo con las ruedas de Python (URL y sha256), **generado** |
| `io.oriol.TurnosMedicos.desktop`, `…Nativa.desktop` | Entradas del menú |
| `io.oriol.TurnosMedicos.metainfo.xml` | Metadatos AppStream (GNOME Software): descripción y notas de cada versión |
| `iconos/` | Icono normal y simbólico |

El guion: compila la interfaz, construye la rueda de la aplicación en
`build/flatpak/fuentes`, ejecuta `flatpak-builder` (con `--disable-rofiles-fuse`)
y crea el paquete. Con `--instalar` lo instala además para el usuario actual.

**Por qué Flatpak.** Instala en el menú de todos los usuarios, aísla la
aplicación (solo ve su carpeta de datos) y no depende de las versiones de Python
o GTK del sistema.

**Cómo se mantiene.**

- **Nueva versión** (receta 9.6).
- **Si cambian las dependencias de Python**: regenera el módulo (necesita red):

```sh
.venv/bin/python scripts/generar-dependencias-flatpak.py
```

  Toma las versiones exactas del `.venv`, elige ruedas cp314/manylinux y anota
  su sha256. Instala con `--ignore-installed` para no tocar los paquetes del SDK.
- **Validar los metadatos**: `desktop-file-validate` sobre los `.desktop` y
  `appstreamcli validate --no-net` sobre el AppStream.
- **Cambiar de runtime** (GNOME 52…): cambia `runtime-version` y la versión de
  Python en `generar-dependencias-flatpak.py` si cambia, regenera las
  dependencias y prueba el paquete instalado.

---

## 9. Recetas

### 9.1 Añadir un ajuste general (ejemplo real: «mostrar asignados frente a necesarios»)

1. **Servicio**: añade el campo con su valor por defecto en
   `servicios/ajustes.py` (`mostrar_cobertura: bool = False`). No hace falta
   migración: lo que no está en la tabla toma el valor por defecto.
2. **Esquema**: añade el campo a `Ajustes` en `api/esquemas.py` con su
   descripción.
3. **Prueba de la API**: actualiza `tests/api/test_configuracion.py` (valores por
   defecto y guardado).
4. **Contrato**: regenera `openapi.json` y los tipos (sección 3.7).
5. **Interfaz web**: el control en `paginas/Configuracion.tsx` (con
   `useGuardarAjustes`) y su efecto donde corresponda (aquí, `Calendario.tsx`
   con `useAjustes()`).
6. **Interfaz nativa**: la fila en `configuracion.py` (`_mostrar` y
   `_guardar_ajustes`) y su efecto (aquí, `calendario.py`, que pide los ajustes
   antes del calendario).
7. **Si afecta al motor**: pásalo en `servicios/periodos.construir` al
   `Problema` y úsalo en el motor, con pruebas en `tests/motor`.
8. **Prueba de flujo completo**, guía de uso y documentación técnica.

### 9.2 Añadir un dato a los médicos (una columna nueva)

1. Columna en `datos/tablas.py` (`Medico`).
2. Migración nueva (sección 3.4) y revisión del fichero generado; prueba en
   `tests/datos/test_bd.py` que migre una base anterior con datos.
3. `MedicoEntrada` en `api/esquemas.py` (la ruta `modificar` ya copia todos los
   campos).
4. Contrato, interfaz web (`TarjetaMedico.tsx`) e interfaz nativa
   (`medicos.py`, `_guardar_medico`).
5. Si lo usa el motor: `ReglasMedico` en `motor/entrada.py` y
   `servicios/periodos.construir`.

### 9.3 Añadir una regla al motor

1. Datos de entrada: el campo en `Problema` o `ReglasMedico` (`motor/entrada.py`).
2. Restricción en `_Modelo` (`modelo_cpsat.py`):
   - dura: `self.m.add(...)` directamente;
   - blanda: una variable de holgura y una pasada en `_objetivos()` en el lugar
     de prioridad que le toque.
3. Comprobación en `validacion.py` (genera el aviso) y, si puede ser imposible,
   la causa en `diagnostico.py`.
4. Pruebas en `tests/motor/`: que se cumpla cuando se puede, que avise cuando no
   y que no empeore el tiempo del caso real.
5. Datos y servicio para alimentarla desde la base (`construir`), API e
   interfaces.

### 9.4 Añadir una ruta a la API

1. Lógica en un servicio (si no es trivial).
2. Función en `api/rutas/<recurso>.py` con `response_model` y los esquemas de
   entrada; si el recurso es nuevo, registra su `router` en `api/app.py`.
3. Prueba en `tests/api/`.
4. Contrato regenerado; hook en `interfaz/src/api/consultas.ts`; llamada en la
   interfaz nativa con `cliente.en_segundo_plano`.

### 9.5 Añadir una pantalla

- **Web**: componente en `paginas/`, ruta en `App.tsx`, enlace en
  `componentes/Disposicion.tsx`.
- **Nativa**: clase con `pendiente` y `cargar()` (normalmente un
  `Adw.PreferencesPage` o un `Gtk.ScrolledWindow`), y su entrada en la lista de
  `Ventana.conectar` (nombre, título, icono).

### 9.6 Publicar una versión nueva

1. Sube `version` en `pyproject.toml` y reinstala (`pip install -e .`).
2. Añade un `<release>` en el AppStream.
3. Ejecuta todas las pruebas (Python, Vitest, tipos, flujo completo).
4. Actualiza la guía de uso y la historia de la documentación técnica.
5. `scripts/empaquetar-flatpak.sh` y, en cada equipo,
   `sudo flatpak install --system build/turnos-medicos-<versión>.flatpak`. Al
   abrirla, las migraciones actualizan los datos de cada usuario con copia
   previa.
6. Fusiona la rama en `main` y marca la versión con una etiqueta (`git tag -a v2.x`).

### 9.6.1 Regenerar las capturas de la guía

`scripts/capturas-guia.sh` arranca la aplicación con una base temporal, crea un
equipo **ficticio** (Dr. Díaz, Dra. García…) y vuelve a hacer las capturas de la
web de `docs/imagenes/` (las `nativa-*` se hicieron a mano con Xvfb). Nunca uses
datos reales en las capturas: se publican con la documentación.

### 9.7 Cambiar colores o textos visibles

- Web: variables en `estilos/global.css` (y su versión oscura); textos en los
  componentes y en `util/textos.ts`.
- Nativa: `arranque/gnome/estilos.css` (con reglas `.oscuro …` para el tema
  oscuro) y textos en cada pantalla o en `comun.py`.
- Si cambias un texto que buscan las pruebas de flujo completo, actualízalas.

---

## 10. Solución de problemas

| Síntoma | Causa | Qué hacer |
|---|---|---|
| «Sesión no válida» en el navegador | La pestaña es de un arranque anterior (otro token) | Abrir de nuevo con `turnos` o desde el icono |
| «Datos de una versión más reciente» | El fichero lo actualizó una versión más nueva | Instalar esa versión o una posterior; no se ha tocado nada |
| «No se puede usar el puerto 8000» | Otra instancia del modo web abierta | Cerrarla o usar `TURNOS_PUERTO=0` |
| La página no carga dentro del Flatpak («This call is not available inside the sandbox») | Un portal rechaza la llamada (pasó con el de proxy) | Revisar qué portal y sus permisos; el WebView ya va sin proxy |
| `flatpak-builder` falla con `rofiles-fuse` | Montaje FUSE en la carpeta del proyecto (sobre todo si está sincronizada con la nube) | El guion ya usa `--disable-rofiles-fuse` |
| pip falla al instalar en el Flatpak («Read-only file system») | Intenta desinstalar un paquete del SDK | Las dependencias se instalan con `--ignore-installed` |
| La prueba de la ventana no carga cuando la aplicación está abierta | Una sola instancia: la prueba pasa el control a la ventana abierta | Las pruebas ya usan su propia sesión de D-Bus |
| Capturas en blanco con Xvfb (`VK_ERROR_DEVICE_LOST`) | El render por Vulkan en Xvfb | `GSK_RENDERER=cairo` |
| Una prueba de flujo completo falla de vez en cuando | Esperas de 5 s con el equipo cargado | Repetirla; si se reproduce, investigar (no se ha visto fallar con el equipo libre) |
| `pkill -f patrón` termina la propia terminal | El patrón aparece en la misma línea de órdenes | Usar el PID guardado (`kill $pid`) |
| Generar tarda mucho | Una pasada del motor no demuestra su óptimo | Medir las pasadas (sección 3.3) y revisar el último cambio en los objetivos |

---

## 11. Glosario

| Término | Significado |
|---|---|
| Medio turno | La unidad de carga: un turno = 2. Todas las cargas se guardan así |
| Mitad | M1, M2 (mañana), T1, T2 (tarde). Una asignación es un médico en una mitad |
| Cobertura | Médicos necesarios (mínimo y máximo) en cada mitad de turno |
| Carga | Turnos al mes de un médico (rango mínimo–máximo), ajustada por sus ausencias |
| Elegibilidad | Para cada día y turno: Fijo (siempre), Habitual (preferido si trabaja ese día), Disponible o No disponible («—») |
| Jornada especial | Mañana + media tarde, media mañana + tarde, o doble; solo si la indica el planificador |
| Bloqueada | Asignación puesta a mano que el motor respeta |
| Veto | Turno quitado a mano que el motor no vuelve a asignar |
| Periodo | Un mes del calendario, con su estado (sin generar, borrador, publicado) |
| Saldo | Turnos de más o de menos acumulados en meses publicados; la equidad los compensa |
| Pasada | Cada objetivo de la optimización lexicográfica del motor |
| Holgura | Variable que mide cuánto se incumple una restricción blanda |
| Causa / incumplimiento | Aviso previo (por qué no puede cumplirse algo) / aviso posterior (qué no se cumple en el calendario) |
| Rotación | Turnos de la semana que un grupo hace por semanas alternas |
| Token | Clave aleatoria de cada arranque que protege la API |
