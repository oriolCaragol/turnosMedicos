# turnosMedicos — Diseño del modo servidor (red doméstica)

| | |
|---|---|
| Estado | **v1.0 — aprobado** (18/10/2026): todas las decisiones de la sección 15 tomadas |
| Fecha | 2026-10-18 |
| Parte de | v2.12 (`main`) |
| Relacionado | [arquitectura.md](arquitectura.md), [diseno-escritorio.md](diseno-escritorio.md), [mantenimiento.md](mantenimiento.md) |

## 1. Objetivo

Que el núcleo de la aplicación pueda ejecutarse en **un equipo de la red
doméstica** (primero este PC y después una Raspberry Pi) y que se use desde:

- el **navegador** de cualquier ordenador, móvil o tablet de la red;
- las **aplicaciones de escritorio** GNOME (la de WebView y la nativa) de otros
  ordenadores, en «modo cliente».

Lo usarán **el planificador y los médicos**. El planificador edita como ahora.
Los médicos consultan sus turnos y el calendario publicado, ven su ficha y
**proponen cambios** (disponibilidad semanal, ausencias y cambios concretos en
el calendario) que el planificador o el administrador **aprueban o rechazan**.

El modo actual («personal»: todo en un equipo, sin red) **se mantiene**. Es el
mismo programa: cómo se despliega lo decide quien lo instala.

## 2. Decisiones de partida

Tomadas el 18/10/2026:

| # | Pregunta | Respuesta |
|---|---|---|
| R1 | ¿Quién lo usa en red? | El planificador y los médicos |
| R2 | ¿Acceso desde fuera de casa? | De momento no: solo la red doméstica |
| R3 | ¿Qué equipo hace de servidor? | Primero este PC, para probar; después, una Raspberry Pi |
| R4 | ¿Interfaces? | Se conservan las dos: la nativa GNOME en los PC con GNOME y la web en el resto de dispositivos |

## 3. Entorno comprobado (2026-10-18)

| Comprobación | Resultado |
|---|---|
| Ruedas para ARM de 64 bits (Raspberry Pi) | Existen para Python 3.13 y 3.14: ortools 9.15, numpy, pandas, SQLAlchemy, Pydantic, MarkupSafe, protobuf, y también cryptography y zeroconf (necesarias para este diseño). En la Pi no hay que compilar nada |
| Python en la Pi | Raspberry Pi OS actual (Debian 13, 64 bits) trae Python 3.13; el proyecto exige ≥ 3.13 |
| **La Raspberry Pi de referencia** | **Raspberry Pi 3 Model B**: Cortex-A53 a 1,2 GHz (4 núcleos), **1 GB de RAM**, tarjeta SD de 32 GB. Con un sistema antiguo (**Raspbian 10 «buster» de 32 bits**, **Python 3.7**) hay que reinstalar Raspberry Pi OS de 64 bits. Puede compartir la Pi con otros servicios (DNS, web en el puerto 80…): el servidor usa el 8443 |
| Rendimiento | En un PC de sobremesa (i5-13400), generar un mes con 10 médicos tarda **0,12 s** y el proceso usa **146 MB**. En la Pi 3, 10–15 veces más lenta por núcleo, serían **1–2 s**: aceptable. El caso de prueba de 30 médicos (4 s aquí) podría acercarse al minuto |

## 4. Los dos modos

| | Personal (el actual) | Servidor |
|---|---|---|
| Dónde está el núcleo | En el mismo equipo que la interfaz | En un equipo de la red (PC o Raspberry Pi) |
| Quién entra | El usuario de esa cuenta | Planificador y médicos, desde cualquier dispositivo de la red |
| Dónde escucha | 127.0.0.1 | La red local (por ejemplo `https://turnos.local:8443`) |
| Acceso | Token por arranque, invisible | **Usuarios con contraseña** y roles |
| Cifrado | No hace falta (no sale del equipo) | **HTTPS** |
| Datos | `~/.local/share/turnosMedicos` de cada usuario | Uno solo, en el servidor (`/var/lib/turnos` en la Pi) |
| Cómo se arranca | Icono del menú o `turnos` | Servicio del sistema (`turnos servidor`) |
| Clientes | La propia ventana o el navegador local | Navegadores; aplicaciones de escritorio en modo cliente |

```
                       Red doméstica
  ┌──────────────┐   HTTPS + sesión   ┌────────────────────────────────────────┐
  │ Móvil/tablet │ ─────────────────▶ │  Raspberry Pi (o este PC)              │
  │ (navegador)  │ ◀──── eventos ──── │  turnos servidor  (servicio systemd)   │
  └──────────────┘                    │   ├── API + interfaz web               │
  ┌──────────────┐                    │   ├── usuarios, sesiones, eventos      │
  │ PC GNOME     │ ─────────────────▶ │   ├── motor, servicios, datos          │
  │ app nativa o │                    │   └── /var/lib/turnos/turnos.sqlite    │
  │ de escritorio│                    │       + copias diarias                 │
  │ (modo cliente)│                   └────────────────────────────────────────┘
  └──────────────┘                         anunciado como «Turnos médicos» (mDNS)
```

## 5. Lo que ya sirve y lo que cambia

**Ya sirve** (por cómo está hecha la aplicación):

- La **API es la única fuente de verdad**: las tres interfaces ya hablan HTTP con
  el núcleo. Apuntarlas a otro equipo es, sobre todo, cambiar la dirección.
- La **interfaz web se adapta a pantallas estrechas** (lista de días, pestañas
  abajo).
- **Exportar e importar** los datos permite pasar los de este PC al servidor.
- **SQLite** basta para unos pocos usuarios simultáneos con el modo WAL.

**Cambia** (sección por sección más abajo): autenticación y roles (6), cifrado
(7), varios clientes a la vez (8), actualización en vivo (9), el servidor como
servicio (10), los clientes (11) y la instalación en la Pi (12).

## 6. Usuarios, roles, sesiones y solicitudes

### 6.1 Roles

| Rol | Puede |
|---|---|
| **Administrador** | Todo lo del planificador, más gestionar usuarios, ver los dispositivos conectados y cerrar sesiones |
| **Planificador** | Todo lo que se hace hoy: médicos, reglas, cobertura, festivos, generar, retocar, publicar, configuración, exportar e importar |
| **Médico** | **Consultar**: sus turnos (vista «Mis turnos»), el calendario y las urgencias y domicilios de los **meses publicados**, y **su ficha** (disponibilidad semanal, carga, ausencias); descargar e imprimir esos informes. **Proponer** cambios a su disponibilidad semanal y a sus ausencias, y cambios concretos en el calendario publicado (sección 6.4). No modifica nada directamente |

- En el **modo personal no hay usuarios**: quien abre la aplicación es
  administrador, como ahora.
- Una cuenta de médico va **vinculada a su ficha** (`medico_id`), así «Mis
  turnos» sabe quién es.
- La API comprueba el rol en **cada ruta**, no solo la interfaz: un médico no
  puede modificar nada aunque haga peticiones a mano, y solo ve **su** ficha,
  **sus** solicitudes y los meses publicados.

### 6.2 Datos nuevos

| Tabla | Campos |
|---|---|
| `usuario` | id, nombre de usuario, nombre visible, hash de la contraseña, rol, `medico_id` (si es médico), activo, creado |
| `sesion` | hash del token, usuario, dispositivo (texto del navegador o de la aplicación), creada, último uso, caduca |
| `registro_cambio` | quién, cuándo, qué (generar, publicar, cambio manual, reglas, solicitud aprobada…), mes afectado. Con varios usuarios conviene saber quién hizo cada cambio |
| `solicitud` | id, tipo, médico, autor (usuario), estado, propuesta (JSON con el cambio pedido), comentario del médico, quién la resolvió, cuándo, comentario de la resolución, creada (sección 6.4) |

Las contraseñas se guardan con **scrypt** (biblioteca estándar de Python,
`hashlib.scrypt`), nunca en claro.

### 6.3 Inicio de sesión

- La primera vez, el servidor **no tiene usuarios**: se crea el administrador
  desde la terminal del servidor (`turnos servidor crear-administrador`), así
  nadie de la red puede adelantarse.
- El administrador crea las cuentas de los médicos desde la interfaz. Cada cuenta
  recibe una **contraseña temporal o un código QR de invitación** de un solo uso;
  el médico elige su contraseña al entrar la primera vez.
- Al entrar, el servidor crea una **sesión** y la guarda en una cookie
  (`HttpOnly`, `Secure`, `SameSite=Lax`). Las sesiones duran 30 días desde el
  último uso (cómodo en el móvil); el administrador puede cerrarlas.
- Protección: limitar los intentos fallidos (por ejemplo, 5 por minuto y
  usuario) y exigir una cabecera propia en las peticiones que modifican datos,
  que un formulario de otra web no puede enviar (contra CSRF).

### 6.4 Solicitudes de los médicos

Los médicos no cambian nada directamente: **proponen**, y el planificador o el
administrador deciden. Así el planificador mantiene el control del calendario y
los médicos no tienen que pedir los cambios por otras vías (mensajes, papel).

#### Qué se puede proponer

| Tipo | Qué propone el médico | Al aprobarse |
|---|---|---|
| **Disponibilidad semanal** | Su cuadrícula de turnos (Disponible, Habitual, Fijo, «—») y sus preferencias, **desde un mes** | Se guarda una nueva versión de sus reglas desde ese mes (las reglas ya están versionadas por fecha). La carga mensual y las jornadas especiales las sigue decidiendo el planificador |
| **Ausencia** | Una ausencia nueva (desde, hasta, día completo, mañana o tarde, y un comentario), o modificar o anular una existente | Se crea, cambia o borra la ausencia |
| **Cambio en el calendario** | Sobre un mes **publicado** y un turno suyo concreto: «no puedo hacer este turno», «prefiero la otra mitad del día» o «intercambiarlo con otro médico» (eligiendo con quién y qué turno a cambio) | Se aplica como cambio manual (bloqueado), igual que si lo hiciera el planificador |

#### Circuito

```
Médico: propone ──▶ PENDIENTE ──▶ Planificador o administrador: aprueba ──▶ APROBADA (se aplica)
                        │                                 └── rechaza ──▶ RECHAZADA (con motivo)
                        └── el médico la retira ──▶ RETIRADA
```

- El médico ve sus solicitudes y su estado en **«Mis solicitudes»** y puede
  retirar las pendientes.
- El planificador tiene una bandeja **«Solicitudes»** con un contador de
  pendientes en la cabecera, que se actualiza en vivo (sección 9).
- Para cada solicitud, el planificador ve **qué cambia** (la cuadrícula antes y
  después, la ausencia, o el turno del calendario) y **qué efectos tendría**
  aprobarla, calculados con la validación del motor: por ejemplo, «El martes
  3/11 por la mañana faltaría 1 médico» o «Dra. Ruiz quedaría por encima de su
  máximo». Puede aprobar, rechazar con un motivo o, para un cambio en el
  calendario, aplicarlo él mismo de otra forma y marcarla como resuelta.
- **Meses ya generados**: si una disponibilidad o una ausencia aprobada afecta a
  un mes ya generado o publicado, el planificador recibe el aviso «afecta a
  noviembre (publicado): revisa el calendario». No se regenera solo, para no
  cambiar un calendario publicado sin que él lo decida.
- **Mes publicado y cambio concreto**: aprobar un cambio en el calendario lo
  aplica sobre el mes publicado sin reabrirlo (decisión D-S9); queda en el
  registro de cambios y los médicos afectados lo ven en vivo.
- **Intercambios**: el otro médico implicado ve la propuesta y puede aceptarla o
  no antes de que llegue al planificador (decisión D-S8).
- Todas las solicitudes, resueltas o no, quedan como **historial** (quién pidió
  qué, quién lo resolvió y cuándo).

#### API

| Ruta | Quién | Para qué |
|---|---|---|
| `GET /api/yo` | Todos | Usuario, rol y, si es médico, su ficha |
| `GET/POST /api/solicitudes` | Médico: las suyas; planificador: todas | Listar (con filtros de estado) y crear |
| `POST /api/solicitudes/{id}/retirar` | El médico que la creó | Retirar una pendiente |
| `GET /api/solicitudes/{id}/efectos` | Planificador | Qué avisos produciría aprobarla |
| `POST /api/solicitudes/{id}/aprobar`, `/rechazar` | Planificador, administrador | Resolver, con comentario |
| `POST /api/solicitudes/{id}/aceptar` | El otro médico de un intercambio | Aceptar o rechazar su parte |

La lógica va en un servicio nuevo, `servicios/solicitudes.py`, que reutiliza lo
que ya existe para aplicarlas: `guardar_reglas`, las ausencias y
`aplicar_cambios`.

## 7. Cifrado (HTTPS)

Por la red viajarían nombres, turnos y ausencias del equipo: son **datos
personales** y deben ir cifrados. El problema práctico en una red doméstica son
los certificados: sin un dominio público, un certificado autofirmado hace que el
navegador muestre un aviso.

**Propuesta** (decisión D-S1):

1. Al instalar el servidor, la aplicación crea una **autoridad de certificación
   propia** y un certificado para el servidor (con su nombre `turnos.local`, el
   nombre del equipo y sus direcciones IP).
2. La página de inicio de sesión ofrece **descargar el certificado de la
   autoridad** (con instrucciones para Android, iPhone, Windows, macOS y
   Linux). Instalado una vez en cada dispositivo, el navegador ya no avisa.
3. Las **aplicaciones de escritorio** no necesitan instalar nada: la primera vez
   muestran la huella del certificado, el usuario confirma y la recuerdan
   (como hace SSH).
4. Para pruebas, `turnos servidor --sin-https` (solo HTTP) con un aviso claro.

Alternativas descartadas por ahora: certificados de Let's Encrypt (exigen un
dominio y exponerse a internet o gestionar DNS) y solo HTTP (los datos irían en
claro por la red, también la contraseña).

## 8. Varios clientes a la vez

Hoy solo hay un usuario. En red, el planificador puede tener abierta la
aplicación en dos equipos, o dos personas pueden cambiar cosas a la vez.

| Situación | Solución |
|---|---|
| Escrituras simultáneas en SQLite | **Un cerrojo de escritura** en el proceso (las peticiones que escriben van de una en una; las lecturas no esperan) y, **solo en el modo servidor**, el **modo WAL** (en el modo personal se deja el diario clásico: con WAL, copiar a mano solo el `.sqlite` podría dejar fuera los últimos cambios, que viven en el `-wal`) |
| Dos personas cambian el mismo mes | **Versión del mes**: cada cambio la incrementa; los clientes envían la versión que conocen y, si no coincide, el servidor responde 409 con el calendario actual y la interfaz avisa: «Otro usuario ha cambiado el calendario; se muestra la versión actual» |
| Dos «Generar» a la vez del mismo mes | **Bloqueo por mes** mientras se genera; el segundo recibe «Se está generando el calendario» |
| Deshacer tras un cambio de otro usuario | El historial de deshacer de cada cliente se vacía si cambia la versión del mes (no se deshace lo que hizo otro) |
| Dos cambios seguidos desde el mismo cliente | Cada cliente **encola** sus cambios del mes: el segundo sale cuando vuelve el primero, con la versión que este dejó (si no, un clic rápido tras «Regenerar» chocaría consigo mismo) |
| Reglas, cobertura y ajustes | Gana el último que guarda; los demás clientes reciben el aviso del cambio y recargan (sección 9) |

## 9. Actualización en vivo

Si alguien cambia algo, las demás pantallas abiertas deben enterarse sin pulsar
«Recargar».

- El servidor ofrece `GET /api/eventos` con **Server-Sent Events**: una conexión
  abierta por la que envía avisos breves (`{"tipo": "calendario", "anio": 2026,
  "mes": 11, "origen": "…"}`, `{"tipo": "medicos", "origen": "…"}`…), un latido
  cada 15 s y `retry: 3000` para reconectar. Tipos: `calendario`, `medicos`,
  `ausencias`, `festivos`, `cobertura`, `configuracion`, `rotaciones` y `todo`
  (importar una copia). Se publican **después** de confirmar la transacción.
- Cada cliente envía su identificador en la cabecera `X-Cliente`; el evento lo
  devuelve en `origen`, y así cada cliente ignora sus propios cambios.
- Tras una desconexión, el cliente vuelve a pedirlo todo (pudo perder eventos).
- La **interfaz web** los recibe con `EventSource` e invalida las consultas
  afectadas (TanStack Query las vuelve a pedir).
- La **interfaz nativa** los lee en un hilo y marca como pendientes las
  pantallas afectadas; el calendario visible se recarga en el acto (las demás
  pantallas al volver a verlas, para no perder lo que se esté escribiendo).
- Se eligen eventos del servidor en lugar de WebSockets porque solo hace falta
  enviar en un sentido, funcionan con la misma sesión HTTP y FastAPI los admite
  sin dependencias nuevas.

## 10. El servidor

### 10.1 Orden y configuración

```sh
turnos servidor                       # arranca con /etc/turnos/servidor.toml (o ~/.config/turnosMedicos/servidor.toml)
turnos servidor crear-administrador   # primer usuario
turnos servidor certificado           # (re)genera la autoridad y el certificado
turnos servidor copia                 # copia de seguridad inmediata
```

```toml
# servidor.toml
[red]
direccion = "0.0.0.0"     # todas las interfaces de la red local
puerto = 8443
nombre = "turnos"         # se anuncia como turnos.local

[datos]
ruta = "/var/lib/turnos/turnos.sqlite"
copias = "/var/lib/turnos/copias"
conservar_copias = 14      # días

[seguridad]
https = true
duracion_sesion_dias = 30
```

### 10.2 Funciones del servidor

- Sirve la API y la interfaz web compilada. La interfaz pasa a ir **dentro del
  paquete de Python** (hoy se busca en `interfaz/dist`), así el servidor es un
  solo paquete instalable, y de paso se simplifica el Flatpak.
- Se **anuncia en la red** con mDNS (biblioteca `zeroconf`) como «Turnos
  médicos»: las aplicaciones de escritorio lo encuentran solas y los navegadores
  pueden usar `https://turnos.local:8443`.
- Como algunos móviles Android no resuelven los nombres `.local`, la página de
  administración muestra la **dirección IP y un código QR** para abrirla desde el
  móvil sin teclear.
- **Copia de seguridad diaria** automática, conservando las de los últimos 14
  días, además de la copia previa a cada migración que ya existe.
- Página de **administración**: usuarios, dispositivos conectados, copias,
  certificado para descargar y dirección y QR.

## 11. Clientes

### 11.1 Navegador (ordenadores, móviles y tablets)

- **Inicio de sesión** y, según el rol, la interfaz completa (planificador) o la
  de consulta (médico).
- **Para los médicos**, pensado para el móvil:
  - **«Mis turnos»**: sus turnos del mes como lista (fecha, mañana o tarde,
    urgencias o domicilios) y el calendario completo de los meses publicados;
    desde un turno suyo, **«Proponer un cambio»**;
  - **«Mi ficha»**: su disponibilidad semanal, su carga y sus ausencias, con
    **«Proponer cambios»** (la misma cuadrícula, editable sobre una copia) y
    **«Pedir una ausencia»**;
  - **«Mis solicitudes»**: estado de cada una, comentario del planificador,
    retirar las pendientes, y las propuestas de intercambio que le hagan otros.
- **Para el planificador**: la pestaña **«Solicitudes»** con el contador de
  pendientes, el detalle de cada una (antes y después, efectos) y aprobar o
  rechazar.
- **Aplicación web instalable** (PWA): un manifiesto e icono para «Añadir a la
  pantalla de inicio» en el móvil. Sin funcionamiento sin conexión (los datos
  están en el servidor).
- Ajustes para pantallas táctiles en lo que usa el planificador desde una tablet:
  el diálogo del turno ya permite cambiar sin arrastrar.

### 11.2 Aplicaciones de escritorio en modo cliente

Las dos aplicaciones GNOME tienen en *Configuración* (o en su primera pantalla):

- **«Usar este equipo»** (modo personal, como ahora) o **«Conectar a un
  servidor»**: lista los servidores encontrados en la red (mDNS) o deja escribir
  la dirección.
- La primera vez muestran la huella del certificado para confirmarla, piden el
  usuario y la contraseña, y guardan la sesión en el **llavero de GNOME**
  (libsecret), no en un fichero.
- **Escritorio (WebView)**: carga la interfaz web del servidor; el inicio de
  sesión es el de la web.
- **Nativa**: su `ClienteApi` apunta al servidor, con la sesión en una cabecera,
  un diálogo propio de inicio de sesión y la bandeja de **solicitudes** para el
  planificador. Las vistas de los médicos (consulta, ficha, solicitudes) se
  hacen primero en la web, que es la que usarán en el móvil; en la nativa,
  según la decisión D-S10.

En el Flatpak, el modo cliente no necesita permisos nuevos (ya tiene red).

## 12. Instalación en la Raspberry Pi

### 12.1 El sistema de la Pi actual no sirve tal cual

| Problema | Por qué importa |
|---|---|
| **Sistema de 32 bits** (armv7l) | OR-Tools **no publica ruedas para ARM de 32 bits**, y compilarlo en una Pi 3 con 1 GB no es viable. Las ruedas existen para **ARM de 64 bits** (aarch64) |
| **Python 3.7** | La aplicación usa sintaxis de Python 3.12 en adelante y exige ≥ 3.13 |
| **Raspbian 10 «buster»** | Sin actualizaciones de seguridad desde junio de 2024: no conviene para un servidor con datos personales |

La Pi 3 B **sí admite un sistema de 64 bits** (su procesador es ARMv8). Opciones:

| Opción | Qué supone | Valoración |
|---|---|---|
| **A. Reinstalar la Pi con Raspberry Pi OS Lite de 64 bits** (Debian 13) y volver a instalar Pi-hole y Node-RED | Copia de su configuración (Pi-hole: *Teleporter*; Node-RED: los flujos `~/.node-red`), tarjeta nueva o borrada, reinstalar. Unas horas, con el DNS de casa parado mientras tanto (los equipos pueden usar otro DNS ese rato) | **Recomendada**: sistema con soporte, Python 3.13, todo nativo, la opción más sencilla de mantener |
| B. Mantener «buster», activar el núcleo de 64 bits (`arm_64bit=1`) y ejecutar turnos en un **contenedor** de 64 bits | No toca Pi-hole ni Node-RED; añade Docker o Podman sobre un sistema sin soporte | Funciona, pero apila piezas sobre un sistema que ya no recibe parches |
| C. Otro equipo como servidor (un mini PC o una Pi 4/5) | Comprar o reutilizar hardware | Más margen (memoria, velocidad); la Pi 3 seguiría con sus servicios |
| D. Seguir con este PC como servidor | Sin cambios de hardware | Ya está previsto para las pruebas; exige tenerlo encendido |

En todos los casos, el desarrollo y las fases 1 a 3 se hacen con **este PC como
servidor**; la Pi solo afecta a la fase 4.

**Aprovechar Pi-hole**: si la Pi hace de DNS de la casa, se le puede añadir un
nombre local (por ejemplo `turnos.casa → 192.168.1.50`). Así **todos** los
dispositivos encuentran el servidor por nombre, incluidos los Android que no
resuelven `.local`, y ese nombre va también en el certificado.

**Red**: conviene usar el cable (192.168.1.50), reservar esa IP en el router y
anunciar solo esa dirección.

### 12.2 Instalación (con un sistema de 64 bits)

| Aspecto | Propuesta |
|---|---|
| Hardware | La Raspberry Pi 3 B disponible (1 GB) con Raspberry Pi OS Lite de 64 bits (Debian 13); una Pi 4 o 5 daría más margen |
| Instalación | Guion `scripts/instalar-servidor.sh`: crea el usuario de sistema `turnos`, un entorno Python en `/opt/turnos`, instala la rueda de la aplicación, crea `/etc/turnos/servidor.toml`, los datos en `/var/lib/turnos`, el certificado y el servicio `turnos.service` (systemd) con su temporizador de copias |
| Actualizar | Copiar la rueda nueva y `sudo /opt/turnos/actualizar.sh`: instala, reinicia el servicio; las migraciones se aplican solas, con copia previa |
| Datos de este PC | Exportar la copia desde la aplicación actual e importarla en el servidor (ya existe) |
| Alternativa | Un contenedor (Podman o Docker) multiarquitectura, si se prefiere; no es necesario para empezar |

**Por qué no Flatpak en la Pi**: Flatpak está pensado para aplicaciones de
escritorio con ventana; un servicio de red sin pantalla se gestiona mejor con
systemd, sus registros (`journalctl`) y sus reinicios automáticos.

**Rendimiento del motor**: se medirá en la Pi con el caso de 30 médicos. Si
tarda demasiado, opciones: usar los 4 núcleos (CP-SAT en paralelo, perdiendo la
reproducibilidad exacta) o ajustar el tiempo por pasada. Mientras genera, la
interfaz muestra que está trabajando (ya lo hace).

## 13. Seguridad (resumen)

| Riesgo | Medida |
|---|---|
| Alguien de la red ve los datos al pasar | HTTPS con certificado propio |
| Alguien de la red entra sin permiso | Usuarios con contraseña (scrypt), sesiones que caducan, límite de intentos |
| Un médico modifica datos | Roles comprobados en cada ruta de la API |
| Otra web hace peticiones con la sesión del usuario (CSRF) | Cookie `SameSite`, cabecera propia obligatoria en las modificaciones y comprobación del origen |
| Primer arranque aprovechado por otro | El administrador solo se crea desde la terminal del servidor |
| Pérdida de datos | Copias diarias + copia antes de migrar + exportar desde la interfaz |
| Exposición a internet | No se abre ningún puerto en el router (R2). Si más adelante hace falta, mejor una VPN (WireGuard, Tailscale) que exponer el servidor |

## 14. Plan por fases

| Fase | Contenido | Resultado verificable |
|---|---|---|
| 0 | **Probar la v2.12 con usuarios reales** y abrir la rama `estable-2.12` para corregir lo que salga, mientras el modo servidor avanza en `main` | La versión actual en uso; los fallos que aparezcan se corrigen en las dos ramas |
| 1 | **Núcleo multiusuario** (sin cambios visibles en el modo personal): WAL, versión del mes y conflictos, bloqueo al generar, eventos (SSE) en la web y en la nativa, interfaz dentro del paquete, registro de cambios | El modo personal sigue igual; dos ventanas a la vez se avisan y no se pisan. **Hecha** (rama `servidor-fase1`) |
| 2 | **Modo servidor**: orden y configuración, usuarios, roles y sesiones, inicio de sesión, administración, HTTPS con autoridad propia, mDNS, dirección y QR, copias diarias | `turnos servidor` en este PC; se entra desde el móvil y otro ordenador con usuario y contraseña. **Hecha** (rama `servidor-fase2`; ver 14.1) |
| 3 | **Clientes**: «Mis turnos», «Mi ficha» y consulta para médicos en la web, aplicación web instalable, modo cliente en las dos aplicaciones GNOME | Un médico ve sus turnos y su ficha en el móvil; el planificador trabaja desde el PC con la app nativa contra el servidor. **Hecha** (rama `servidor-fase3`; ver 14.2) |
| 4 | **Solicitudes**: proponer disponibilidad, ausencias y cambios en el calendario (también intercambios); bandeja del planificador con antes y después y efectos; aprobar y rechazar; historial; en la web y la bandeja en la nativa | Un médico pide una ausencia desde el móvil y el planificador la aprueba desde el PC; aparece aplicada y el médico ve el estado. **Hecha** (rama `servidor-fase4`; ver 14.3) |
| 5 | **Raspberry Pi**: guion de instalación, servicio y copias, medición del motor, actualización, guía de instalación | El servidor funcionando en la Pi. **Preparada** (rama `servidor-fase5`; ver 14.4): falta reinstalar la Pi y desplegar |
| (opcional) | **Calendario para el móvil (iCal)**: un enlace personal por médico que su aplicación de calendario consulta sola | Los turnos aparecen en el calendario del teléfono |

Cada fase termina con todas las pruebas en verde y el modo personal intacto.

### 14.1 Cómo quedó la fase 2

- `turnos servidor` (`src/turnos/red/`) con `crear-administrador`, `certificado`,
  `copia` y `configuracion`; las bibliotecas nuevas (cryptography, zeroconf,
  segno) van en el extra `turnos[servidor]`, así el Flatpak no cambia.
- Cuentas: en lugar del QR de invitación, **contraseña temporal** de un solo uso
  que el administrador da en persona (más simple y suficiente en casa). Con ella
  solo se puede elegir la contraseña definitiva.
- Permisos: una tabla central en `api/acceso.py`. Lo que no aparece en ella
  queda **cerrado a los médicos**, así una ruta nueva no se abre por descuido.
- CSRF: las peticiones que modifican exigen la cabecera `X-Cliente` (que ya
  enviaban las interfaces por la fase 1) y, si llega, un `Origin` del propio
  servidor; la cookie es `SameSite=Lax`, `HttpOnly` y `Secure`.
- Las aplicaciones podrán usar `Authorization: Bearer` (`aplicacion: true` al
  entrar devuelve el token), para la fase 3.
- Los médicos, de momento, ven solo un saludo: sus pantallas son la fase 3.
- Importar una copia en el servidor **conserva las cuentas** (las cuentas de
  médico se vuelven a vincular por el código del médico) y las copias que se
  descargan no llevan las sesiones.
- Arreglos que salieron al probar con WAL (fase 2): las copias de seguridad salían con la
  marca WAL (dependían de un segundo fichero) y la importación no sustituía los
  datos; ahora las copias son un único fichero completo.

### 14.2 Cómo quedó la fase 3

- Web para médicos (`interfaz/src/medico/`): «Mis turnos», «Calendario» del equipo
  día a día y «Mi ficha» de solo lectura, con el mes elegido entre los publicados
  (`GET /api/periodos/publicados`). Las reglas que se muestran son las del mes
  elegido. Aplicación instalable: manifiesto e iconos, sin modo sin conexión.
- Aplicaciones de escritorio (`arranque/conexion.py`, `dialogos.py`, `llavero.py`):
  la elección se guarda en `~/.config/turnosMedicos/conexion.json` y la autoridad
  confirmada al lado; cambiar de conexión vuelve a abrir la aplicación.
- La de escritorio (WebView) usa una sesión de WebKit **persistente** en el modo
  servidor (la cookie de la web se recuerda), en lugar del llavero. Acepta el
  certificado del servidor solo si lo firma la autoridad confirmada, **antes** de
  cargar (si no, una página servida desde la caché fallaba en sus peticiones).
- La nativa usa `Authorization: Bearer` con la sesión del llavero; si el servidor
  responde 401, vuelve a pedir la contraseña.
- **Dentro de Flatpak los nombres `.local` no se resuelven** (el runtime no trae
  mDNS): `conexion.resolver` los resuelve con zeroconf y usa la IP, que también
  está en el certificado. Por eso el Flatpak incluye `zeroconf` (extra `cliente`).

### 14.3 Cómo quedó la fase 4

- Tabla `solicitud` (migración 0008) y `servicios/solicitudes.py`: crear (con
  validación), describir en frases (las usan la web y la nativa), efectos,
  aprobar (o «resuelta de otra forma»), rechazar, retirar y la respuesta del
  compañero en un intercambio.
- **Efectos**: se aplica la solicitud dentro de un punto de guardado de la
  transacción, se leen los avisos de los meses afectados y se deshace; se
  muestran solo los avisos nuevos y los meses ya generados que hay que revisar.
- Aprobar un cambio de calendario usa `aplicar_cambios(..., en_publicado=True)`
  (D-S9) y sube la versión del mes. Una ruta puede publicar varios eventos
  (`request.state.eventos`): aprobar avisa de «solicitudes» y de lo que cambia
  (calendario, médicos o ausencias), también a quien aprueba.
- Disponibilidad: se guarda una versión nueva de las reglas desde el mes pedido
  conservando la carga y las jornadas (D-S11). Si había una versión posterior,
  sigue valiendo desde su fecha.

### 14.4 Cómo quedó la fase 5

- `empaquetado/raspberry/`: `instalar.sh` (instala o actualiza: usuario de
  sistema, entorno en `/opt/turnos` con el extra `servidor`, configuración en
  `/etc/turnos`, servicio systemd con protección `ProtectSystem=strict` y datos en
  `StateDirectory`), `turnos.service` y `servidor.toml`.
- `scripts/desplegar-raspberry.sh usuario@pi`: construye la rueda en el PC, la
  copia por SSH y ejecuta el instalador.
- `turnos servidor medir`: cuánto tarda el motor en ese equipo, con una copia de
  los datos.
- `scripts/probar-raspberry-contenedor.sh`: la instalación completa en un Debian
  13 arm64 emulado (podman + qemu): ruedas de aarch64, instalador, arranque como
  `turnos` con HTTPS, entrada y medición. No sustituye a la prueba en la Pi
  (rendimiento real, mDNS junto a avahi, convivencia con Pi-hole y Node-RED).
- Guía paso a paso: [instalacion-raspberry.md](instalacion-raspberry.md),
  incluido cómo llevar la autoridad del PC a la Pi para no reinstalarla en los
  dispositivos.

**Pruebas nuevas**: inicio de sesión, roles por ruta, sesiones y su caducidad;
dos clientes que se pisan (versión del mes, 409); eventos; solicitudes (cada
tipo, su circuito, que un médico no vea ni resuelva las de otros, que aprobar
aplique el cambio y sus efectos); Playwright con un planificador y un médico
(también en tamaño de móvil); modo cliente de la
interfaz nativa contra un servidor de prueba. La Pi se probará a mano (no se
puede emular con fiabilidad en las pruebas automáticas).

## 15. Decisiones (todas tomadas el 18/10/2026)

| # | Pregunta | Propuesta |
|---|---|---|
| D-S1 | ¿Cómo cifrar? | **Decidido (18/10/2026): autoridad de certificación propia**, con restricciones de nombre (solo el servidor de turnos y la red local), certificado del servidor renovado cada año y perfil de configuración para iPhone. Si instalarlo resulta engorroso para los médicos, se puede pasar a un dominio propio con Let's Encrypt sin cambiar el resto |
| D-S2 | ¿Qué ven los médicos? | **Decidido**: los **meses publicados** (no los borradores) con el calendario de todo el equipo, sus turnos, y **su ficha** (disponibilidad semanal, carga y ausencias) |
| D-S3 | ¿Cuentas individuales o un código compartido para los médicos? | **Decidido: individuales**, vinculadas a su ficha |
| D-S4 | ¿Los médicos pueden pedir algo? | **Decidido: sí, por solicitudes** que aprueba el planificador o el administrador: disponibilidad semanal, ausencias y cambios concretos en el calendario (sección 6.4) |
| D-S5 | ¿Calendario iCal para el móvil? | **Decidido**: sí, como fase opcional al final |
| D-S6 | ¿Qué Raspberry Pi y qué sistema? | **Decidido: opción A**. La disponible es una Pi 3 B con Raspbian 10 de 32 bits, que no sirve tal cual (sección 12.1): se reinstalará con Raspberry Pi OS Lite de 64 bits, volviendo a instalar Pi-hole y Node-RED, cuando llegue la fase 5. Hasta entonces, el servidor es este PC |
| D-S7 | ¿El planificador puede seguir usando el modo personal en su PC? | **Decidido**: sí, pero **no a la vez que el servidor con los mismos datos**: al pasar al servidor, los datos se importan allí y su aplicación se conecta como cliente |
| D-S8 | En un intercambio de turnos, ¿el otro médico debe aceptarlo antes de que llegue al planificador? | **Decidido**: sí: así el planificador solo ve intercambios ya acordados |
| D-S9 | ¿Aprobar un cambio en un mes publicado exige reabrirlo? | **Decidido**: no: se aplica sobre el mes publicado, queda en el registro de cambios y los afectados lo ven en vivo |
| D-S10 | ¿Las vistas de los médicos también en la interfaz nativa? | **Decidido**: primero en la web (la que usarán en el móvil); en la nativa, la bandeja de solicitudes del planificador. Las vistas de médico en la nativa, más adelante si se piden |
| D-S11 | ¿El médico puede proponer cambios en su carga mensual o en sus jornadas especiales? | **Decidido**: no: las decide el planificador. Puede explicarlo en el comentario de una solicitud |
| D-S12 | ¿Avisos fuera de la aplicación (correo, notificaciones del móvil)? | **Decidido**: no por ahora: el contador y las listas se actualizan en vivo dentro de la aplicación. Las notificaciones del móvil (Web Push) exigirían certificado reconocido y se pueden estudiar después |
