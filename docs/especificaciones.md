# turnosMedicos — Especificaciones

| | |
|---|---|
| Estado | v1.0 — todas las preguntas cerradas; pendiente de aprobación para pasar al diseño |
| Última actualización | 2026-10-14 |

Los valores que el planificador puede cambiar están resumidos en la
[sección 9](#9-parámetros-configurables). Las decisiones tomadas durante la
redacción están en la [sección 10](#10-registro-de-decisiones).

---

## 1. Objetivo

Construir una herramienta que asigne automáticamente los turnos de días
laborables (mañana y tarde) a un equipo de médicos, de forma que todos los
turnos de un periodo de planificación queden cubiertos respetando las reglas
definidas para cada médico.

La persona que usa la herramienta (el **planificador** o administrador, p. ej.
el jefe de servicio) define una vez los médicos y sus reglas, y después pide a la
herramienta que genere el calendario de un periodo. Puede revisar y ajustar el
resultado antes de publicarlo.

## 2. Alcance

### Incluido (primera versión)

- Gestión de la lista de médicos.
- Definición, por médico, de qué turnos puede/debe hacer.
- Definición de cuántos médicos necesita cada turno.
- Registro de festivos y ausencias de médicos (vacaciones, permisos, cursos).
- Exportar e importar todos los datos (copia completa), por ejemplo para
  llevarlos a otro ordenador o a otro usuario.
- Generación automática del calendario de un periodo de planificación.
- Revisión, ajuste manual y bloqueo de asignaciones.
- Visualización y exportación del calendario resultante.

### Excluido (por ahora)

- Turnos de fin de semana y guardias / turnos de noche.
- Solicitudes de cambio de turno hechas por los propios médicos.
- Nóminas y cómputo de horas a efectos salariales.
- Notificaciones (correo, SMS).
- Varios servicios/equipos en la misma instalación.
- Patrones alternos (p. ej. mañanas en semanas pares, tardes en impares).
- Varios usuarios, inicio de sesión y roles.
- Exportación a iCal.
- Idiomas de la interfaz distintos del castellano.

## 3. Glosario

| Término | Significado |
|---|---|
| **Día laborable** | De lunes a viernes, excluyendo festivos. |
| **Tipo de turno** | `MAÑANA` o `TARDE`. |
| **Hueco** | Un turno concreto en una fecha concreta, p. ej. *mar 2026-11-03, MAÑANA*. |
| **Jornada** | Lo que trabaja un médico en un día: 1, 1,5 o 2 turnos (ver 5.3). |
| **Medio turno** | La mitad de un turno; unidad mínima de asignación (ver 5.3). |
| **Hueco semanal** | Un día de la semana + tipo de turno, p. ej. *martes MAÑANA*. Se usa para definir reglas que se repiten cada semana. |
| **Asignación** | Un médico colocado en un hueco. |
| **Periodo de planificación** | El rango de fechas que se planifica (p. ej. un mes). |
| **Requisito de cobertura** | Cuántos médicos necesita un hueco. |
| **Regla estricta** | Debe cumplirse siempre; un calendario que la incumple no es válido. |
| **Regla flexible** | Preferencia; el generador intenta cumplirla pero puede saltársela si es necesario. |

## 4. Modelo de dominio

### 4.1 Tipos de turno

El horario de cada turno y el punto en que se divide en dos mitades (5.3)
son **configurables**. Valores iniciales de ejemplo:

| Turno | Horario | 1.ª mitad | 2.ª mitad |
|---|---|---|---|
| MAÑANA | 08:00 – 15:00 | 08:00 – 11:30 | 11:30 – 15:00 |
| TARDE | 15:00 – 22:00 | 15:00 – 18:30 | 18:30 – 22:00 |

El horario es solo informativo (se muestra en el calendario y en la
exportación); la lógica de asignación trabaja con el tipo de turno, no con las
horas.

### 4.2 Calendario

- Solo se planifican días de lunes a viernes.
- Un **calendario de festivos** elimina días del calendario. Es configurable:
  el planificador puede añadir, quitar o modificar festivos.
- La herramienta arranca con el calendario de **Madrid (Comunidad de
  Madrid)** precargado, que combina:
  - festivos nacionales (BOE),
  - festivos de la Comunidad de Madrid (BOCM),
  - los 2 festivos locales de Madrid (BOCM).
- Los festivos se cargan por año. Cuando se planifica un mes de un año sin
  festivos cargados, la herramienta avisa antes de generar.
- *(Versión 2.7.)* El **municipio del centro** es configurable (de la relación
  de municipios del INE). Para él, la herramienta busca en internet los
  festivos oficiales de un año (nacionales, autonómicos y locales, con la
  referencia oficial de cada uno), los compara con los guardados y añade los
  que falten, sin borrar ni cambiar los que haya. Los precargados de Madrid
  solo se usan si el municipio es Madrid.
- Las fechas exactas se verificarán con las fuentes oficiales al implementar.

### 4.3 Médico

| Campo | Descripción |
|---|---|
| Nombre | Nombre a mostrar. |
| Identificador | Código corto/iniciales para las vistas compactas del calendario. |
| Activo | Los médicos inactivos se conservan en el histórico pero nunca se asignan. |
| Reglas | Ver sección 5. |

### 4.4 Requisitos de cobertura

Son **configurables**. Para cada hueco semanal (p. ej. *lunes MAÑANA*), el
planificador indica:

- **Mínimo** de médicos necesarios (regla estricta).
- **Máximo** de médicos permitidos (regla estricta, opcional — por defecto
  igual al mínimo).

Ejemplo: las mañanas necesitan 3 médicos y las tardes 2.

Además, el planificador puede sobrescribir el requisito en **fechas
concretas** (p. ej. plantilla reducida el 24 de diciembre).

### 4.5 Ausencias

Un médico puede marcarse como no disponible durante un rango de fechas,
opcionalmente solo para un tipo de turno (p. ej. "las tardes de la semana del
10 de noviembre"). Las ausencias prevalecen siempre sobre cualquier otra regla.

## 5. Reglas por médico

Es el núcleo de la herramienta: *para cada médico debe poder definirse qué
subconjunto de mañanas/tardes tiene que cubrir.* El borrador propone los
siguientes tipos de regla, que pueden combinarse.

### 5.1 Elegibilidad (qué huecos *puede* hacer el médico) — estricta

Una cuadrícula de día de la semana × tipo de turno donde cada celda es:

| Valor | Significado |
|---|---|
| **Fijo** | El médico hace *siempre* este hueco (todas las semanas, salvo ausencia). |
| **Disponible** | El generador *puede* asignar al médico aquí. |
| **No disponible** | El generador *nunca* asigna al médico aquí. |

Ejemplo — Dra. García:

| | Lun | Mar | Mié | Jue | Vie |
|---|---|---|---|---|---|
| MAÑANA | Fijo | Fijo | Disponible | Disponible | No disponible |
| TARDE | No disponible | No disponible | Disponible | Disponible | No disponible |

Plantillas rápidas: "solo mañanas", "solo tardes", "cualquiera".

### 5.2 Carga mensual (cuántos turnos) — estricta, dentro de un rango

La carga se mide **por mes**, en turnos y con precisión de medio turno:

- **Mínimo de turnos al mes** y **máximo de turnos al mes** (p. ej. entre 16
  y 18,5).
- Opcionalmente por tipo de turno: p. ej. "entre 4 y 6 tardes al mes".

Los huecos fijos cuentan para estos números. Un medio turno cuenta 0,5.

#### Reducción por ausencias

Si un médico tiene ausencias en el mes, su rango (mínimo y máximo, y los
rangos por tipo de turno si los tiene) se **reduce de forma proporcional** a
los días laborables en que está disponible:

```
rango ajustado = rango × (días laborables disponibles / días laborables del mes)
```

- Los festivos no cuentan como días laborables del mes.
- Una ausencia de un solo turno (p. ej. solo tardes) cuenta como medio día.
- El resultado se redondea al medio turno más cercano.
- La herramienta muestra el rango ajustado junto al original, y el
  planificador puede sobrescribirlo a mano para ese mes.

Ejemplo: rango 16–18 turnos, mes con 20 días laborables, 5 días de
vacaciones → 15/20 = 0,75 → rango ajustado 12–13,5.

### 5.3 Jornada diaria — estricta

Cada día, un médico puede trabajar:

| Jornada | Composición |
|---|---|
| **1 turno** | Mañana **o** tarde. |
| **1,5 turnos** | Mañana + primera mitad de la tarde, **o** segunda mitad de la mañana + tarde. |
| **2 turnos** | Mañana **y** tarde completas. |

- **R-D1**: El generador **solo asigna jornadas de 1 turno**. Las jornadas de
  1,5 y 2 turnos las define **únicamente el planificador**, de dos formas:
  - como regla semanal del médico (p. ej. "todos los martes, mañana + primera
    mitad de la tarde"), que se trata igual que un hueco *Fijo* (5.1);
  - manualmente en una fecha concreta, que se trata como una asignación
    bloqueada (6.1).
- **R-D2**: El medio turno es siempre la mitad contigua al turno completo:
  - con turno de **mañana**, se añade la **primera mitad de la tarde**;
  - con turno de **tarde**, se añade la **segunda mitad de la mañana**.
- **R-D3**: No existen jornadas de solo medio turno.
- Para representar los medios turnos, cada turno se divide en dos mitades
  (MAÑANA-1, MAÑANA-2, TARDE-1, TARDE-2). La cobertura (4.4) se comprueba en
  cada mitad, y los medios turnos definidos por el planificador cuentan para
  la cobertura de su mitad.

Las horas de cada mitad son configurables (4.1).

### 5.4 Preferencias — flexibles

Opcionales, por médico:

- Huecos preferidos / no deseados (día de la semana × tipo de turno).
- Turno **habitual** en la cuadrícula (5.1): si trabaja ese día, mejor ese
  turno (añadido en la versión 2.1).

### 5.6 Urgencias y domicilios por la tarde (añadido en la versión 2.3)

- Cada tarde laborable, entre los médicos asignados, uno se encarga de las
  **urgencias** en el centro y otro de **asistir a domicilios**. No pueden
  ser el mismo médico.
- Solo pueden hacerlo quienes hacen la **tarde completa** ese día (no quien
  solo hace media tarde).
- Se exige las tardes que necesitan al menos **dos médicos** (4.4); con
  menos, el reparto no es posible.
- El reparto de cada papel, y el de los dos juntos, es **lo más ajustado
  posible a la parte de cada médico**:
  - Opción *según la presencia* (configurable, **activada por defecto**,
    versión 2.8): la parte es proporcional a las tardes del mes en que el
    médico no está ausente. Las reglas de su tarjeta no reducen su parte; solo
    limitan cuántas puede hacer.
  - Desactivada: la misma parte para todos (versión 2.6.1).
  - En los dos casos, quien no tiene tardes suficientes se queda con las que
    puede, y el resto se reparte entre los demás. La parte exacta se redondea
    por restos mayores: entre médicos con la misma presencia no hay más de
    una de diferencia (nunca 3, 2 y 1).
  - *(Versión 2.15.)* Si no se puede ajustar todo, **la igualdad de las
    urgencias prevalece**: primero se iguala el reparto de urgencias, después el
    de domicilios y por último el de los dos juntos, de modo que la desigualdad
    inevitable recae en los domicilios. Es configurable: urgencias primero (por
    defecto), domicilios primero o los dos a la vez.
- El planificador puede cambiarlo a mano; el cambio queda bloqueado.

### 5.7 Todos trabajan cada día (añadido en la versión 2.4)

Opción general, en *Configuración* y **activada por defecto**: cada médico
activo con carga tiene al menos un turno cada día laborable, salvo los días
que está ausente o en que no tiene ningún turno posible (los dos marcados
«—» o quitados a mano). Si solo está ausente un turno, hace el otro. Va por
delante de la cobertura máxima y de la carga mensual; si chocan, se avisa
de qué límite conviene subir.

### 5.7.1 Carga según la presencia (añadido en la versión 2.16)

- Configurable: **cuánto trabaja cada médico** se decide por el **rango** de su
  ficha (mínimo y máximo al mes, como hasta ahora; por defecto) o **según la
  presencia**: todos los días laborables salvo ausencia.
- Según la presencia: «todos trabajan cada día» (5.7) va siempre incluido; no se
  usan los rangos de las fichas ni los límites por tipo de turno, ni los rangos
  ajustados a mano del mes; el reparto de los turnos que sobran sigue la
  equidad (6), en proporción a los días que está cada médico.
- La interfaz no pide ni muestra rangos (fichas, tabla de carga, avisos de
  «sin carga», hoja de cálculo).

### 5.8 Turnos rotativos (añadido en la versión 2.5)

Un grupo de médicos comparte unos turnos de la semana (p. ej. lunes y jueves
por la tarde) sin coincidir: cada semana los hace **uno** del grupo, como
turno fijo, por orden; la semana de inicio, el primero de la lista; la
siguiente, el segundo, y así en bucle. La cuenta de semanas sigue de un mes a
otro.

- Los demás miembros no reciben esos turnos la semana que no les toca; la
  rotación manda sobre el «Fijo» de sus tarjetas para esos turnos.
- Si a quien le toca no puede (ausencia, festivo, quitado a mano), ese día el
  turno queda libre y lo cubre el resto del equipo, incluidos los demás del
  grupo.
- Se definen en *Médicos y reglas → Turnos rotativos*; un grupo necesita al
  menos dos médicos y un turno, y puede desactivarse sin borrarlo.

## 6. Asignación automática

### 6.1 Entradas

Periodo de planificación, festivos, médicos con sus reglas, requisitos de
cobertura, ausencias y las asignaciones que el planificador haya **bloqueado**
manualmente.

### 6.2 Restricciones estrictas (deben cumplirse todas)

1. Cada hueco (cada una de sus dos mitades) tiene entre su mínimo y su máximo
   de médicos.
2. Los médicos solo se asignan a huecos donde son *Fijo* o *Disponible*.
3. Los huecos *Fijos* siempre se asignan (salvo ausencia del médico o
   festivo).
4. Ningún médico se asigna durante una ausencia.
5. La carga mensual de cada médico (5.2) está dentro de su rango, ya ajustado
   por ausencias.
6. Se cumplen las reglas de jornada diaria (5.3): el generador nunca crea por
   su cuenta una jornada de 1,5 o 2 turnos.
7. Las asignaciones bloqueadas se mantienen tal cual.
8. Cada tarde que lo requiere (5.6), un médico distinto para urgencias y para
   domicilios, ambos con la tarde completa.
9. Con la opción de 5.7, cada médico trabaja todos los días en que puede.
10. Los turnos rotativos (5.8): a quien le toca, fijo; los demás del grupo, no.

### 6.3 Objetivos de optimización (flexibles, por orden de prioridad — por confirmar)

1. **Equidad**: repartir los turnos "extra" de forma equilibrada entre médicos
   con las mismas reglas (cada médico cerca de la media de su grupo).
2. Respetar las preferencias de los médicos (5.4).
3. **Estabilidad**: al regenerar un periodo, cambiar el menor número posible
   de asignaciones existentes.
4. Equidad entre periodos: tener en cuenta los totales de meses anteriores
   para que los desequilibrios se compensen con el tiempo (solo se usan
   los meses publicados).

### 6.4 Cuando no existe un calendario válido

La herramienta no debe generar en silencio un calendario incompleto. Debe
explicar *por qué*, en términos sobre los que el planificador pueda actuar,
p. ej.:

- "El mar 2026-11-11 MAÑANA necesita 3 médicos pero solo hay 2 disponibles."
- "El Dr. López necesita al menos 16 turnos en noviembre pero solo tiene 14
  huecos disponibles (ausencia del 10 al 13 de noviembre)."

Después, ofrece un calendario **de mejor esfuerzo** que deja sin cubrir los
huecos problemáticos y los resalta, para que el planificador los resuelva a
mano.

### 6.5 Determinismo

Con las mismas entradas, el generador produce el mismo calendario. Una acción
"generar alternativa" puede producir otro calendario válido distinto.

### 6.6 Rendimiento

Objetivo: un equipo de hasta ~30 médicos y un periodo de un mes generado en
menos de 10 segundos.

## 7. Flujo de trabajo e interfaz

1. **Configuración** (una vez, y se edita ocasionalmente): médicos, reglas,
   requisitos de cobertura, horarios de turno.
2. **Por cada periodo**:
   1. Elegir el periodo (por defecto: el mes siguiente).
   2. Introducir festivos y ausencias.
   3. Generar.
   4. Revisar el calendario: vista mensual con una fila por día y columnas
      MAÑANA / TARDE con los médicos asignados (indicando los medios
      turnos); más un resumen por médico (turnos del mes, por tipo,
      frente a su rango).
   5. Ajustar manualmente: mover/añadir/quitar un médico de un hueco. La
      herramienta avisa al momento si un cambio manual incumple una regla
      estricta (pero lo permite — el planificador tiene la última palabra).
   6. Bloquear asignaciones y regenerar el resto si hace falta.
   7. Marcar el periodo como **publicado** (solo lectura salvo que se reabra
      explícitamente).
3. **Exportación**: vista imprimible / PDF y hoja de cálculo (XLSX). Es la
   forma de compartir el calendario con los médicos. Además (versión 2.9), un informe
   de **urgencias y domicilios** del mes, imprimible y en XLSX: quién hace
   cada papel cada día y cuántas veces cada médico.

Idioma de la interfaz: castellano.

## 8. Requisitos no funcionales

- **Usuarios**: un único planificador, sin inicio de sesión.
- **Plataforma**: **aplicación web local**. Se ejecuta en el PC del
  planificador y se usa desde el navegador; no necesita servidor ni conexión
  a internet.
- **Almacenamiento**: base de datos local en un único fichero (SQLite), fácil
  de copiar como copia de seguridad.
- **Privacidad**: solo se guardan nombres de médicos y su disponibilidad —
  ningún dato de pacientes. No se guarda el motivo de las ausencias (p. ej.
  baja médica), solo las fechas.
- **Copias de seguridad / histórico**: los calendarios publicados se conservan
  y pueden consultarse más adelante.

## 9. Parámetros configurables

| Parámetro | Ámbito | Sección | Valor inicial |
|---|---|---|---|
| Horario de cada turno y división en mitades | Global | 4.1 | 08:00–15:00 / 15:00–22:00, mitades a las 11:30 y 18:30 |
| Calendario de festivos | Por año | 4.2 | Madrid (Comunidad de Madrid) |
| Médicos por hueco (mínimo / máximo) | Por día de la semana × turno | 4.4 | Por definir al configurar |
| Médicos por hueco en fechas concretas | Por fecha × turno | 4.4 | Ninguna |
| Ausencias | Por médico y rango de fechas | 4.5 | — |
| Cuadrícula de elegibilidad (Fijo / Disponible / No disponible) | Por médico | 5.1 | Disponible en todo |
| Carga mensual (mínimo / máximo, opcionalmente por tipo) | Por médico | 5.2 | Por definir al configurar |
| Rango ajustado por ausencias (sobrescritura manual) | Por médico y mes | 5.2 | Calculado |
| Jornadas de 1,5 / 2 turnos | Por médico (regla semanal) o por fecha | 5.3 | Ninguna |
| Preferencias (huecos preferidos / no deseados) | Por médico | 5.4 | Ninguna |

## 10. Registro de decisiones

| # | Pregunta | Decisión |
|---|---|---|
| P1 | ¿Qué subconjunto de turnos tiene que cubrir cada médico? | Configurable por médico: cuadrícula de elegibilidad (5.1) + carga mensual (5.2). |
| P2 | ¿Cuántos médicos por turno? | Configurable por día de la semana × turno, con excepciones por fecha (4.4). |
| P3 | ¿Puede un médico hacer mañana y tarde el mismo día? | Sí: la jornada puede ser de 1; 1,5 o 2 turnos (5.3). |
| P4 | ¿Cómo se mide la carga? | Por mes, con precisión de medio turno (5.2). |
| P5 | ¿Hacen falta rotaciones (semanas alternas)? | No en la v1. |
| P6 | ¿Duración del periodo de planificación? | Un mes natural. |
| P7 | ¿La equidad se arrastra entre meses? | Sí, como objetivo de baja prioridad (6.3). |
| P8 | ¿Qué hacer cuando las reglas no pueden cumplirse? | Explicar el conflicto + calendario de mejor esfuerzo con huecos resaltados (6.4). |
| P9 | ¿Quién usa la herramienta? | Un único planificador; los médicos reciben la exportación. |
| P10 | ¿Plataforma? | Aplicación web local (8). |
| P11 | ¿Tamaño del equipo? | Hasta ~30 médicos (6.6). |
| P12a | ¿Horario de los turnos y de cada mitad? | Configurable (4.1). |
| P12b | ¿Qué festivos aplican? | Configurable; se arranca con Madrid (Comunidad de Madrid) (4.2). |
| P13 | ¿Idioma de la interfaz? | Castellano. |
| P14 | ¿Formatos de exportación? | PDF/impresión + XLSX. |
| P15 | ¿Qué mitad es el medio turno? | La contigua: mañana + primera mitad de la tarde, o segunda mitad de la mañana + tarde (5.3). |
| P16 | ¿El generador puede crear jornadas de 1,5 / 2 turnos? | No. Solo las define el planificador (5.3). |
| P17 | ¿Las ausencias reducen la carga mensual? | Sí, de forma proporcional (5.2). |
| P18 | ¿Almacenamiento? | Fichero SQLite local (8). |
| P21 | ¿Cómo se comparten turnos fijos entre varios médicos? | Turnos rotativos por semanas, sin coincidir (5.8). |
| P20 | ¿Todos los médicos trabajan cada día? | Opción general, activada por defecto (5.7). |
| P19 | ¿Quién hace urgencias y domicilios por la tarde? | Uno de cada, distintos, con la tarde completa, repartidos de forma uniforme entre quienes pueden hacer tardes (5.6). |
