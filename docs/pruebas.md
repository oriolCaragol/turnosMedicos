# turnosMedicos — Pruebas automáticas

| | |
|---|---|
| Versión de la aplicación | 2.12 |
| Fecha | 2026-10-17 |
| Para quién | Quien vaya a ejecutar, entender, ampliar o mejorar las pruebas |
| Relacionado | [arquitectura.md](arquitectura.md) (capas y recorridos), [mantenimiento.md](mantenimiento.md) (componentes y recetas) |

Este documento explica **qué pruebas tiene la aplicación**, **cómo se
desarrollaron** y **por qué así**, **cómo ejecutarlas a mano** (todas, un
fichero o una sola prueba, y cómo depurar una que falla) y **cómo ampliarlas**,
con ejemplos sacados del propio código.

## Índice

1. [Resumen](#1-resumen)
2. [Cómo se han desarrollado](#2-cómo-se-han-desarrollado)
3. [Preparar el entorno](#3-preparar-el-entorno)
4. [Pruebas del núcleo y de la base de datos (pytest)](#4-pruebas-del-núcleo-y-de-la-base-de-datos-pytest)
5. [Pruebas de la interfaz web (Vitest)](#5-pruebas-de-la-interfaz-web-vitest)
6. [Pruebas de flujo completo (Playwright)](#6-pruebas-de-flujo-completo-playwright)
7. [Pruebas de las ventanas GTK](#7-pruebas-de-las-ventanas-gtk)
8. [Cobertura](#8-cobertura)
9. [Cómo ampliar las pruebas](#9-cómo-ampliar-las-pruebas)
10. [Mejoras posibles](#10-mejoras-posibles)
11. [Problemas frecuentes](#11-problemas-frecuentes)

---

## 1. Resumen

```
                    ▲  más lentas, más realistas
                    │
   Flujo completo   │  Playwright (19)      la aplicación de verdad en Chromium          ~20 s
   Ventanas GTK     │  pytest + Xvfb (4)    modo escritorio e interfaz nativa            ~30 s
   Interfaz web     │  Vitest (27)          lógica y componentes React, sin navegador    ~3 s
   API y arranque   │  pytest (77)          rutas, servicios y base de datos reales      ~10 s
   Núcleo           │  pytest (94)          dominio, motor, base de datos, recursos      ~15 s
                    │
                    ▼  más rápidas, más precisas
```

| Conjunto | Herramienta | Pruebas | Orden | Dónde |
|---|---|---|---|---|
| Núcleo, base de datos, API, arranque y ventanas GTK | pytest | 175 | `.venv/bin/pytest` | `tests/` |
| Lógica y componentes de la interfaz web | Vitest | 27 | `cd interfaz && npm test` | `interfaz/src/**/*.test.ts(x)` |
| Flujo completo de la interfaz web | Playwright | 19 | `scripts/e2e.sh` | `interfaz/e2e/` |
| Tipos de la interfaz web | TypeScript | — | `cd interfaz && npm run comprobar` | |
| Comprobación estática de Python | pyflakes | — | `.venv/bin/python -m pyflakes src tests scripts/*.py` | |

**Para dar un cambio por bueno** se ejecutan las cinco órdenes de la tabla y
todas deben pasar. La cobertura del núcleo (todo menos las ventanas) es del 97 %
(sección 8).

## 2. Cómo se han desarrollado

Las pruebas se escribieron **a la vez que el código, fase a fase** (la historia
completa está en la sección 14 de [documentacion-tecnica.md](documentacion-tecnica.md)).
Estas son las ideas que las guían:

1. **Probar comportamientos, no detalles internos.** Una prueba describe algo
   que el usuario o el planificador esperan («una asignación manual queda
   bloqueada y se respeta al regenerar»), no cómo está programado. Así se puede
   reorganizar el código sin reescribir las pruebas. Los nombres de las pruebas
   son frases en castellano que dicen lo que comprueban.
2. **Cada capa se prueba donde vive su lógica.** El motor, con problemas
   inventados en memoria; la API, con una base de datos temporal real; la
   interfaz, con un navegador real. No se repite en un nivel lo que ya se
   comprueba en otro más rápido.
3. **Sin simulaciones salvo lo externo.** La base de datos nunca se simula: se
   crea un SQLite temporal por prueba. Solo se sustituyen las fuentes de
   internet (festivos oficiales), para que las pruebas no dependan de la red.
4. **Cada fallo encontrado deja una prueba.** Cuando apareció un error, primero
   se escribió una prueba que lo reproducía y fallaba, después se corrigió y la
   prueba se quedó para siempre. Algunos ejemplos:

| Fallo real | Prueba que lo evita |
|---|---|
| Se perdían las reglas al cambiar de pestaña enseguida (fase 10) | `las reglas persisten aunque se cambie de pestaña enseguida` (Playwright) |
| «Generar» no asignaba nada a médicos sin carga (fase 11) | `test_medico_sin_carga_no_se_asigna`, `avisa junto al botón de generar si hay médicos sin carga mensual` |
| El «Fijo» de un médico chocaba con un turno rotativo (fase 16) | `test_la_rotacion_manda_sobre_el_fijo_de_la_tarjeta` (motor y API) |
| Repartos de urgencias 3/2/1 cuando cabía 2/2/2 (fase 18) | `test_reparto_igualado_aunque_unos_tengan_mas_tardes_disponibles`, `test_segun_presencia_sin_diferencias_injustificadas` |
| Al cerrar la ventana de escritorio se perdían los guardados pendientes (fase 17) | `test_abre_carga_guarda_al_cerrar_y_detiene_el_servidor` |
| Datos de una versión más nueva podían estropearse (fase 17) | `test_datos_de_una_version_mas_reciente_no_se_tocan` |

5. **Deterministas.** El motor usa un hilo y una semilla fija: los mismos datos
   dan el mismo calendario. Las pruebas no dependen de la fecha de hoy ni del
   orden en que se ejecuten (salvo las de Playwright, sección 6.4).
6. **Esperar a condiciones, no a tiempos.** Las pruebas de interfaz esperan a
   que aparezca algo (`await expect(…).toBeVisible()`, o una condición en las
   ventanas GTK) en lugar de dormir un tiempo fijo. Al pasar las de la interfaz
   nativa a condiciones, bajaron de 35 s a 7 s y dejaron de fallar con el equipo
   cargado.

## 3. Preparar el entorno

```sh
python3 -m venv --system-site-packages .venv      # ve PyGObject del sistema (pruebas GTK)
.venv/bin/pip install -e '.[dev]'                  # pytest, httpx, pyflakes
(cd interfaz && npm ci)                            # Vitest, Playwright, Testing Library
```

| Para | Hace falta además |
|---|---|
| Playwright | Chromium del sistema (`/usr/bin/chromium-browser`, o la ruta en `CHROMIUM`) y `curl` |
| Pruebas de las ventanas GTK | `python3-gobject`, `gtk4`, `libadwaita`, `webkitgtk6.0`, `xvfb-run`, `dbus-run-session`; `pdfinfo` (poppler) para contar páginas de los PDF |

Si falta algo de lo segundo, esas pruebas **se saltan** solas (aparecen como
`skipped`), el resto se ejecuta igual.

> **VS Code instalado como Flatpak**: su terminal no tiene Node ni el Python del
> sistema. Usa una terminal del sistema o antepón `flatpak-spawn --host`.

---

## 4. Pruebas del núcleo y de la base de datos (pytest)

### 4.1 Ejecutarlas

```sh
.venv/bin/pytest                                   # todas (175)
.venv/bin/pytest tests/motor                       # una carpeta
.venv/bin/pytest tests/api/test_periodos.py        # un fichero
.venv/bin/pytest tests/api/test_periodos.py::test_alternativa      # una prueba
.venv/bin/pytest -k "urgencias or domicilios"      # por nombre (expresión)
.venv/bin/pytest -m escritorio                     # solo las ventanas GTK
.venv/bin/pytest -m "not escritorio"               # todo menos las ventanas
.venv/bin/pytest -x                                # parar en el primer fallo
.venv/bin/pytest --lf                              # solo las que fallaron la última vez
.venv/bin/pytest -v                                # una línea por prueba
.venv/bin/pytest --durations=10                    # las 10 más lentas
.venv/bin/pytest -s                                # ver los print()
.venv/bin/pytest --pdb                             # abrir el depurador al fallar
```

La configuración está en `pyproject.toml` (`[tool.pytest.ini_options]`): carpeta
`tests` y la marca `escritorio`.

### 4.2 Organización

`tests/` reproduce las capas de `src/turnos/`:

| Carpeta | Pruebas | Qué cubre |
|---|---|---|
| `dominio/` | 21 | Tipos y reglas puras: mitades de cada turno, jornadas especiales, rangos de carga no válidos, ausencias de día completo o de un turno, días laborables, ajuste de la carga por ausencias y su redondeo |
| `motor/` | 57 | El resolvedor: cobertura, turnos completos y uno al día, fijos y no disponibles, ausencias, jornadas especiales, bloqueos y vetos, carga y carga por turno, calendario de mejor esfuerzo con avisos cuando faltan médicos, equidad (también entre meses), preferencias, estabilidad al regenerar, determinismo, alternativas, rendimiento con un mes real, turno habitual, urgencias y domicilios (reparto igualado y según presencia, bandas por restos mayores), turnos rotativos, «todos trabajan cada día» y la validación posterior |
| `datos/` | 13 | La base de datos: creación con todas las tablas, datos iniciales, reinicializar sin duplicar ni deshacer, años de festivos incompletos, claves ajenas, migración de la 0001 a la última conservando datos, copia previa, `busy_timeout`, datos de una versión más nueva, municipio distinto de Madrid (sin precargados) |
| `recursos/` | 6 | Los festivos precargados: que existan y sean coherentes (fechas del año, entre semana o no, ámbitos) |
| `api/` | 102 | Todas las rutas con una base temporal: médicos y reglas (versiones), ausencias, festivos (precargados, oficiales, restaurar), cobertura, horarios, ajustes, estado, calendario del mes (generar, cambios, bloqueos, deshacer, publicar, alternativa, carga manual, saldo, volver a automático, urgencias y domicilios), turnos rotativos, exportación XLSX, copia de seguridad, importar, que se sirve la interfaz; varios clientes a la vez (versión del mes y 409, bloqueo al generar, registro de cambios, WAL solo si se pide, dos clientes reales a la vez, eventos con su origen, parada con un cliente de eventos conectado); modo servidor en `test_acceso.py` (entrar y salir, cookie protegida, token para las aplicaciones, límite de intentos, caducidad y renovación de sesiones, CSRF, permisos de cada rol, contraseña temporal, cuentas, dispositivos, registro con el usuario, importar conservando las cuentas); solicitudes en `test_solicitudes.py` (cada tipo, efectos, aprobar en un mes publicado sin reabrirlo, intercambio que acepta o no el compañero, que cada médico solo ve y retira las suyas, rechazar y resolver de otra forma) |
| `arranque/` | 15 | El servidor común (puerto libre, token, parada, puerto ocupado, datos más nuevos) y el token (401 sin sesión, cookie tras `?token=`, cabecera, cookie de otro puerto) y la versión de Windows (rutas de datos y configuración, autoprueba del ejecutable) |
| `red/` | 15 | El modo servidor: configuración, autoridad con restricciones de nombre (verificada como un navegador, también que no vale para webs de internet), renovación, perfil de iPhone, copias diarias y su limpieza, `crear-administrador` y un servidor HTTPS real de principio a fin; en `test_cliente.py`, lo que usan las aplicaciones para conectarse (dirección, confirmar la autoridad, entrar, que otra autoridad no vale) |
| `escritorio/` | 12 | Las ventanas GTK (sección 7) |

### 4.3 Preparaciones comunes (fixtures)

pytest inyecta en cada prueba los objetos que pide por nombre. Las de la API
están en `tests/api/conftest.py`:

| Fixture | Qué da |
|---|---|
| `tmp_path` (de pytest) | Una carpeta temporal nueva para cada prueba |
| `motor` | `inicializar(tmp_path / "turnos.sqlite")`: una base nueva, migrada y con los datos iniciales |
| `cliente` | `TestClient(crear_app(motor, interfaz=None))`: un cliente HTTP contra la aplicación, sin servidor ni token |
| `medico` | Un médico creado por la API |
| `equipo` | 4 médicos con reglas desde noviembre de 2026 (Ana con el lunes por la mañana fijo) y cobertura de 1 médico por turno |

```python
@pytest.fixture
def motor(tmp_path):
    return inicializar(tmp_path / "turnos.sqlite")

@pytest.fixture
def cliente(motor):
    return TestClient(crear_app(motor, interfaz=None))
```

Como cada prueba tiene su propia base, las pruebas son independientes y se
pueden ejecutar en cualquier orden o por separado.

Las del motor no usan fixtures sino **funciones auxiliares** al principio de
cada fichero, que construyen problemas pequeños en memoria:

```python
LUNES = date(2026, 11, 2)

def medico(id_: int, minimo: int = 0, maximo: int = 100, **kw) -> ReglasMedico:
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(minimo, maximo), **kw)

def problema(medicos, semanas=1, **kw) -> Problema:
    dias = laborables(semanas)
    kw.setdefault("cobertura", cobertura(dias))
    return Problema(dias=dias, medicos=tuple(medicos), **kw)
```

### 4.4 Patrones con ejemplos

**Una prueba del motor**: se construye el problema justo para lo que se quiere
comprobar, se genera y se comprueba el resultado.

```python
def test_segun_presencia_las_ausencias_reducen_la_parte():
    ausente = (Ausencia(LUNES, LUNES + timedelta(days=4)),)  # falta la primera de dos semanas
    medicos = [medico(1, ausencias=ausente), medico(2), medico(3), medico(4)]
    r = generar(problema(medicos, semanas=2, roles_segun_presencia=True))
    assert r.valido
    for rol in Rol:
        assert [_veces(r, rol)[m] for m in (1, 2, 3, 4)] == [1, 3, 3, 3], rol
```

**Una prueba de la API**: peticiones reales y comprobación de la respuesta y del
estado posterior.

```python
def test_publicar_impide_cambios_hasta_reabrir(cliente, equipo):
    cliente.post(f"{URL}/generar", json={})
    cal = cliente.post(f"{URL}/publicar").json()
    assert cal["estado"] == "PUBLICADO" and cal["publicado_en"]
    assert cliente.post(f"{URL}/generar", json={}).status_code == 409   # publicado: no se regenera
    a = cal["asignaciones"][0]
    r = cliente.post(f"{URL}/cambios", json=[{"medico_id": a["medico_id"], "fecha": a["fecha"], "mitades": []}])
    assert r.status_code == 409                                          # ni se cambia
    assert cliente.post(f"{URL}/reabrir").json()["estado"] == "BORRADOR"
```

**Una prueba de migraciones**: se crea una base en la versión 0001, se le meten
datos con SQL directo, se migra a la última y se comprueba que los datos siguen
ahí (`test_migrar_de_0001_a_la_ultima_conserva_los_datos`). Es la forma de
asegurar que una versión nueva no estropea los datos de quien ya usaba la
anterior.

**Simular una fuente externa** con `monkeypatch` (festivos oficiales):

```python
@pytest.fixture
def fuentes(monkeypatch):
    respuestas = {}
    def descargar(url):
        valor = respuestas.get(url)
        if isinstance(valor, Exception):
            raise valor            # simula «sin conexión»
        return valor               # None simula un 404
    monkeypatch.setattr(festivos_oficiales, "descargar_json", descargar)
    return respuestas
```

**Varios casos con la misma prueba** (`parametrize`):

```python
@pytest.mark.parametrize("minimo, maximo", [(-1, 4), (5, 4)])
def test_rango_carga_no_valido(minimo, maximo):
    with pytest.raises(ValueError):
        RangoCarga(minimo, maximo)
```

**Comprobar un fichero generado**: las pruebas de exportación abren el XLSX con
openpyxl y miran celdas concretas; la de importar descarga una copia de otra
instalación y la sube.

**Rendimiento**: `test_tamano_real_en_menos_de_10_segundos` genera un mes de 30
médicos y falla si tarda 10 s o más. Avisa si un cambio en el motor lo hace
demasiado lento (pasó dos veces durante el desarrollo, fases 18 y 20).

---

## 5. Pruebas de la interfaz web (Vitest)

### 5.1 Ejecutarlas

```sh
cd interfaz
npm test                                   # todas, una vez (vitest run)
npx vitest                                 # modo vigilancia: repite al guardar
npx vitest run src/calendario              # una carpeta o fichero
npx vitest run -t "copiar mantiene"        # por nombre
npm run comprobar                          # tipos de TypeScript (tsc -b)
```

La configuración está en `interfaz/vite.config.ts` (sección `test`): entorno
**jsdom** (un DOM simulado, sin navegador), `globals` (`test` y `expect` sin
importar) y `src/pruebas.setup.ts`, que añade comprobaciones como
`toBeVisible()` o `toHaveAccessibleName()` de Testing Library.

### 5.2 Qué cubren

| Fichero | Pruebas | Qué cubre |
|---|---|---|
| `calendario/logica.test.ts` | 12 | La lógica del calendario sin React: mover, copiar y quitar al soltar, añadir desde la tabla, jornadas, estado de un turno según la cobertura, idoneidad al arrastrar, selector No / ½ / 1, cifras, papeles y foto para deshacer |
| `componentes/CuadriculaElegibilidad.test.tsx` | 4 | La cuadrícula semanal: pulsar para cambiar de valor, arrastrar para pintar, uso con el teclado, atajos |
| `componentes/CampoTurnos.test.tsx` | 4 | El campo de turnos: conversión a medios turnos, múltiplos de 0,5, vacío como «sin límite» |
| `rotaciones/semanas.test.ts` | 3 | A quién le toca cada semana de un turno rotativo |
| `util/colores.test.ts`, `util/util.test.ts` | 4 | Colores legibles, medios turnos y fechas |

### 5.3 Patrones

**Lógica pura**: funciones de entrada y salida, sin pantalla. Es el sitio para
las reglas de interacción con muchos casos:

```ts
test("copiar mantiene el origen", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  const origen = { tipo: "celda" as const, medico: 1, fecha: "2026-11-03", turno: "MANANA" as const };
  expect(cambiosAlSoltar(c, origen, { fecha: "2026-11-03", turno: "TARDE" }, true)).toEqual([
    { medico_id: 1, fecha: "2026-11-03", mitades: ["M1", "M2", "T1", "T2"] },
  ]);
});
```

**Componentes** con Testing Library: se dibuja el componente y se interactúa
como un usuario, buscando los elementos **por su rol y su nombre accesible**:

```tsx
test("pulsar una celda pasa al siguiente valor", () => {
  render(<Envoltorio />);
  const lunes = screen.getByRole("button", { name: /Lunes, mañana/ });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Disponible");
  fireEvent.pointerDown(lunes, { button: 0 });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Habitual");
});
```

Buscar por rol y nombre tiene una ventaja doble: la prueba no se rompe al
cambiar clases o estructura, y obliga a que la interfaz sea accesible para
lectores de pantalla.

---

## 6. Pruebas de flujo completo (Playwright)

Prueban **la aplicación de verdad**: el servidor Python con una base real, la
interfaz compilada y un navegador Chromium que hace clic, arrastra y escribe
como un usuario.

### 6.1 Ejecutarlas

La forma normal es el guion, que lo prepara todo:

```sh
scripts/e2e.sh
```

Qué hace `scripts/e2e.sh`:

1. compila la interfaz (`npm run build`);
2. arranca la aplicación en el puerto 8790 (`E2E_PUERTO` para otro) con una
   **base de datos temporal vacía**, sin abrir navegador y **sin token**
   (Playwright también llama a la API directamente), y con las fuentes de
   festivos apuntando a ficheros de prueba (`interfaz/e2e/datos`, por `file://`);
3. espera a que responda `/api/estado`;
4. ejecuta `npx playwright test` contra ella;
5. al terminar (bien o mal), para el servidor y borra la base temporal.

Para depurar es más cómodo arrancar la aplicación a mano y lanzar Playwright
con opciones:

```sh
# Terminal 1: la aplicación con una base vacía
TURNOS_DATOS=/tmp/e2e.sqlite TURNOS_PUERTO=8790 TURNOS_SIN_NAVEGADOR=1 TURNOS_SIN_TOKEN=1 \
TURNOS_FUENTE_FESTIVOS_IO="file://$PWD/interfaz/e2e/datos/festivos-io/{anio}-{ine}.json" \
TURNOS_FUENTE_MADRID="file://$PWD/interfaz/e2e/datos/madrid-locales.json" \
  .venv/bin/turnos

# Terminal 2
cd interfaz
npx playwright test                               # todas
npx playwright test e2e/configuracion.spec.ts     # un fichero
npx playwright test -g "vista en lista"           # por nombre
npx playwright test --headed                      # ver el navegador
npx playwright test --debug                       # paso a paso, con el inspector
npx playwright test --ui                          # interfaz gráfica de Playwright
npx playwright show-trace test-results/<prueba>/trace.zip   # reproducir un fallo
```

> La base debe estar **vacía** al empezar: la preparación inicial se salta si ya
> hay médicos (sección 6.4). Borra `/tmp/e2e.sqlite` entre ejecuciones manuales.

### 6.2 Configuración

`interfaz/playwright.config.ts`:

```ts
export default defineConfig({
  testDir: "e2e",
  workers: 1,                       // una a una, en orden (comparten la base)
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_URL ?? "http://127.0.0.1:8790",
    locale: "es-ES",
    viewport: { width: 1400, height: 1000 },
    launchOptions: { executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium-browser" },
    trace: "retain-on-failure",     // guarda la traza completa de las que fallan
  },
});
```

Se usa el **Chromium del sistema** en lugar de los navegadores que descarga
Playwright, que no están soportados en Fedora.

Hay dos **proyectos**: `personal` (todas las pruebas salvo `servidor.spec.ts`,
contra el modo personal) y `servidor` (solo esa, contra `turnos servidor` con
HTTPS en el puerto siguiente, con `ignoreHTTPSErrors` porque el navegador de
pruebas no tiene instalada la autoridad propia). `scripts/e2e.sh` arranca los dos
servidores y crea el administrador `admin`; se puede elegir uno con
`scripts/e2e.sh --project servidor`.

### 6.3 Qué cubren

`e2e/calendario.spec.ts` (16), `e2e/configuracion.spec.ts` (3),
`e2e/varios-clientes.spec.ts` (2) y, en el proyecto `servidor` contra un
servidor HTTPS real (ver 6.2), `e2e/servidor.spec.ts` (6):

| Prueba | Qué recorre |
|---|---|
| generar, editar arrastrando, deshacer, regenerar y publicar | El ciclo completo del mes: generar, quitar arrastrando fuera, deshacer con Ctrl+Z y con botones, añadir desde la tabla de carga, avisos, bloqueos, regenerar respetando lo manual, publicar y reabrir |
| panel de un turno: medio turno y volver a automático | El panel lateral: poner medio turno, volver a automático |
| vista en lista | Cambiar a lista, que se recuerde al recargar |
| médicos y reglas: tarjetas que se guardan solas y ausencias | Autoguardado de la tarjeta, ausencias, «Más reglas» |
| las reglas persisten aunque se cambie de pestaña enseguida | El fallo de la fase 10 |
| un médico nuevo conserva su disponibilidad aunque aún no tenga carga | Guardado sin carga |
| la cobertura persiste aunque se cambie de pestaña enseguida | Autoguardado de la cobertura |
| exportar, imprimir y copia de seguridad | Descargas y vista para imprimir |
| turno habitual: el panel del turno lo indica | Elegibilidad «Habitual» |
| pestañas: el mes se conserva y las direcciones antiguas redirigen | Navegación |
| avisa junto al botón de generar si hay médicos sin carga mensual | El fallo de la fase 11 |
| color de cada médico | De la tarjeta al calendario |
| urgencias y domicilios | Uno de cada cada tarde, intercambio a mano, recuento, informe para imprimir y XLSX |
| configuración: todos trabajan cada día | La opción y su aviso |
| turnos rotativos | Subpestaña, vista previa, alternancia en el calendario |
| configuración: urgencias y domicilios según la presencia | La opción, activada por defecto |
| festivos oficiales | Cambiar el municipio, buscar con fuentes de prueba, añadir los que faltan |
| datos: importar una copia | Sustituir los datos y rechazar un fichero que no es una copia |
| vista del calendario: asignados frente a necesarios | Oculto por defecto, aparece al activarlo |
| dos usuarios ven en vivo los cambios del otro | Dos contextos de navegador (`browser.newContext()`) sobre diciembre: lo que genera o quita uno lo ve el otro sin recargar, y un cambio ajeno vacía el historial de deshacer |
| entrar, cuentas, un médico en el móvil y dispositivos conectados | Entrada (con error), cuenta de médico con contraseña temporal, que la cambia desde un móvil (390 px, sin desplazamiento lateral), el administrador cierra su sesión, planificador sin «Administración», salir |
| servidor: direcciones con QR, certificado y copia inmediata | La pestaña Administración: QR que carga, huella, perfil de iPhone sin sesión, copia a mano |
| cambiar la propia contraseña desde la cabecera | Validación de las dos contraseñas y entrar con la nueva |
| un médico ve en el móvil sus turnos, el calendario del equipo y su ficha | Sin meses publicados, el aviso; al publicar, aparece en vivo; sus días, el calendario con el festivo, su ficha de solo lectura y que la API le niega cambiar |
| aplicación instalable: manifiesto e iconos | Tipo del manifiesto, iconos accesibles, icono de iPhone |
| solicitudes: el médico pide desde el móvil y el planificador decide desde el PC | Ausencia pedida en el móvil, contador y efectos en el PC, aprobada con comentario y vista en vivo; un turno que no puede hacer, rechazado con motivo |
| un cambio sobre una versión antigua se rechaza | La página no recibe eventos (`page.route` corta `/api/eventos`), otro cliente publica el mes y el cambio de la página recibe 409, se avisa y se muestra la versión actual |

### 6.4 Cómo están escritas

**Datos de partida.** `calendario.spec.ts` prepara un equipo de 4 médicos con un
`beforeAll` que llama a la API (más rápido y fiable que hacerlo por pantalla):

```ts
test.beforeAll(async ({ request }) => {
  const medicos = await (await request.get("/api/medicos")).json();
  test.skip(medicos.length > 0, "La prueba necesita una base de datos vacía");
  for (const [nombre, codigo] of [["Ana Ruiz", "ANA"], ["Bea Gil", "BEA"], ...]) { ... }
  await request.put("/api/cobertura/semanal", { data: cobertura });
});
```

**Estado compartido y orden.** Las pruebas se ejecutan una a una y en orden
(`workers: 1`) sobre la misma base: generar un mes en una prueba lo deja
generado para las siguientes. Por eso:

- una prueba que cambia algo global (un ajuste, la cobertura, un municipio) **lo
  deja como estaba** al terminar;
- si una prueba falla, Playwright reinicia el proceso, el `beforeAll` vuelve a
  ejecutarse, ve la base con médicos y **se salta** el resto del fichero (esas
  pruebas aparecen como *skipped*, no como fallos). Arregla primero la que falló.

**Encontrar elementos.** Por orden de preferencia:

1. **Por rol y nombre accesible**: `page.getByRole("button", { name: "Regenerar" })`;
2. **Por etiqueta**: `page.getByLabel("Mostrar en cada turno …")`;
3. **Por texto visible**: `page.getByText("Borrador", { exact: true })`;
4. **Por atributos `data-` pensados para las pruebas**, cuando no hay un nombre
   claro: `[data-celda="2026-11-03-MANANA"]` (un turno de un día),
   `[data-ficha]` (una ficha de médico), `[data-medico]`, `[data-rotacion]`,
   `[data-vista]`.

**Ayudas** al principio de `calendario.spec.ts`: `franja(page, fecha, turno)`
localiza un turno y `arrastrar(page, origen, destino)` simula un arrastre con el
ratón paso a paso (dnd-kit necesita movimientos intermedios para reconocerlo).

**Esperas.** Las comprobaciones de Playwright (`await expect(…).toBeVisible()`,
`toHaveCount`, `toHaveText`) reintentan hasta 5 s: no hace falta dormir. Cuando
hay que esperar a que termine una petición antes de leer la API, se espera a su
respuesta:

```ts
await Promise.all([
  page.waitForResponse((r) => r.url().includes("/generar") && r.ok()),
  page.getByRole("button", { name: "Regenerar" }).click(),
]);
const cal = await (await request.get("/api/periodos/2026/11")).json();
```

(Sin esa espera, una prueba leía el calendario antes de que terminara la
regeneración y fallaba a veces: fase 16.)

**Diálogos del navegador** (`confirm`): se aceptan antes de provocarlos con
`page.once("dialog", (d) => d.accept())`.

**Ficheros**: para importar se usa `setInputFiles` con un búfer en memoria; para
las descargas, `request.get(...)` sobre la ruta de la API.

---

## 7. Pruebas de las ventanas GTK

`tests/escritorio/` comprueba el modo escritorio y la interfaz nativa con
ventanas reales, sin pantalla.

| Prueba | Qué comprueba |
|---|---|
| `test_humo.py` | El modo escritorio abre, carga la interfaz web en el WebView, al cerrar envía un guardado hecho en `pagehide` y detiene el servidor |
| `test_gnome.py::test_generar_retocar_y_guardar…` | Interfaz nativa: genera, quita a un médico de una tarde y cambia un papel desde el diálogo, guarda reglas y añade un festivo |
| `test_gnome.py::test_resto_de_funciones…` | Interfaz nativa: alternativa, deshacer y rehacer, arrastrar, ajustar un rango, imprimir los dos informes a PDF, ausencia, «Más reglas», turno rotativo, cobertura y excepción, horario y festivos |
| `test_gnome.py::test_la_interfaz_nativa_ve_los_cambios_de_otro_cliente` | Otro cliente cambia el mes con la ventana abierta: la ventana lo ve sin recargar y vacía su historial de deshacer; si deja de escuchar y cambia una versión antigua, recibe 409 y muestra la actual |
| `test_gnome.py::test_la_interfaz_nativa_como_cliente_de_un_servidor` | Contra un `turnos servidor` real: entra como planificador, genera noviembre en el servidor (el registro lo anota a su nombre) y no arranca servidor interno |
| `test_gnome.py::test_un_medico_en_la_interfaz_nativa_va_a_la_web` | Un médico que entra en la nativa ve el enlace a la web |
| `test_gnome.py::test_bandeja_de_solicitudes_en_la_interfaz_nativa` | El contador de la pestaña, los efectos y aprobar una ausencia pedida por una médica, con comentario |
| `test_humo.py::test_como_cliente_de_un_servidor_y_recuerda_la_sesion` | El WebView carga la web del servidor con su autoridad, entra y, al volver a abrir, la sesión sigue |
| `test_gnome.py::test_al_abrir_se_elige_trabajar_en_este_equipo` | La pantalla de inicio: «En este equipo» arranca el servidor interno y, sin «Recordar», volverá a preguntar |
| `test_gnome.py::test_al_abrir_se_elige_un_servidor_y_se_confirma_su_huella` | La pantalla de inicio contra un servidor real: «Recordar», la huella que se confirma, entrar como planificador |
| `test_gnome.py::test_soltar_un_medico_como_en_la_web` | La lógica de soltar de la nativa con los mismos casos que la web |

**Cómo funcionan.** La prueba prepara una base con la API y lanza un programa
auxiliar (`humo.py`, `gnome_humo.py`, `gnome_completa.py`, `gnome_varios.py`) dentro de:

- `xvfb-run`: una pantalla X virtual;
- `dbus-run-session` con una configuración **sin servicios activables**: así no
  interfiere con la aplicación si está abierta en el escritorio (es de una sola
  instancia) y no pierde tiempo esperando portales que no existen;
- variables que evitan esperas inútiles (`GDK_DEBUG=no-portals`, `NO_AT_BRIDGE=1`,
  `GTK_A11Y=none`).

El programa auxiliar recorre una lista de **(condición, acción)**: comprueba la
condición cada 100 ms y, cuando se cumple, ejecuta la acción. Al terminar escribe
un JSON con lo que ha visto; la prueba lo lee y **comprueba el resultado en la
API**.

```python
pasos = [
    (lambda: cal().get("estado") == "BORRADOR" and libre(), guardar_base),
    (lambda: libre() and p("calendario")._generar.get_sensitive(), tras_alternativa),
    ...
]
```

### 7.1 Instalación en la Raspberry Pi (a mano)

`scripts/probar-raspberry-contenedor.sh` instala el servidor en un contenedor
Debian 13 **arm64** emulado (podman + qemu-user-static) con
`empaquetado/raspberry/instalar.sh`, lo vuelve a instalar (actualización), crea
el administrador, lo arranca como el usuario `turnos` con HTTPS, entra y mide el
motor. No forma parte de pytest porque tarda varios minutos y necesita podman; se
lanza al cambiar dependencias o el instalador.

---

## 8. Cobertura

La **cobertura** mide qué líneas del código ejecutan las pruebas. No dice si las
pruebas comprueban bien, pero señala lo que nadie prueba.

```sh
.venv/bin/pytest --cov=turnos --cov-report=term-missing   # por fichero, con las líneas sin probar
.venv/bin/pytest --cov=turnos --cov-report=html           # informe navegable en htmlcov/index.html
```

(`pytest-cov` no está en las dependencias de desarrollo del proyecto; en este
equipo viene de los paquetes del sistema. Si no lo tienes: `.venv/bin/pip
install pytest-cov`.)

Medición del 17/10/2026:

| Parte | Cobertura |
|---|---|
| Dominio, datos, recursos, servicios de ajustes y rotaciones | 100 % |
| Motor | 98–100 % (`diagnostico.py` 95 %) |
| API | 93–100 % |
| Servicios del mes, reglas, importar | 95–98 % |
| Festivos oficiales | 81 % (ramas de error de red poco comunes) |
| Exportación | 98 % |
| Arranque común (servidor, web) | 65–85 % |
| **Núcleo en conjunto** (todo menos las ventanas, `motor/ejemplo.py` y las órdenes `__main__`) | **97 %** |
| Modo escritorio e interfaz nativa | aparecen con 0–27 % |

Las ventanas aparecen casi sin cubrir porque sus pruebas las ejecutan en **otro
proceso** (con Xvfb), que la medición no sigue. Sí se ejecutan; para medirlas
habría que activar la cobertura en subprocesos (sección 10).

---

## 9. Cómo ampliar las pruebas

### 9.1 ¿Dónde va una prueba nueva?

| Si el cambio está en… | La prueba va en… |
|---|---|
| Una regla de cálculo pura | `tests/dominio/` |
| El motor (una regla, un objetivo) | `tests/motor/`, con un problema hecho a mano |
| El esquema de la base o una migración | `tests/datos/test_bd.py` |
| Un servicio o una ruta | `tests/api/`, con `cliente` y las fixtures |
| La lógica de la interfaz web | Una función en `calendario/logica.ts` o similar y su `*.test.ts` |
| Un componente con interacción propia | `*.test.tsx` con Testing Library |
| Un recorrido de usuario o un fallo que solo se ve en el navegador | `interfaz/e2e/` |
| La ventana de escritorio o la interfaz nativa | `tests/escritorio/` |

Regla práctica: **la prueba más rápida que pueda detectar el fallo**. Una regla
del motor se prueba en el motor, no con Playwright.

### 9.2 Lista de comprobación al añadir una funcionalidad

1. Al menos una prueba de la capa donde vive la lógica: el caso normal, un caso
   límite y uno de error o imposible.
2. Si cambia la API: prueba en `tests/api/` y regenerar los tipos de la interfaz
   (TypeScript señalará lo que hay que adaptar).
3. Si cambia el esquema: prueba de migración con datos.
4. Si cambia lo que ve el usuario: una prueba de Playwright (o ampliar una
   existente) y, si toca la interfaz nativa, su paso en `gnome_completa.py`.
5. Si se corrige un fallo: primero la prueba que lo reproduce y falla.
6. Las cinco órdenes de la sección 1, en verde.

### 9.3 Ejemplo: una prueba de motor nueva

```python
# tests/motor/test_modelo.py
def test_nadie_trabaja_si_la_cobertura_es_cero():
    p = problema([medico(1), medico(2)], cobertura=cobertura(laborables(), manana=(0, 0), tarde=(0, 0)))
    r = generar(p)
    assert r.valido
    assert not r.asignaciones
```

### 9.4 Ejemplo: una prueba de API nueva

```python
# tests/api/test_medicos.py
def test_desactivar_un_medico(cliente, medico):
    datos = {**medico, "activo": False}
    del datos["id"]
    r = cliente.put(f"/api/medicos/{medico['id']}", json=datos)
    assert r.status_code == 200 and r.json()["activo"] is False
```

### 9.5 Ejemplo: una prueba de migración nueva

Cuando añadas la migración 0006, amplía
`test_migrar_de_0001_a_la_ultima_conserva_los_datos` con datos que la toquen, o
añade una prueba que cree la base en la 0005 (`command.upgrade(cfg, "0005")`),
inserte datos, migre a la última y compruebe que siguen bien.

### 9.6 Ejemplo: una prueba de Playwright nueva

```ts
// interfaz/e2e/configuracion.spec.ts
test("horario: se guarda y aparece en la vista para imprimir", async ({ page }) => {
  await page.goto("/configuracion?mes=2026-11");
  await page.getByLabel("Mañana, inicio").fill("08:30");
  await page.getByRole("button", { name: "Guardar horarios" }).click();
  await expect(page.getByText("Horarios guardados")).toBeVisible();
  await page.goto("/imprimir?mes=2026-11");
  await expect(page.getByRole("columnheader", { name: /Mañana 08:30/ })).toBeVisible();
  // Deja los datos como estaban para las demás pruebas.
  ...
});
```

Consejos:

- **Usa nombres accesibles.** Si no puedes encontrar algo por su rol y nombre,
  probablemente le falta una etiqueta (`aria-label`), y añadírsela mejora
  también la accesibilidad.
- Si necesitas un atributo para la prueba, usa `data-…` con un nombre que
  describa qué es, no cómo se ve.
- Prepara los datos por la API (`request`), no por la pantalla, salvo que lo
  que pruebes sea precisamente esa pantalla.
- **Deja el estado como estaba** al terminar.
- Si dependes de internet, añade un fichero en `interfaz/e2e/datos` y apunta la
  fuente a él en `scripts/e2e.sh`.

---

## 10. Mejoras posibles

Ideas para cuando se quiera ir más allá, con cómo empezar cada una.

| Mejora | Para qué | Cómo empezar |
|---|---|---|
| **Integración continua** | Ejecutar todo en cada cambio, sin depender de acordarse | Un flujo de GitHub Actions o GitLab CI en Fedora o Ubuntu con Python, Node y Chromium que ejecute las cinco órdenes; las pruebas GTK necesitan Xvfb (`xvfb-run`) en la imagen |
| **Cobertura en el proyecto y en las ventanas** | Medir también lo que se prueba en subprocesos | Añadir `pytest-cov` a `[dev]`; para los subprocesos, `coverage` con `COVERAGE_PROCESS_START` y `parallel = true` en `pyproject.toml` |
| **Pruebas basadas en propiedades** para el motor | Que el resolvedor cumpla siempre ciertas propiedades con datos al azar (nunca dos turnos a la vez, nunca un médico ausente, cobertura cumplida si es posible) | La biblioteca **Hypothesis**: generar equipos y coberturas aleatorias pequeños y comprobar invariantes sobre el `Resultado` |
| **Prueba de calendarios de referencia** | Detectar cambios no buscados en el resultado del motor | Guardar el calendario generado para unos cuantos problemas fijos y compararlo (gracias al determinismo); actualizarlo a propósito cuando se cambie el motor |
| **Medir el rendimiento con más casos** | Vigilar el tiempo de generación con equipos y meses variados | Ampliar `test_tamano_real…` con varios tamaños y ausencias, o usar `pytest-benchmark` |
| **Comprobación de accesibilidad automática** | Detectar contraste insuficiente, botones sin nombre… | `@axe-core/playwright` en las pruebas de Playwright: `await new AxeBuilder({ page }).analyze()` |
| **Comparación visual** de la interfaz | Detectar cambios de maquetación (como los de la interfaz nativa, que hubo que revisar con capturas) | `expect(page).toHaveScreenshot()` en Playwright; para GTK, comparar las capturas de Xvfb con una referencia y una tolerancia |
| **Pruebas en paralelo** de Playwright | Reducir el tiempo | Una base y un servidor por *worker*, o pruebas independientes que preparen sus propios datos |
| **Motor WebKit en Playwright** | Acercarse al WebKitGTK del modo escritorio | El proyecto `webkit` de Playwright (no está soportado en Fedora; las pruebas GTK ya cubren el WebKitGTK real) |
| **Pruebas de mutación** | Saber si las pruebas detectan fallos de verdad | `mutmut` sobre `turnos.motor` y `turnos.servicios`: introduce pequeños errores y comprueba que alguna prueba falla |

---

## 11. Problemas frecuentes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| Playwright: muchas pruebas *skipped* | Falló una antes y el `beforeAll` encontró la base con datos | Arreglar la primera que falló; en ejecución manual, empezar con la base vacía |
| Playwright: «La prueba necesita una base de datos vacía» | Se lanzó contra una base con datos | Usar `scripts/e2e.sh` o borrar la base temporal |
| Playwright no encuentra el navegador | Chromium en otra ruta | `CHROMIUM=/ruta/al/chromium scripts/e2e.sh` |
| Una prueba de Playwright falla de vez en cuando | Comprobaciones con 5 s de margen y el equipo muy cargado | Repetir; si se reproduce, revisar las esperas (¿falta un `waitForResponse`?) |
| Pruebas GTK *skipped* | Falta GTK, libadwaita, WebKitGTK, `xvfb-run` o `dbus-run-session` | Instalarlos (sección 3); el resto de pruebas no se ve afectado |
| Prueba GTK: «no carga» o tarda 30 s | Sesión de D-Bus sin aislar (pasaba con la aplicación abierta) | Las pruebas ya usan su propia sesión sin servicios; si escribes una nueva, copia `_preparar` y `_ejecutar` de `test_gnome.py` |
| `test_tamano_real_en_menos_de_10_segundos` falla | Un cambio en el motor lo ha hecho más lento, o el equipo está muy ocupado | Medir las pasadas (ver [mantenimiento.md](mantenimiento.md), 3.3) |
| Vitest: «document is not defined» | Falta el entorno jsdom | Comprobar `vite.config.ts` (`environment: "jsdom"`) |
| TypeScript falla tras cambiar la API | Tipos desactualizados | Regenerar `openapi.json` y `npm run tipos` |
