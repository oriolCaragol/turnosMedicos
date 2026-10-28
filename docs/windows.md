# Turnos médicos en Windows

La versión de Windows es `TurnosMedicos.exe`: el mismo núcleo y la misma base de
datos que en Linux, con la interfaz web en el navegador predeterminado. No hace
falta instalar Python ni nada más.

## Instalar

1. Descarga `turnos-medicos-<versión>-windows.zip`, de la página de versiones
   publicadas (*Releases*) del proyecto en GitHub o de quien te lo pase.
2. Descomprímelo donde quieras, por ejemplo en `Documentos` o en `C:\Programas`.
   Queda una carpeta `TurnosMedicos`.
3. Abre `TurnosMedicos\TurnosMedicos.exe`. Para tenerlo a mano: botón derecho ›
   *Mostrar más opciones* › *Enviar a* › *Escritorio (crear acceso directo)*.

La primera vez, Windows puede avisar de que es una aplicación de un editor
desconocido (*Windows protegió su PC*): pulsa *Más información* › *Ejecutar de
todas formas*. Ocurre con cualquier programa que no esté firmado con un
certificado de pago.

## Usar

Al abrirlo, una ventana pequeña pregunta **dónde trabajar**:

- **En este equipo**: arranca el motor con los datos de este ordenador y abre la
  aplicación en el navegador. La ventana pequeña se queda abierta: sirve para
  volver a abrir el navegador o para **cerrar Turnos médicos** (al cerrarla se
  cierra la aplicación). Si la abres otra vez mientras está en marcha, solo se
  abre el navegador.
- **En un servidor de la red** (`turnos servidor` en un PC o una Raspberry Pi de
  casa, ver [guia-servidor.md](guia-servidor.md)): elige uno de los encontrados
  en la red o escribe su dirección; se abre en el navegador. La primera vez,
  instala en Windows el certificado del servidor, como explica su página de
  entrada.

Con **«Recordar mi elección y no volver a preguntar»** se abre directamente; para
volver a elegir, «Cambiar dónde trabajar…» en la ventana pequeña.

Todo lo demás es igual que en la [guía de uso](guia-de-uso.md).

## Dónde están los datos

| Qué | Dónde |
|---|---|
| Datos (base de datos y copias previas a cada actualización) | `%LOCALAPPDATA%\TurnosMedicos\` (`turnos.sqlite`) |
| Dónde trabajar (lo recordado) | `%APPDATA%\TurnosMedicos\conexion.json` |
| Registro (para diagnosticar problemas) | `%LOCALAPPDATA%\TurnosMedicos\registro.txt` |

Para llevar los datos a otro equipo (o desde Linux): *Configuración › Datos ›
Exportar copia de los datos* en uno e *Importar una copia* en el otro.

Para actualizar a una versión nueva, sustituye la carpeta `TurnosMedicos` por la
nueva: los datos no están dentro y se actualizan solos al abrirla (con una copia
previa).

## Construir el ejecutable

PyInstaller solo genera ejecutables de Windows desde Windows. Hay dos formas:

- **En GitHub** (la recomendada): el flujo `.github/workflows/windows.yml` lo
  construye en un Windows de verdad, lo prueba y guarda el zip como artefacto. Al
  subir una etiqueta (`git tag v2.17.0 && git push --tags`), además lo adjunta a
  la versión publicada. También se puede lanzar a mano desde la pestaña
  *Actions*.
- **Desde Linux**, con Wine dentro de un contenedor (podman):

  ```sh
  scripts/construir-windows.sh      # → build/turnos-medicos-<versión>-windows.zip
  ```

  La primera vez prepara la imagen (Debian, Wine y el Python oficial de Windows
  de python.org, con su suma SHA-256 comprobada; unos minutos) y descarga las
  dependencias, que quedan en caché (volumen `turnos-windows-pip`).

Las dos ejecutan la **autoprueba** del ejecutable, `TurnosMedicos.exe --prueba
FICHERO`: arranca el servidor interno con datos temporales, comprueba la
interfaz y la API y genera un mes con el motor; escribe `BIEN` o el error.

Piezas: `src/turnos/arranque/windows/` (lanzador Tkinter y autoprueba),
`empaquetado/windows/turnos-medicos.spec` (PyInstaller: OR-Tools entero, la
interfaz web, los recursos y las migraciones de Alembic como ficheros),
`empaquetado/windows/Containerfile` y `turnos.ico`.
