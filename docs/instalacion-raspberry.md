# Turnos médicos en la Raspberry Pi — Guía de instalación

Cómo dejar el servidor de turnos funcionando de forma permanente en una Raspberry
Pi de casa, también si ya tiene otros servicios, como Pi-hole o Node-RED (diseño
del modo servidor, 12; decisión D-S6). Para el uso diario del servidor (cuentas, certificado en los
dispositivos, solicitudes…), ver [guia-servidor.md](guia-servidor.md).

| | |
|---|---|
| Equipo | Raspberry Pi 3 Model B (1 GB) o posterior |
| Sistema | **Raspberry Pi OS Lite de 64 bits** (Debian 13), instalado desde cero |
| Dónde queda | Servicio `turnos` (systemd), datos en `/var/lib/turnos`, configuración en `/etc/turnos` |
| Dirección | `https://turnos.local:8443/` o `https://192.168.1.50:8443/` |

## 1. Por qué hay que reinstalar

Si la Pi tiene un sistema de **32 bits** (por ejemplo Raspbian 10, con Python
3.7), hay que reinstalarla. Si ya tiene Raspberry Pi OS de 64 bits (Debian 13),
pasa directamente a la sección 5. El motor de turnos
(OR-Tools) no existe para 32 bits, y ese sistema ya no recibe actualizaciones.
Con Raspberry Pi OS de **64 bits** hay versiones oficiales de todo lo que usa la
aplicación. La placa sirve: la Pi 3 B ya es de 64 bits.

En 1 GB de memoria cabe junto a otros servicios ligeros. El servidor de turnos usa unos 200 MB
mientras genera un mes y menos en reposo.

## 2. Antes de reinstalar: guardar lo que hay

Haz esto **antes** de tocar la tarjeta (los pasos 1 y 2, solo si los tienes):

1. **Pi-hole**: en su página de administración, *Settings › Teleporter ›
   Export*. Guarda el fichero en el PC.
2. **Node-RED**: desde el PC,
   ```sh
   ssh usuario@192.168.1.50 'tar czf - .node-red' > node-red-copia.tgz
   ```
3. Anota la **dirección fija** de la Pi (`192.168.1.50`) y la puerta de enlace
   del router (normalmente `192.168.1.1`): Pi-hole necesita la misma dirección.
4. Si es posible, usa **otra tarjeta microSD** (16 GB o más): si algo sale mal,
   basta con volver a poner la antigua.

## 3. Instalar Raspberry Pi OS Lite de 64 bits

Con **Raspberry Pi Imager** en el PC (`flatpak install flathub org.raspberrypi.rpi-imager`):

1. Dispositivo: *Raspberry Pi 3*. Sistema: *Raspberry Pi OS (other) › Raspberry
   Pi OS Lite (64-bit)*.
2. En *Editar ajustes*: el mismo **nombre de equipo** que tenía, un usuario y
   contraseña, zona horaria *Europe/Madrid*, teclado *es*. En *Servicios*,
   **activar SSH** (mejor con la clave pública del PC).
3. Graba la tarjeta, ponla en la Pi y enciéndela (con cable de red).

Después, desde el PC:

```sh
ssh usuario@nombre-de-la-pi.local        # o por la IP que le haya dado el router
sudo apt update && sudo apt full-upgrade -y
# Dirección fija (la que tenía), con NetworkManager:
sudo nmcli con mod "Wired connection 1" ipv4.method manual \
  ipv4.addresses 192.168.1.50/24 ipv4.gateway 192.168.1.1 ipv4.dns 192.168.1.1
sudo nmcli con up "Wired connection 1"   # se corta la sesión: vuelve a entrar por 192.168.1.50
```

## 4. Volver a poner Pi-hole y Node-RED (si los tenías)

Sigue sus instaladores oficiales (comprueba en sus webs que siguen siendo estos):

```sh
curl -sSL https://install.pi-hole.net | bash          # Pi-hole
# Después, en su página: Settings › Teleporter › Import (el fichero del paso 2)

bash <(curl -sL https://github.com/node-red/linux-installers/releases/latest/download/update-nodejs-and-nodered-deb)
tar xzf node-red-copia.tgz -C ~                      # tras copiarlo a la Pi con scp
sudo systemctl enable --now nodered
```

Comprueba que los dos funcionan como antes antes de seguir.

## 5. Instalar el servidor de turnos

Desde el PC, en la carpeta del proyecto:

```sh
scripts/desplegar-raspberry.sh usuario@192.168.1.50
```

Construye la aplicación (con la interfaz web dentro), la copia a la Pi y ejecuta
allí `empaquetado/raspberry/instalar.sh`, que:

- crea el usuario de sistema `turnos` (sin acceso a la consola);
- instala la aplicación en `/opt/turnos` (la primera vez descarga unos 150 MB);
- copia la configuración a `/etc/turnos/servidor.toml`;
- instala y arranca el servicio `turnos`, que se arranca solo al encender.

Pedirá la contraseña del usuario de la Pi (para `sudo`). Después, **una sola
vez**, crea el administrador:

```sh
ssh -t usuario@192.168.1.50 sudo -u turnos /opt/turnos/bin/turnos servidor crear-administrador \
  --config /etc/turnos/servidor.toml
```

### 5.1 Conservar el certificado de las pruebas en el PC (recomendado)

Si ya has usado el servidor en el PC e instalado su certificado en los móviles,
puedes llevar **la misma autoridad** a la Pi: así nadie tiene que volver a
instalar nada. La autoridad vale para cualquier nombre `.local` y cualquier
dirección de la red de casa, así que sirve igual para la Pi. Hazlo **antes del
primer arranque**, o para el servicio un momento:

```sh
scp ~/.local/share/turnosMedicos/servidor/certificados/autoridad.* usuario@192.168.1.50:/tmp/
ssh -t usuario@192.168.1.50 '
  sudo systemctl stop turnos
  sudo install -d -o turnos -g turnos -m 0700 /var/lib/turnos/certificados
  sudo install -o turnos -g turnos -m 0600 /tmp/autoridad.key /var/lib/turnos/certificados/
  sudo install -o turnos -g turnos -m 0644 /tmp/autoridad.crt /var/lib/turnos/certificados/
  sudo rm -f /var/lib/turnos/certificados/servidor.* /tmp/autoridad.*
  sudo systemctl start turnos'
```

El certificado del servidor se crea solo, con los nombres y direcciones de la Pi.
Las aplicaciones de escritorio: *Conexión…* › elige la Pi; la huella será la
misma.

Si no lo haces, la Pi crea su propia autoridad: habrá que instalarla en cada
dispositivo (guia-servidor.md, 4) y volver a elegir la conexión en las
aplicaciones de escritorio.

## 6. Comprobar y medir

```sh
ssh usuario@192.168.1.50
systemctl status turnos                    # «active (running)»
journalctl -u turnos -f                    # lo que dice el servidor (direcciones, huella…)
sudo -u turnos /opt/turnos/bin/turnos servidor medir --config /etc/turnos/servidor.toml
```

`medir` genera un mes con una **copia** de los datos (o con un equipo de ejemplo
si aún no hay) y dice cuánto tarda y cuánta memoria usa. En el PC de desarrollo
(i5-13400), con 10 médicos, tarda 0,16 s; en la Pi 3 se espera bastante más,
pero muy por debajo del minuto.

Abre `https://turnos.local:8443/` desde el PC y el móvil.

## 7. Pasar los datos

En la aplicación de siempre (modo personal) o en el servidor del PC:
*Configuración › Datos › Exportar copia de los datos*. Después, en la web de la
Pi como administrador: *Configuración › Datos › Importar una copia*. Las cuentas
de la Pi se conservan.

Desde entonces, trabaja **solo contra la Pi** (D-S7): en las aplicaciones de
escritorio, *Conexión…* › la Pi.

## 8. Actualizar

Con una versión nueva de la aplicación, desde el PC:

```sh
scripts/desplegar-raspberry.sh usuario@192.168.1.50
```

Se instala encima, se reinicia el servicio y, si cambia la base de datos, se migra
al arrancar (con una copia previa). La configuración y los datos no se tocan.

El sistema de la Pi: `sudo apt update && sudo apt full-upgrade` de vez en cuando.

## 9. Copias de seguridad

- La Pi hace **una copia al día** en `/var/lib/turnos/copias` y guarda 14 días.
- Pero está en la **misma tarjeta**: si la tarjeta falla, se pierden también.
  Guarda una copia fuera de la Pi con frecuencia, por ejemplo cada semana:
  *Configuración › Datos › Exportar copia de los datos* desde el PC, y guárdala
  en otro sitio (la nube, un disco…).
- Con un pendrive en la Pi, se pueden dejar ahí las copias diarias: móntalo de
  forma fija, cambia `copias = "/ruta/del/pendrive/turnos"` en
  `/etc/turnos/servidor.toml`, añade esa ruta a `ReadWritePaths=` del servicio
  (`sudo systemctl edit turnos`) y reinicia.

## 10. Problemas frecuentes

| Problema | Solución |
|---|---|
| `instalar.sh` dice «sistema de 32 bits» | El sistema instalado no es el de 64 bits: repite el paso 3 eligiendo *Lite (64-bit)* |
| `systemctl status turnos` muestra un error | `journalctl -u turnos -n 50` dice la causa (configuración, puerto ocupado…) |
| `turnos.local` no responde | Prueba con `https://192.168.1.50:8443/`. Si así funciona, es el nombre: algunos Android no resuelven `.local`; usa la IP o el QR de *Administración* |
| El navegador avisa del certificado | El dispositivo no tiene la autoridad de la Pi: guia-servidor.md, 4 (o paso 5.1) |
| La Pi va lenta | `free -h` y `top`: Pi-hole y Node-RED también usan memoria. El servidor de turnos usa unos 200 MB al generar |
| Desinstalar | `sudo systemctl disable --now turnos && sudo rm -r /opt/turnos /etc/systemd/system/turnos.service /etc/turnos` (los datos siguen en `/var/lib/turnos`) |
