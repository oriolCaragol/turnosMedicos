import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAccionesCalendario, useAjustes, useCalendario, useEstado } from "../api/consultas";
import { useCambiosExternos } from "../api/eventos";
import { useYo } from "../api/sesion";
import type { Calendario as TCalendario, Cambio, MedicoCalendario, Rol, Turno } from "../api/tipos";
import {
  admiteMedio,
  cambiosAlSoltar,
  cifra,
  estadoCelda,
  foto,
  idoneidad,
  mitadesConValor,
  mitadesDe,
  NOMBRE_ROL,
  nombreCorto,
  rolDe,
  valorEnTurno,
  type Destino,
  type Origen,
  type Valor,
} from "../calendario/logica";
import { useHistorial } from "../calendario/useHistorial";
import { useVista, type Vista } from "../calendario/useVista";
import { Cajon } from "../componentes/Cajon";
import { IconoCasa, IconoEmergencia } from "../componentes/Iconos";
import { CampoTurnos } from "../componentes/CampoTurnos";
import { mayuscula } from "../componentes/Disposicion";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { diaSemana, formatearFecha, nombreMes } from "../util/fechas";
import { estiloColor } from "../util/colores";
import { useMes } from "../util/mes";
import { DIAS, DIAS_CORTOS, formatearMedios, MITADES_DE, TURNOS } from "../util/textos";
import css from "./Calendario.module.css";

const NOMBRE: Record<Turno, string> = { MANANA: "Mañana", TARDE: "Tarde" };
const ESTADOS: Record<string, string> = { SIN_GENERAR: "Sin generar", BORRADOR: "Borrador", PUBLICADO: "Publicado" };
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** "2026-11-04" → "miércoles 4 nov" */
function diaLargo(fecha: string): string {
  const [, m, d] = fecha.split("-").map(Number);
  return `${DIAS[diaSemana(fecha)].toLowerCase()} ${d} ${MESES_CORTOS[m - 1]}`;
}

type Hueco = { fecha: string; turno: Turno };
type Liberar = (alcance: { fecha?: string; turno?: Turno }, mensaje: string) => void;

/** Cobertura de un turno: el mayor mínimo y el mayor máximo de sus dos mitades. */
function coberturaTurno(cal: TCalendario, fecha: string, turno: Turno) {
  const filas = cal.cobertura.filter((c) => c.fecha === fecha && MITADES_DE[turno].includes(c.mitad));
  return { minimo: Math.max(0, ...filas.map((c) => c.minimo)), maximo: Math.max(0, ...filas.map((c) => c.maximo)) };
}

function turnoBloqueado(cal: TCalendario, fecha: string, turno: Turno) {
  return (
    cal.asignaciones.some((a) => a.fecha === fecha && a.bloqueada && MITADES_DE[turno].includes(a.mitad)) ||
    cal.vetos.some((v) => v.fecha === fecha && v.turno === turno) ||
    (turno === "TARDE" && (cal.roles ?? []).some((r) => r.fecha === fecha && r.manual))
  );
}

export function Calendario() {
  const { mes, anio, numMes } = useMes();
  const calendario = useCalendario(anio, numMes);
  const acciones = useAccionesCalendario(anio, numMes);
  const tostada = useTostada();
  const cal = calendario.data;
  const editable = cal?.estado !== "PUBLICADO";

  const calRef = useRef(cal);
  calRef.current = cal;
  // Si otro usuario cambia este mes, el historial de deshacer se vacía.
  const externos = useCambiosExternos(anio, numMes);
  const historial = useHistorial(
    `${mes}|${externos}`,
    useCallback(() => (calRef.current ? foto(calRef.current) : undefined), []),
    acciones.restaurar.mutateAsync,
    editable,
  );

  const cambiar = (cambios: Cambio[]) => {
    if (!cal || cambios.length === 0) return;
    historial.registrar(foto(cal));
    acciones.cambiar.mutate(cambios);
  };

  const [sinResultado, setSinResultado] = useState(false);
  const generar = (alternativa: boolean) => {
    if (cal && cal.estado !== "SIN_GENERAR") historial.registrar(foto(cal));
    setSinResultado(false);
    acciones.generar.mutate(alternativa, {
      // Si no se ha podido asignar ningún turno, se dice junto al botón (no solo abajo).
      onSuccess: (nuevo) => setSinResultado(nuevo.asignaciones.length === 0),
    });
  };

  const liberar: Liberar = (alcance, mensaje) => {
    if (!cal) return;
    historial.registrar(foto(cal));
    acciones.liberar.mutate(alcance, { onSuccess: () => tostada(mensaje) });
  };

  const error =
    acciones.generar.error ??
    acciones.cambiar.error ??
    acciones.restaurar.error ??
    acciones.publicar.error ??
    acciones.cargaManual.error ??
    acciones.liberar.error;

  if (calendario.isPending) return <Cargando />;
  if (calendario.isError || !cal) return <MensajeError error={calendario.error} />;
  const sinGenerar = cal.estado === "SIN_GENERAR";
  const activos = cal.medicos.filter((m) => m.activo);
  const sinCarga = activos.filter((m) => !m.con_carga);

  return (
    <>
      <section className="panel">
        <div className="barra-titulo">
          <Resumen cal={cal} />
          <div className="acciones">
            {editable && (
              <>
                <button type="button" className="btn primario" onClick={() => generar(false)} disabled={acciones.generar.isPending}>
                  {acciones.generar.isPending ? "Generando…" : sinGenerar ? "Generar calendario" : "Regenerar"}
                </button>
                {!sinGenerar && (
                  <button type="button" className="btn" onClick={() => generar(true)} disabled={acciones.generar.isPending}>
                    Generar alternativa
                  </button>
                )}
                <button type="button" className="btn" onClick={historial.deshacer} disabled={!historial.puedeDeshacer} title="Ctrl+Z">
                  Deshacer
                </button>
                <button type="button" className="btn" onClick={historial.rehacer} disabled={!historial.puedeRehacer} title="Ctrl+Y">
                  Rehacer
                </button>
              </>
            )}
            {!sinGenerar && (
              <button
                type="button"
                className="btn"
                onClick={() => {
                  if (!editable || confirm(`¿Publicar el calendario de ${nombreMes(mes)}? Quedará en solo lectura.`)) {
                    acciones.publicar.mutate(editable);
                  }
                }}
              >
                {editable ? "Publicar" : "Reabrir"}
              </button>
            )}
          </div>
        </div>
        {editable && sinCarga.length > 0 && (
          <div className={`mensaje ${sinCarga.length === activos.length ? "mensaje-error" : "mensaje-aviso"} ${css.avisoGenerar}`} role="alert">
            {sinCarga.length === activos.length
              ? `Ningún médico tiene carga mensual en ${nombreMes(mes)}, así que el calendario no puede asignar turnos. `
              : `${sinCarga.length === 1 ? "1 médico no tiene" : `${sinCarga.length} médicos no tienen`} carga mensual en ${nombreMes(mes)} y no recibirán turnos (${sinCarga
                  .map((m) => m.nombre)
                  .join(", ")}). `}
            Indica sus <b>turnos/mes mínimo y máximo</b> en <Link to={`/medicos?mes=${mes}`}>Médicos y reglas</Link>.
          </div>
        )}
        {sinResultado && sinGenerar && sinCarga.length < activos.length && (
          <div className={`mensaje mensaje-error ${css.avisoGenerar}`} role="alert">
            No se ha podido asignar ningún turno. Revisa las causas en <a href="#problemas">Problemas a resolver</a>.
          </div>
        )}
        {activos.length === 0 && (
          <div className={`mensaje mensaje-aviso ${css.avisoGenerar}`} role="alert">
            Aún no hay médicos. Añádelos en <Link to={`/medicos?mes=${mes}`}>Médicos y reglas</Link>.
          </div>
        )}
        <Leyenda />
      </section>
      <MensajeError error={error} />

      <ZonaArrastre cal={cal} cambiar={cambiar}>
        {(arrastrado) => (
          <>
            <Rejilla cal={cal} editable={editable} cambiar={cambiar} liberar={liberar} arrastrado={arrastrado} />
            <div className="dos-columnas">
              <Problemas cal={cal} mes={mes} />
              <CargaPorMedico cal={cal} editable={editable} acciones={acciones} />
            </div>
          </>
        )}
      </ZonaArrastre>

      {!sinGenerar && (
        <section className="panel">
          <div className="barra-titulo">
            <div>
              <h2>Exportar</h2>
              <p className="entradilla" style={{ margin: 0 }}>
                Hoja de cálculo con el calendario, los turnos de cada médico y el resumen de carga. Para imprimir o guardar
                como PDF: el calendario como se ve aquí, o la tabla día a día. Y aparte, las urgencias y domicilios del mes.
              </p>
            </div>
            <div className="acciones">
              <a className="btn" href={`/api/periodos/${anio}/${numMes}/exportar.xlsx`} download>
                Exportar XLSX
              </a>
              <Link className="btn" to={`/imprimir/calendario?mes=${mes}&auto=1`}>
                Imprimir calendario / PDF
              </Link>
              <Link className="btn" to={`/imprimir?mes=${mes}&auto=1`}>
                Imprimir tabla / PDF
              </Link>
              <a className="btn" href={`/api/periodos/${anio}/${numMes}/urgencias-domicilios.xlsx`} download>
                Urgencias y domicilios XLSX
              </a>
              <Link className="btn" to={`/imprimir/urgencias-domicilios?mes=${mes}&auto=1`}>
                Imprimir urgencias y domicilios
              </Link>
              {editable && (
                <button type="button" className="btn" onClick={() => liberar({}, "Todo el mes vuelve a ser automático")}>
                  Volver a automático todo el mes
                </button>
              )}
            </div>
          </div>
        </section>
      )}
    </>
  );
}

// --- Resumen ------------------------------------------------------------------------------

function Resumen({ cal }: { cal: TCalendario }) {
  const laborables = cal.dias.filter((d) => !d.festivo);
  let bajoMinimo = 0;
  let sobre = 0;
  let bloqueados = 0;
  for (const d of laborables)
    for (const t of TURNOS) {
      const e = estadoCelda(cal, d.fecha, t);
      if (e === "falta") bajoMinimo++;
      if (e === "sobra") sobre++;
      if (turnoBloqueado(cal, d.fecha, t)) bloqueados++;
    }
  const generado = cal.estado !== "SIN_GENERAR";
  const enServidor = useYo().data?.modo === "servidor";

  const cifras: [ReactNode, string, string?][] = [
    [laborables.length, "días laborables"],
    [laborables.length * 2, "turnos"],
    ...(generado
      ? ([
          [bajoMinimo, "bajo el mínimo", bajoMinimo ? "--critico" : "--ok"],
          [sobre, "sobre el máximo", sobre ? "--aviso" : undefined],
        ] as [ReactNode, string, string?][])
      : []),
    [cal.dias.length - laborables.length, "festivos entre semana"],
    ...(generado ? ([[bloqueados, "turnos bloqueados"]] as [ReactNode, string][]) : []),
  ];

  return (
    <div className={css.franjaResumen}>
      <span className={`${css.estado} ${css[`estado_${cal.estado}`]}`}>{ESTADOS[cal.estado]}</span>
      {enServidor && cal.estado === "BORRADOR" && (
        <span className="nota" data-aviso-borrador>
          Los médicos no lo ven hasta que se publique
        </span>
      )}
      {cifras.map(([valor, texto, color]) => (
        <div key={texto} className={css.cifra}>
          <b style={color ? { color: `var(${color})` } : undefined}>{valor}</b>
          <span className="etiqueta">{texto}</span>
        </div>
      ))}
    </div>
  );
}

function Leyenda({ soloLectura = false }: { soloLectura?: boolean }) {
  return (
    <div className={css.leyenda}>
      {!soloLectura && (
        <>
          <span>
            <span className={css.punto} style={{ background: "var(--critico)" }} />
            bajo el mínimo
          </span>
          <span>
            <span className={css.punto} style={{ background: "var(--aviso)" }} />
            sobre el máximo
          </span>
        </>
      )}
      <span>
        <span className={`${css.ficha} ${css.fija}`}>Nombre</span> fijo
      </span>
      <span>
        <span className={`${css.ficha} ${css.media}`}>Nombre ½</span> medio turno
      </span>
      <span>
        <span className={`${css.ficha} ${css.doble}`}>Nombre</span> mañana y tarde
      </span>
      {!soloLectura && (
        <span>
          <span className={css.bloqueo}>BLOQ.</span> cambiado a mano
        </span>
      )}
      <span>
        <InsigniaRol rol="URGENCIAS" decorativa /> urgencias
      </span>
      <span>
        <InsigniaRol rol="DOMICILIOS" decorativa /> domicilios
      </span>
    </div>
  );
}

/**
 * El calendario del mes con el mismo formato que el del planificador, pero solo para
 * consultar: la vista de los médicos y la de imprimir el calendario.
 */
export function CalendarioSoloLectura({ cal, resaltar, vistaFija }: { cal: TCalendario; resaltar?: number; vistaFija?: Vista }) {
  const nada = () => {};
  return (
    <>
      <Leyenda soloLectura />
      {/* Las fichas usan dnd-kit aunque no se puedan arrastrar: necesitan su contexto. */}
      <DndContext>
        <Rejilla cal={cal} editable={false} cambiar={nada} liberar={nada} soloLectura resaltar={resaltar} vistaFija={vistaFija} />
      </DndContext>
    </>
  );
}

// --- Rejilla del mes -------------------------------------------------------------------------

/**
 * Contexto de arrastrar y soltar: abarca el calendario y la tabla de carga, para poder
 * arrastrar médicos de una celda a otra y desde la tabla. Soltar fuera de una celda quita.
 */
function ZonaArrastre({
  cal,
  cambiar,
  children,
}: {
  cal: TCalendario;
  cambiar: (c: Cambio[]) => void;
  children: (arrastrado: MedicoCalendario | undefined) => ReactNode;
}) {
  const [arrastrando, setArrastrando] = useState<Origen | null>(null);
  const ctrl = useRef(false);
  const sensores = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );
  const medicos = useMemo(() => new Map(cal.medicos.map((m) => [m.id, m])), [cal.medicos]);

  useEffect(() => {
    const teclas = (e: KeyboardEvent) => (ctrl.current = e.ctrlKey || e.metaKey);
    window.addEventListener("keydown", teclas);
    window.addEventListener("keyup", teclas);
    return () => {
      window.removeEventListener("keydown", teclas);
      window.removeEventListener("keyup", teclas);
    };
  }, []);

  const alEmpezar = (e: DragStartEvent) => {
    const evento = e.activatorEvent as PointerEvent;
    ctrl.current = Boolean(evento.ctrlKey || evento.metaKey);
    setArrastrando(e.active.data.current as Origen);
  };

  const alSoltar = (e: DragEndEvent) => {
    const origen = e.active.data.current as Origen;
    setArrastrando(null);
    const destino = (e.over?.data.current as { destino?: Destino } | undefined)?.destino ?? null;
    if (origen.tipo === "resumen" && !destino) return;
    cambiar(cambiosAlSoltar(cal, origen, destino, ctrl.current));
  };

  const arrastrado = arrastrando ? medicos.get(arrastrando.medico) : undefined;
  return (
    <DndContext sensors={sensores} onDragStart={alEmpezar} onDragEnd={alSoltar} onDragCancel={() => setArrastrando(null)}>
      {children(arrastrado)}
      <DragOverlay dropAnimation={null}>
        {arrastrado && (
          <span className={`${css.ficha} ${css.flotante}`} style={estiloColor(arrastrado.color)}>
            {nombreCorto(arrastrado.nombre)}
            {arrastrando?.tipo === "celda" && ctrl.current ? " +" : ""}
          </span>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function Rejilla({
  cal,
  editable,
  cambiar,
  liberar,
  arrastrado,
  soloLectura = false,
  resaltar,
  vistaFija,
}: {
  cal: TCalendario;
  editable: boolean;
  cambiar: (c: Cambio[]) => void;
  liberar: Liberar;
  arrastrado?: MedicoCalendario;
  /** Solo consulta (médicos, impresión): sin panel del turno ni marcas del planificador. */
  soloLectura?: boolean;
  /** Médico cuyo nombre se resalta (el propio, en la vista de un médico). */
  resaltar?: number;
  /** Para imprimir: siempre en cuadrícula, sin el selector de vista. */
  vistaFija?: Vista;
}) {
  const [abierto, setAbierto] = useState<Hueco | null>(null);
  const [vistaGuardada, setVista] = useVista();
  const vista = vistaFija ?? vistaGuardada;
  const medicos = useMemo(() => new Map(cal.medicos.map((m) => [m.id, m])), [cal.medicos]);
  const primero = cal.dias[0] ? diaSemana(cal.dias[0].fecha) : 0;

  const franjas = (fecha: string) =>
    TURNOS.map((t) => (
      <Franja
        key={t}
        cal={cal}
        fecha={fecha}
        turno={t}
        medicos={medicos}
        editable={editable && !soloLectura}
        arrastrado={arrastrado}
        abrir={() => !soloLectura && setAbierto({ fecha, turno: t })}
        soloLectura={soloLectura}
        resaltar={resaltar}
      />
    ));

  return (
    <>
      <section>
        {!vistaFija && (
          <div className={css.barraVista}>
            <span className="etiqueta">Vista</span>
            <div className="segmentos" role="group" aria-label="Vista del calendario">
              {(
                [
                  ["cuadricula", "Cuadrícula"],
                  ["lista", "Lista"],
                ] as [Vista, string][]
              ).map(([v, texto]) => (
                <button key={v} type="button" aria-pressed={vista === v} onClick={() => setVista(v)}>
                  {texto}
                </button>
              ))}
            </div>
          </div>
        )}
        {vista === "cuadricula" ? (
          <div className={css.desplazable}>
            <div className={css.mesRejilla} data-vista="cuadricula">
              {DIAS_CORTOS.map((d) => (
                <div key={d} className={`etiqueta ${css.cabeceraDia}`}>
                  {d}
                </div>
              ))}
              {Array.from({ length: primero }, (_, i) => (
                <div key={`vacio-${i}`} className={`${css.dia} ${css.fuera}`} />
              ))}
              {cal.dias.map((d) =>
                d.festivo ? (
                  <div key={d.fecha} id={`dia-${d.fecha}`} className={`${css.dia} ${css.festivo}`}>
                    <div className={css.numeroDia}>
                      <b>{Number(d.fecha.slice(8))}</b>
                      <span>Festivo</span>
                    </div>
                    <div className={css.nombreFestivo}>{d.festivo}</div>
                  </div>
                ) : (
                  <div key={d.fecha} id={`dia-${d.fecha}`} className={css.dia}>
                    <div className={css.numeroDia}>
                      <b>{Number(d.fecha.slice(8))}</b>
                    </div>
                    {franjas(d.fecha)}
                  </div>
                ),
              )}
            </div>
          </div>
        ) : (
          <div className={css.lista} data-vista="lista">
            {cal.dias.map((d, i) => {
              const ds = diaSemana(d.fecha);
              const nuevaSemana = i > 0 && ds === 0;
              return (
                <div
                  key={d.fecha}
                  id={`dia-${d.fecha}`}
                  className={[css.filaLista, d.festivo && css.festivo, nuevaSemana && css.nuevaSemana].filter(Boolean).join(" ")}
                >
                  <div className={css.diaLista}>
                    <b>{Number(d.fecha.slice(8))}</b>
                    <span>{DIAS[ds]}</span>
                  </div>
                  {d.festivo ? (
                    <div className={css.festivoLista}>
                      <span className="etiqueta">Festivo</span> {d.festivo}
                    </div>
                  ) : (
                    franjas(d.fecha)
                  )}
                </div>
              );
            })}
          </div>
        )}
        {!soloLectura && (
          <p className="nota">
            Las cifras indican «asignados / mínimo–máximo». Pulsa un turno para elegir quién lo hace, o arrastra un nombre a
            otro turno (con Ctrl, para copiarlo); suéltalo fuera del calendario para quitarlo. Lo que cambias a mano queda
            bloqueado y se respeta al regenerar.
          </p>
        )}
      </section>

      {abierto && (
        <DetalleTurno cal={cal} {...abierto} editable={editable} cambiar={cambiar} liberar={liberar} cerrar={() => setAbierto(null)} />
      )}
    </>
  );
}

function Franja({
  cal,
  fecha,
  turno,
  medicos,
  editable,
  arrastrado,
  abrir,
  soloLectura = false,
  resaltar,
}: {
  cal: TCalendario;
  fecha: string;
  turno: Turno;
  medicos: Map<number, MedicoCalendario>;
  editable: boolean;
  arrastrado?: MedicoCalendario;
  abrir: () => void;
  soloLectura?: boolean;
  resaltar?: number;
}) {
  const destino: Destino = { fecha, turno };
  const { setNodeRef, isOver } = useDroppable({ id: `celda|${fecha}|${turno}`, data: { destino }, disabled: !editable });

  const filas = cal.asignaciones.filter((a) => a.fecha === fecha && MITADES_DE[turno].includes(a.mitad));
  const porMedico = new Map<number, typeof filas>();
  for (const a of filas) porMedico.set(a.medico_id, [...(porMedico.get(a.medico_id) ?? []), a]);
  const { minimo, maximo } = coberturaTurno(cal, fecha, turno);
  const ajustes = useAjustes();
  const estado = estadoCelda(cal, fecha, turno);
  const ido = arrastrado ? idoneidad(cal, arrastrado, fecha, turno) : null;
  const total = cifra(filas.length);
  const otro: Turno = turno === "MANANA" ? "TARDE" : "MANANA";

  const clases = [
    css.franja,
    turno === "MANANA" ? css.franjaManana : css.franjaTarde,
    !soloLectura && estado === "falta" && css.critica,
    !soloLectura && estado === "sobra" && css.sobrante,
    soloLectura && css.soloLectura,
    ido && css[`ido_${ido}`],
    isOver && css.encima,
  ].filter(Boolean);

  return (
    <div ref={setNodeRef} className={clases.join(" ")} data-celda={`${fecha}-${turno}`} onClick={abrir}>
      <button
        type="button"
        className={css.cabeceraFranja}
        onClick={(e) => {
          e.stopPropagation();
          abrir();
        }}
        aria-label={`${NOMBRE[turno]} del ${formatearFecha(fecha)}: ${total} asignados`}
      >
        <span className={css.nombreTurno}>{NOMBRE[turno].toUpperCase()}</span>
        {!soloLectura && turnoBloqueado(cal, fecha, turno) && <span className={css.bloqueo}>BLOQ.</span>}
        {ajustes.data?.mostrar_cobertura && (
          <span className={css.cuenta} title="Médicos asignados / necesarios">
            {total}/{minimo === maximo ? minimo : `${minimo}–${maximo}`}
          </span>
        )}
      </button>
      <div className={css.fichas}>
        {porMedico.size === 0 && <span className="nota">nadie</span>}
        {[...porMedico.entries()].map(([id, propias]) => {
          const nombre = medicos.get(id)?.nombre ?? String(id);
          const color = medicos.get(id)?.color;
          const rol = turno === "TARDE" ? rolDe(cal, id, fecha) : null;
          const medio = propias.length === 1;
          const doble = !medio && valorEnTurno(mitadesDe(cal, id, fecha), otro) === 1;
          const fija = propias.every((a) => a.origen === "FIJO");
          const bloq = propias.some((a) => a.bloqueada);
          return (
            <Ficha
              key={id}
              id={`celda|${id}|${fecha}|${turno}`}
              origen={{ tipo: "celda", medico: id, fecha, turno }}
              texto={`${nombreCorto(nombre)}${medio ? " ½" : ""}`}
              titulo={`${nombre}${medio ? " (medio turno)" : ""}${rol ? ` · ${NOMBRE_ROL[rol].toLowerCase()}` : ""}${fija ? " · fijo" : ""}${bloq ? " · bloqueado" : ""}`}
              clases={[fija && css.fija, medio && css.media, doble && css.doble, id === resaltar && css.resaltada]
                .filter(Boolean)
                .join(" ")}
              color={color}
              rol={rol}
              editable={editable}
            />
          );
        })}
      </div>
    </div>
  );
}

function Ficha({
  id,
  origen,
  texto,
  titulo,
  clases = "",
  color,
  rol,
  editable,
}: {
  id: string;
  origen: Origen;
  texto: string;
  titulo: string;
  clases?: string;
  color?: string | null;
  rol?: Rol | null;
  editable: boolean;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id, data: origen, disabled: !editable });
  return (
    <span
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={(e) => e.stopPropagation()}
      title={titulo}
      aria-label={titulo}
      data-ficha={texto}
      style={estiloColor(color)}
      className={`${css.ficha} ${clases} ${editable ? css.arrastrable : ""} ${isDragging ? css.arrastrandose : ""}`}
    >
      {texto}
      {rol && <InsigniaRol rol={rol} />}
    </span>
  );
}

// --- Panel lateral de un turno ------------------------------------------------------------

function DetalleTurno({
  cal,
  fecha,
  turno,
  editable,
  cambiar,
  liberar,
  cerrar,
}: Hueco & {
  cal: TCalendario;
  editable: boolean;
  cambiar: (c: Cambio[]) => void;
  liberar: Liberar;
  cerrar: () => void;
}) {
  const asignados = cal.asignaciones.filter((a) => a.fecha === fecha && MITADES_DE[turno].includes(a.mitad));
  const bloqueado = turnoBloqueado(cal, fecha, turno);
  const { minimo, maximo } = coberturaTurno(cal, fecha, turno);
  const otro: Turno = turno === "MANANA" ? "TARDE" : "MANANA";
  const valor = (m: MedicoCalendario) => valorEnTurno(mitadesDe(cal, m.id, fecha), turno);
  const medicos = cal.medicos
    .filter((m) => m.activo || asignados.some((a) => a.medico_id === m.id))
    .sort((a, b) => Number(valor(b) > 0) - Number(valor(a) > 0) || a.nombre.localeCompare(b.nombre, "es"));

  return (
    <Cajon
      titulo={`${NOMBRE[turno]} del ${formatearFecha(fecha)}`}
      cerrar={cerrar}
      cabecera={
        <>
          <div className="etiqueta" style={{ color: `var(--${turno === "MANANA" ? "manana" : "tarde"})` }}>
            {NOMBRE[turno]}
          </div>
          <h2 style={{ fontSize: 17 }}>{mayuscula(diaLargo(fecha))}</h2>
          <div className="nota">
            {cifra(asignados.length)} asignados · mín. {minimo}, máx. {maximo}
            {bloqueado ? " · bloqueado" : ""}
          </div>
          {turno === "TARDE" && (cal.roles ?? []).some((r) => r.fecha === fecha) && (
            <div className="nota">
              {(["URGENCIAS", "DOMICILIOS"] as Rol[])
                .map((r) => {
                  const quien = (cal.roles ?? []).find((x) => x.fecha === fecha && x.rol === r);
                  const nombre = quien ? cal.medicos.find((mm) => mm.id === quien.medico_id)?.nombre : null;
                  return `${NOMBRE_ROL[r]}: ${nombre ?? "nadie"}`;
                })
                .join(" · ")}
            </div>
          )}
        </>
      }
      pie={
        <>
          {!editable ? (
            <span className="nota">Mes publicado: reábrelo para hacer cambios.</span>
          ) : bloqueado ? (
            <button type="button" className="btn" onClick={() => liberar({ fecha, turno }, "Turno devuelto al generador")}>
              Volver a automático
            </button>
          ) : (
            <span className="nota">Cualquier cambio bloquea este turno.</span>
          )}
          <button type="button" className="btn primario" onClick={cerrar} style={{ marginLeft: "auto" }}>
            Hecho
          </button>
        </>
      }
    >
      {medicos.map((m) => {
        const mitades = mitadesDe(cal, m.id, fecha);
        const actual = valor(m);
        const no = m.no_elegibles.find((n) => n.fecha === fecha && n.turno === turno);
        const enOtro = valorEnTurno(mitades, otro);
        const notas = [
          no
            ? no.motivo === "AUSENTE"
              ? "Ausente"
              : "No disponible"
            : (m.habituales ?? []).some((h) => h.fecha === fecha && h.turno === turno)
              ? "Turno habitual"
              : "Disponible",
          enOtro ? `trabaja la ${NOMBRE[otro].toLowerCase()} (${enOtro === 1 ? "1" : "½"})` : "",
          !cal.carga_por_rangos
            ? `${formatearMedios(m.asignado)} turnos`
            : m.con_carga
              ? `${formatearMedios(m.asignado)} turnos de ${formatearMedios(m.minimo!)}–${formatearMedios(m.maximo!)}`
              : "sin carga",
        ].filter(Boolean);
        const incumple = Boolean(no && actual > 0);
        const rol = turno === "TARDE" ? rolDe(cal, m.id, fecha) : null;
        if (turno === "TARDE" && (m.urgencias || m.domicilios)) {
          notas.push(`${m.urgencias ?? 0} urg. · ${m.domicilios ?? 0} dom. este mes`);
        }
        const bloq = asignados.some((a) => a.medico_id === m.id && a.bloqueada);
        return (
          <div key={m.id} className={css.filaCajon}>
            <div className={css.quien}>
              <b>
                {m.color && <span className={css.punto} style={{ background: m.color }} aria-hidden />}
                {m.nombre}
                {bloq && <span title="Bloqueado"> 🔒</span>}
              </b>
              <div className={`${css.razones} ${incumple ? css.razonesMal : ""}`}>
                {notas.join(" · ")}
                {incumple ? " · incumple una regla" : ""}
              </div>
            </div>
            <div className={css.controles}>
            <div className="segmentos" role="group" aria-label={m.nombre}>
              {([0, 0.5, 1] as Valor[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={actual === v}
                  disabled={!editable || (v === 0.5 && actual !== 0.5 && !admiteMedio(mitades, turno))}
                  title={v === 0.5 ? "Medio turno: solo junto a un turno completo el mismo día" : undefined}
                  onClick={() =>
                    actual !== v && cambiar([{ medico_id: m.id, fecha, mitades: mitadesConValor(mitades, turno, v) }])
                  }
                >
                  {v === 0 ? "No" : v === 0.5 ? "½" : "1"}
                </button>
              ))}
            </div>
            {turno === "TARDE" && actual === 1 && (
              <div className="segmentos" role="group" aria-label={`Papel de ${m.nombre}`}>
                {(["URGENCIAS", "DOMICILIOS"] as Rol[]).map((r) => (
                  <button
                    key={r}
                    type="button"
                    aria-pressed={rol === r}
                    disabled={!editable}
                    title={NOMBRE_ROL[r]}
                    aria-label={NOMBRE_ROL[r]}
                    className={css.botonRol}
                    onClick={() => rol !== r && cambiar([{ medico_id: m.id, fecha, rol: r }])}
                  >
                    {r === "URGENCIAS" ? <IconoEmergencia /> : <IconoCasa />}
                    {r === "URGENCIAS" ? "Urg." : "Dom."}
                  </button>
                ))}
              </div>
            )}
            </div>
          </div>
        );
      })}
    </Cajon>
  );
}

// --- Problemas y carga --------------------------------------------------------------------------

type Problema = { nivel: "critico" | "aviso"; t: ReactNode; r?: ReactNode; fecha?: string | null };

function Problemas({ cal, mes }: { cal: TCalendario; mes: string }) {
  const estado = useEstado();
  const anio = Number(mes.slice(0, 4));
  const problemas: Problema[] = [];

  if (estado.data && !estado.data.cobertura_definida) {
    problemas.push({
      nivel: "aviso",
      t: "No se ha definido cuántos médicos necesita cada turno",
      r: <Link to={`/cobertura?mes=${mes}`}>Definir la cobertura</Link>,
    });
  }
  for (const m of cal.medicos.filter((m) => m.activo && !m.con_carga)) {
    problemas.push({
      nivel: "aviso",
      t: `${m.nombre} no tiene carga mensual en ${nombreMes(mes)}`,
      r: (
        <>
          No se le asignarán turnos. <Link to={`/medicos?mes=${mes}`}>Defínela en Médicos y reglas</Link>.
        </>
      ),
    });
  }
  if (estado.data?.anios_festivos_incompletos.includes(anio)) {
    problemas.push({
      nivel: "aviso",
      t: `Faltan festivos por publicar en ${anio}`,
      r: (
        <>
          Normalmente las dos fiestas locales. <Link to={`/festivos?mes=${mes}`}>Revisar festivos</Link>
        </>
      ),
    });
  }

  // Cada incumplimiento con su causa (si el generador detectó una para ese día).
  const causas = cal.avisos.filter((a) => a.tipo === "CAUSA");
  const usadas = new Set<number>();
  for (const a of cal.avisos.filter((a) => a.tipo === "INCUMPLIMIENTO")) {
    const i = causas.findIndex((c, j) => !usadas.has(j) && c.fecha && c.fecha === a.fecha);
    if (i >= 0) usadas.add(i);
    problemas.push({
      nivel: /falta|por debajo/.test(a.mensaje) ? "critico" : "aviso",
      t: a.mensaje,
      r: i >= 0 ? `Causa: ${causas[i].mensaje}` : undefined,
      fecha: a.fecha,
    });
  }
  causas.forEach((c, j) => {
    if (!usadas.has(j)) problemas.push({ nivel: "aviso", t: c.mensaje, r: "Detectado al generar." });
  });
  problemas.sort((a, b) => Number(b.nivel === "critico") - Number(a.nivel === "critico"));

  return (
    <section className="panel" id="problemas">
      <h2>Problemas a resolver</h2>
      <p className="entradilla">Cada línea dice qué regla no se cumple, para que decidas si cambiar la regla o el calendario.</p>
      {problemas.length === 0 ? (
        <p className="vacio-ok">
          {cal.estado === "SIN_GENERAR"
            ? "La configuración está completa: ya puedes generar el calendario."
            : "Todos los turnos cumplen su cobertura y cada médico está dentro de su rango."}
        </p>
      ) : (
        <ul className="problemas">
          {problemas.map((p, i) => (
            <li key={i} className={p.nivel === "aviso" ? "aviso" : undefined}>
              <div className="t">{p.fecha ? <a href={`#dia-${p.fecha}`}>{p.t}</a> : p.t}</div>
              {p.r && <div className="r">{p.r}</div>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CargaPorMedico({
  cal,
  editable,
  acciones,
}: {
  cal: TCalendario;
  editable: boolean;
  acciones: ReturnType<typeof useAccionesCalendario>;
}) {
  const [editando, setEditando] = useState<number | null>(null);
  const diasEspeciales = (id: number) => {
    let medio = 0;
    let doble = 0;
    for (const d of cal.dias) {
      const n = mitadesDe(cal, id, d.fecha).size;
      if (n === 3) medio++;
      if (n === 4) doble++;
    }
    return { medio, doble };
  };
  const medicos = cal.medicos.filter((m) => m.activo || m.asignado > 0);
  // Según la presencia no hay rangos: ni columna, ni ajuste del mes, ni «fuera de rango».
  const rangos = cal.carga_por_rangos;

  return (
    <section className="panel">
      <h2>Carga por médico</h2>
      <p className="entradilla">
        {rangos
          ? "Turnos del mes frente al rango de cada médico, ya ajustado por sus ausencias."
          : "Turnos del mes de cada médico: trabaja todos los días salvo ausencia."}{" "}
        Arrastra un nombre al calendario para añadirlo a un turno.
      </p>
      <div className="tabla-desplazable">
        <table>
          <thead>
            <tr>
              <th>Médico</th>
              <th className="n">Total</th>
              <th className="n">M</th>
              <th className="n">T</th>
              {rangos && <th className="n">Rango</th>}
              <th className="n">Días 1½</th>
              <th className="n">Dobles</th>
              <th className="n" title="Tardes de urgencias en el mes">Urg.</th>
              <th className="n" title="Tardes de domicilios en el mes">Dom.</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {medicos.map((m) => {
              const fuera = rangos && m.con_carga && (m.asignado < m.minimo! || m.asignado > m.maximo!);
              const { medio, doble } = diasEspeciales(m.id);
              return (
                <tr key={m.id}>
                  <td>
                    <Ficha
                      id={`resumen|${m.id}`}
                      origen={{ tipo: "resumen", medico: m.id }}
                      texto={m.nombre}
                      color={m.color}
                      titulo={`${m.nombre}: arrastra a un turno para añadirlo`}
                      editable={editable && m.activo}
                    />
                  </td>
                  <td className={`n ${fuera ? "mal" : ""}`}>{formatearMedios(m.asignado)}</td>
                  <td className="n">{formatearMedios(m.asignado_manana)}</td>
                  <td className="n">{formatearMedios(m.asignado_tarde)}</td>
                  {rangos && (
                    <td className="n">
                      {m.con_carga ? (
                        <>
                          {formatearMedios(m.minimo!)}–{formatearMedios(m.maximo!)}
                          {m.carga_manual && <span title="Rango ajustado a mano para este mes"> ✎</span>}
                        </>
                      ) : (
                        <span className="nota">sin carga</span>
                      )}
                    </td>
                  )}
                  <td className="n">{medio}</td>
                  <td className="n">{doble}</td>
                  <td className="n" title={`Puede trabajar ${m.tardes_disponibles ?? 0} tardes este mes`}>
                    {m.urgencias ?? 0}
                  </td>
                  <td className="n" title={`Puede trabajar ${m.tardes_disponibles ?? 0} tardes este mes`}>
                    {m.domicilios ?? 0}
                  </td>
                  <td>
                    {rangos && m.con_carga && editable && (
                      <button
                        type="button"
                        className="enlace"
                        onClick={() => setEditando(editando === m.id ? null : m.id)}
                        aria-label={`Ajustar el rango de ${m.nombre}`}
                        title="Ajustar el rango de este mes"
                      >
                        ✎
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editando !== null && (
        <EditarRango
          medico={cal.medicos.find((m) => m.id === editando)!}
          guardar={(carga) => acciones.cargaManual.mutate({ medico: editando, carga }, { onSuccess: () => setEditando(null) })}
        />
      )}
    </section>
  );
}

function EditarRango({
  medico,
  guardar,
}: {
  medico: MedicoCalendario;
  guardar: (carga: { minimo: number | null; maximo: number | null }) => void;
}) {
  const [minimo, setMinimo] = useState<number | null>(medico.minimo ?? null);
  const [maximo, setMaximo] = useState<number | null>(medico.maximo ?? null);
  return (
    <div className={css.editarRango}>
      <p className="nota">
        Rango de {medico.nombre} solo para este mes. Según sus ausencias le corresponden{" "}
        {formatearMedios(medico.minimo_calculado!)}–{formatearMedios(medico.maximo_calculado!)} turnos.
      </p>
      <div className="fila-formulario">
        <CampoTurnos etiqueta="Mínimo" medios={minimo} onChange={setMinimo} />
        <CampoTurnos etiqueta="Máximo" medios={maximo} onChange={setMaximo} />
        <button
          type="button"
          className="btn primario"
          onClick={() => guardar({ minimo, maximo })}
          disabled={minimo === null || maximo === null || maximo < minimo}
        >
          Guardar rango
        </button>
        {medico.carga_manual && (
          <button type="button" className="btn" onClick={() => guardar({ minimo: null, maximo: null })}>
            Volver al calculado
          </button>
        )}
      </div>
    </div>
  );
}

/** Insignia de urgencias (luz de emergencia, roja) o domicilios (casa, azul). */
function InsigniaRol({ rol, decorativa = false }: { rol: Rol; decorativa?: boolean }) {
  const titulo = decorativa ? undefined : NOMBRE_ROL[rol];
  return (
    <span className={`${css.rol} ${css[`rol_${rol}`]}`} title={titulo}>
      {rol === "URGENCIAS" ? <IconoEmergencia titulo={titulo} /> : <IconoCasa titulo={titulo} />}
    </span>
  );
}
