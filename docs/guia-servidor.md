# Turnos médicos en la red de casa — Guía del administrador

Cómo poner en marcha el **modo servidor**: el núcleo corre en un equipo de la red
doméstica (de momento este PC; más adelante la Raspberry Pi) y se entra desde el
navegador de cualquier ordenador, móvil o tableta de la casa, con usuario y
contraseña. El diseño completo está en [diseno-servidor.md](diseno-servidor.md).

> Estado: fase 4. Los médicos consultan sus turnos, el calendario y su ficha, y
> proponen cambios que el planificador aprueba (sección 11). Las dos aplicaciones
> de escritorio pueden trabajar contra el servidor (sección 10).

## 1. Instalar

En el equipo que hará de servidor, con el entorno del proyecto:

```sh
.venv/bin/pip install -e '.[servidor]'    # añade cryptography, zeroconf y segno
```

## 2. Primera vez

```sh
turnos servidor crear-administrador        # pide usuario, nombre y contraseña (dos veces)
turnos servidor                            # arranca; Ctrl+C para pararlo
```

Al arrancar muestra algo así:

```
Turnos médicos (HTTPS)
  Datos: ~/.local/share/turnosMedicos/servidor/turnos.sqlite
  https://turnos.local:8443/
  https://192.168.1.50:8443/
  Huella de la autoridad: 1B:7D:54:…
  Ctrl+C para parar.
```

- Los **datos del servidor van aparte** de los del modo personal
  (`~/.local/share/turnosMedicos/servidor/`): los dos modos no deben usar los
  mismos datos a la vez. Para llevar al servidor lo que ya tienes, exporta una
  copia en el modo personal (*Configuración › Datos*) e impórtala en el servidor
  con la misma opción. Las cuentas del servidor se conservan al importar.
- El administrador **solo se crea desde la terminal** del servidor: así nadie de
  la red puede adelantarse.
- Fedora Workstation ya permite en la red local los puertos altos y mDNS, así que
  no hace falta tocar el cortafuegos. En otros sistemas, abre el puerto 8443/tcp.

## 3. Configuración (opcional)

Sin fichero de configuración se usan los valores por defecto. Para cambiarlos:

```sh
turnos servidor configuracion > ~/.config/turnosMedicos/servidor.toml
```

Se busca primero en `/etc/turnos/servidor.toml` y después en
`~/.config/turnosMedicos/servidor.toml`. Se puede indicar otro con `--config`.
Opciones útiles: `--datos RUTA`, `--puerto N`, `--sin-anuncio` (sin mDNS) y
`--sin-https` (**solo para pruebas**: datos y contraseñas irían sin cifrar).

## 4. Entrar desde otro dispositivo

1. Abre `https://turnos.local:8443/` en el navegador. Algunos Android no
   resuelven los nombres `.local`: usa entonces la dirección con números, o
   escanea su código QR en *Administración › Servidor*.
2. La primera vez el navegador avisará de que la conexión no es segura: el
   servidor usa un **certificado propio**. En la página de entrada, el apartado
   «¿El navegador avisa…?» explica cómo instalarlo en iPhone, Android, Windows,
   Mac y Linux. Se hace **una vez por dispositivo**.
   - En el **iPhone**: descarga el perfil desde Safari, instálalo en *Ajustes ›
     General › VPN y gestión de dispositivos* y **activa la confianza** en
     *Ajustes › General › Información › Ajustes de confianza de certificados*.
   - Para comprobar que el certificado es el tuyo, compara la **huella** con la
     que muestra el servidor al arrancar o *Administración › Servidor*.
3. Entra con tu usuario y contraseña.

El certificado sirve solo para nombres `.local` y direcciones de la red de casa:
aunque alguien se hiciera con él, no le serviría para suplantar ninguna web de
internet.

## 5. Cuentas

En la pestaña **Administración** (solo la ve el administrador):

- **Cuenta nueva**: elige el rol (*Médico*, *Planificador* o *Administrador*) y,
  para un médico, **su ficha**. Se muestra una **contraseña temporal**, una sola
  vez: dásela en persona. Al entrar, elegirá la suya (8 caracteres o más).
- **Nueva contraseña**: para quien la ha olvidado. Da otra temporal y cierra sus
  sesiones.
- **Editar**: cambiar el nombre, el rol, la ficha vinculada o desactivar la
  cuenta (se cierran sus sesiones). Siempre queda al menos un administrador.

| Rol | Puede |
|---|---|
| Administrador | Todo, más cuentas, dispositivos y servidor |
| Planificador | Todo lo de siempre: médicos, reglas, cobertura, festivos, calendarios, configuración, exportar e importar |
| Médico | Consultar los meses **publicados** («Mis turnos» y «Calendario», con el mismo formato que el del planificador y su nombre resaltado; también para imprimir o guardar como PDF) y su propia ficha («Mi ficha»). No cambia nada directamente: **propone** cambios (sección 11) |

Cada persona puede cambiar su contraseña con **Contraseña**, en la cabecera.

## 6. Dispositivos conectados

*Administración › Dispositivos conectados* lista cada sesión abierta (persona,
dispositivo, desde cuándo y último uso). Una sesión dura **30 días desde su
último uso**. Cierra la de un móvil perdido o que ya no se usa.

Tras **5 intentos fallidos en un minuto** con el mismo usuario, hay que esperar
un minuto.

## 7. Copias de seguridad

- **Cada día**, automáticamente, en `…/servidor/copias/turnos-AAAAMMDD.sqlite`.
  Se conservan las de los últimos 14 días.
- **A mano**: *Administración › Hacer una copia ahora*, o
  `turnos servidor copia` desde la terminal.
- Además, como siempre, se guarda una copia antes de cada actualización y antes
  de importar.

Para restaurar una copia: *Configuración › Datos › Importar una copia*.

## 8. Certificado

- El del servidor dura **un año** y se renueva solo un mes antes (también si el
  equipo cambia de dirección IP), sin reiniciar.
- La **autoridad**, que es lo que se instala en los dispositivos, dura 10 años.
- `turnos servidor certificado` muestra dónde están y su huella;
  `--nueva-autoridad` crea otra (habría que volver a instalarla en todos los
  dispositivos: solo si se ha visto comprometida).

## 9. En el móvil, como una aplicación

La web se puede **instalar** en la pantalla de inicio:

- **iPhone** (Safari): botón Compartir › «Añadir a pantalla de inicio».
- **Android** (Chrome): menú ⋮ › «Instalar aplicación» o «Añadir a pantalla de inicio».

Se abre a pantalla completa, con su icono. Necesita estar en la red de casa (los
datos están en el servidor).

## 10. Las aplicaciones de escritorio contra el servidor

Las dos aplicaciones GNOME («Turnos médicos» y la nativa) pueden trabajar con los
datos del servidor en lugar de con los de este equipo:

1. **Al abrir la aplicación**, la pantalla «¿Dónde quieres trabajar?» ofrece
   «En este equipo» (datos y motor incluidos, como siempre) o un servidor: los
   anunciados en la red, el último usado u otra dirección. Con «Recordar mi
   elección» no vuelve a preguntar; se cambia en el menú › **Conexión…**, que
   tiene también la opción «Preguntar al abrir la aplicación».
2. La primera vez se muestra la **huella** del certificado: compárala con la que
   enseña el servidor al arrancar (o *Administración › Servidor*) y pulsa
   «Coincide: confiar». No hace falta instalar nada más.
3. La aplicación queda conectada al servidor:
   - la de **escritorio** muestra la web del servidor, con su página de entrada;
     la sesión se recuerda;
   - la **nativa** pide usuario y contraseña y guarda la sesión en el **llavero
     de GNOME**. Es para el planificador y el administrador: un médico verá un
     enlace a la web.
4. Para volver a los datos de este equipo: elígelo al abrir, o **Conexión…** ›
   «Este equipo».

Si el servidor no responde, la ventana lo dice y ofrece «Reintentar» o «Cambiar
la conexión…». En la nativa, el menú tiene además «Salir de la sesión».

## 11. Solicitudes de los médicos

Los médicos no cambian nada directamente: **proponen**, y el planificador (o el
administrador) decide.

**Qué puede proponer un médico** (desde el móvil):

| Dónde | Qué |
|---|---|
| *Mis turnos* › un turno › **Proponer un cambio** | «No puedo hacer este turno», «Prefiero la otra mitad del día» o **intercambiarlo** con un compañero (eligiendo su turno). Solo en meses publicados |
| *Mi ficha* › **Proponer otra disponibilidad** | Su cuadrícula semanal, desde un mes. La carga y las jornadas las sigue decidiendo el planificador |
| *Mi ficha* › **Pedir una ausencia** / **Pedir anularla** | Una ausencia nueva (días, día completo o solo mañana o tarde), o anular una existente |

En **Solicitudes** ve el estado de cada una y el comentario del planificador, y
puede retirar las pendientes. Un **intercambio** llega primero al compañero, que
lo acepta o no; solo si lo acepta pasa al planificador.

**El planificador** tiene la pestaña **Solicitudes** con el número de pendientes
(también en la aplicación nativa conectada al servidor). Para cada una ve qué
cambia y **qué pasaría al aprobarla** (por ejemplo, «El martes 3/11 por la mañana
falta 1 médico», o «Afecta a noviembre (publicado): revisa el calendario»), y
puede:

- **Aprobar**: se aplica en el momento. En un mes publicado, sin reabrirlo; queda
  en el registro de cambios y los afectados lo ven en vivo.
- **Rechazar**, con el motivo en el comentario.
- **Resuelta de otra forma** (cambios en el calendario): si lo arregla él mismo de
  otra manera.

Un mes ya generado **no se regenera solo** al aprobar una disponibilidad o una
ausencia: el aviso indica qué mes revisar.

## 12. Problemas frecuentes

| Problema | Solución |
|---|---|
| El móvil no abre `turnos.local` | Usa la dirección con números o el QR de *Administración* |
| El navegador avisa de conexión no segura | Instala el certificado (sección 4); en el iPhone, activa además la confianza |
| «Aún no hay usuarios» al arrancar | `turnos servidor crear-administrador` |
| «Demasiados intentos» | Espera un minuto |
| Alguien olvidó la contraseña | *Administración › Nueva contraseña* |
| No se anuncia en la red | Falta `zeroconf` (`pip install -e '.[servidor]'`); se puede entrar por la IP |
| La aplicación de escritorio dice que el certificado no es el confirmado | El servidor ha creado otra autoridad (`--nueva-autoridad`) o es otro equipo: vuelve a elegir la conexión y comprueba la huella |
