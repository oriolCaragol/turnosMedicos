import { useEffect, useRef, useState } from "react";

import { useAjustes, useBorrarAusencia, useBorrarMedico, useCrearAusencia, useGuardarReglas, useModificarAusencia, useModificarMedico, useReglas } from "../api/consultas";
import type { Ausencia, Medico, Turno } from "../api/tipos";
import { CampoTurnos } from "../componentes/CampoTurnos";
import { CuadriculaElegibilidad } from "../componentes/CuadriculaElegibilidad";
import { MensajeError, useTostada } from "../componentes/Mensajes";
import { DIAS_CORTOS, formatearMedios, NOMBRE_JORNADA, NOMBRE_PREFERENCIA, NOMBRE_TURNO } from "../util/textos";
import { useAutoguardado } from "../util/useAutoguardado";
import { estiloColor } from "../util/colores";
import { CajonReglas } from "./CajonReglas";
import { SelectorColor } from "./SelectorColor";
import { aFormulario, aGuardar, cargaValida, type Formulario } from "./formulario";
import css from "./TarjetaMedico.module.css";

/** Tarjeta de un médico: datos, cuadrícula de turnos, carga mensual y ausencias. Se guarda sola. */
export function TarjetaMedico({ medico, desde, ausencias }: { medico: Medico; desde: string; ausencias: Ausencia[] }) {
  const reglas = useReglas(medico.id, desde);
  // Según la presencia no hay rangos: ni se piden ni se avisa de que falten.
  const conRangos = useAjustes().data?.modo_carga !== "PRESENCIA";
  const guardado = useAutoguardado(useGuardarReglas(medico.id));
  const [f, setF] = useState<Formulario | null>(null);
  const [cajon, setCajon] = useState(false);
  const cargado = useRef("");
  const { enviar, reiniciar } = guardado;

  // Carga el formulario al abrir o al cambiar de mes; después manda lo que edita el usuario.
  // Espera a la lectura fresca (no a la copia en caché), que a su vez espera a cualquier
  // guardado en curso: si no, al volver a la pestaña se verían las reglas de antes.
  useEffect(() => {
    const clave = `${medico.id}|${desde}`;
    if (reglas.data && !reglas.isFetching && cargado.current !== clave) {
      cargado.current = clave;
      reiniciar();
      setF(aFormulario(reglas.data));
    }
  }, [reglas.data, reglas.isFetching, medico.id, desde, reiniciar]);

  // Al cambiar de mes, lo pendiente del mes anterior se guarda antes de cargar el nuevo.
  useEffect(() => () => enviar(), [desde, enviar]);

  const editar = (nuevo: Formulario) => {
    setF(nuevo);
    guardado.programar(aGuardar(nuevo, desde));
  };

  const sinCarga = f !== null && f.minimo === null && f.maximo === null;
  const avisoCarga = !f || !conRangos || cargaValida(f)
    ? ""
    : sinCarga || f.minimo === null || f.maximo === null
      ? "Falta la carga mensual: sin ella no se le asignan turnos."
      : "La carga no se guarda: el máximo no puede ser menor que el mínimo.";
  const estado = !f
    ? "Cargando…"
    : guardado.estado === "pendiente" || guardado.estado === "guardando"
      ? "Guardando…"
      : guardado.estado === "error"
        ? "No se ha podido guardar."
        : guardado.estado === "ok"
          ? `Guardado.${avisoCarga ? ` ${avisoCarga}` : ""}`
          : reglas.data?.vigente_desde
            ? avisoCarga || "Reglas guardadas."
            : `Sin reglas para este mes.${avisoCarga ? ` ${avisoCarga}` : ""}`;

  return (
    <article className={`${css.tarjeta} ${medico.activo ? "" : css.inactiva}`} data-medico={medico.codigo}>
      <Datos medico={medico} />
      {f && (
        <>
          <CuadriculaElegibilidad valor={f.elegibilidad} onChange={(elegibilidad) => editar({ ...f, elegibilidad })} />
          <div className="fila-formulario">
            {conRangos && (
              <>
                <CampoTurnos
                  etiqueta="Turnos/mes mín."
                  medios={f.minimo}
                  resaltar={f.minimo === null}
                  onChange={(minimo) => editar({ ...f, minimo })}
                />
                <CampoTurnos
                  etiqueta="Turnos/mes máx."
                  medios={f.maximo}
                  resaltar={f.maximo === null}
                  onChange={(maximo) => editar({ ...f, maximo })}
                />
              </>
            )}
            <button type="button" className="btn pequeno" onClick={() => setCajon(true)}>
              Más reglas…
            </button>
          </div>
          <ResumenExtra f={f} conRangos={conRangos} />
          <p className={`nota ${avisoCarga ? css.pendiente : ""}`} aria-live="polite">
            {estado}
          </p>
          <MensajeError error={guardado.error} />
          {cajon && (
            <CajonReglas
              nombre={medico.nombre}
              f={f}
              setF={editar}
              estado={estado}
              conRangos={conRangos}
              cerrar={() => setCajon(false)}
            />
          )}
        </>
      )}
      <Ausencias medico={medico} desde={desde} ausencias={ausencias} />
    </article>
  );
}

function Datos({ medico }: { medico: Medico }) {
  const modificar = useModificarMedico(medico.id);
  const borrar = useBorrarMedico();
  const tostada = useTostada();
  const [nombre, setNombre] = useState(medico.nombre);
  const [codigo, setCodigo] = useState(medico.codigo);
  useEffect(() => {
    setNombre(medico.nombre);
    setCodigo(medico.codigo);
  }, [medico.nombre, medico.codigo]);

  const guardar = (cambios: Partial<Medico>) => {
    const datos = { nombre: medico.nombre, codigo: medico.codigo, activo: medico.activo, color: medico.color, ...cambios };
    if (datos.nombre.trim() && datos.codigo.trim()) modificar.mutate(datos, { onSuccess: () => tostada("Guardado") });
  };

  return (
    <>
      <div className={css.fila}>
        <SelectorColor color={medico.color} nombre={medico.nombre} onChange={(color) => guardar({ color })} />
        <input
          className={css.nombre}
          style={estiloColor(medico.color)}
          aria-label="Nombre del médico"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onBlur={() => nombre.trim() && nombre !== medico.nombre && guardar({ nombre: nombre.trim() })}
        />
        <input
          className={css.codigo}
          aria-label="Código"
          title="Código corto (iniciales)"
          maxLength={6}
          value={codigo}
          onChange={(e) => setCodigo(e.target.value.toUpperCase())}
          onBlur={() => codigo.trim() && codigo !== medico.codigo && guardar({ codigo: codigo.trim() })}
        />
        <button
          type="button"
          className="x"
          aria-label={`Borrar a ${medico.nombre}`}
          title="Borrar médico"
          onClick={() => {
            if (confirm(`¿Borrar a ${medico.nombre}? Si ya tiene turnos asignados, desactívalo en su lugar.`)) borrar.mutate(medico.id);
          }}
        >
          ×
        </button>
      </div>
      <label className="campo-casilla nota">
        <input type="checkbox" checked={medico.activo} onChange={(e) => guardar({ activo: e.target.checked })} />
        Activo{medico.activo ? "" : " — no se le asignan turnos"}
      </label>
      <MensajeError error={modificar.error ?? borrar.error} />
    </>
  );
}

function ResumenExtra({ f, conRangos }: { f: Formulario; conRangos: boolean }) {
  const partes: string[] = [];
  for (const [d, tipo] of Object.entries(f.jornadas)) if (tipo) partes.push(`${DIAS_CORTOS[Number(d)]}: ${NOMBRE_JORNADA[tipo]}`);
  for (const t of (conRangos ? ["MANANA", "TARDE"] : []) as Turno[]) {
    const { minimo, maximo } = f.porTurno[t];
    if (minimo !== null || maximo !== null)
      partes.push(`${NOMBRE_TURNO[t]}s ${formatearMedios(minimo ?? 0)}–${maximo !== null ? formatearMedios(maximo) : "∞"}`);
  }
  for (const [k, p] of Object.entries(f.preferencias)) {
    if (!p) continue;
    const [d, t] = k.split("-");
    partes.push(`${NOMBRE_PREFERENCIA[p]} ${DIAS_CORTOS[Number(d)]} ${NOMBRE_TURNO[t as Turno].toLowerCase()}`);
  }
  return partes.length ? <p className="nota">{partes.join(" · ")}</p> : null;
}

const TURNO_AUSENCIA = [
  ["", "Día completo"],
  ["MANANA", "Solo mañanas"],
  ["TARDE", "Solo tardes"],
] as const;

function Ausencias({ medico, desde, ausencias }: { medico: Medico; desde: string; ausencias: Ausencia[] }) {
  const crear = useCrearAusencia();
  const modificar = useModificarAusencia();
  const borrar = useBorrarAusencia();

  const cambiar = (a: Ausencia, cambios: Partial<Ausencia>) => {
    const nueva = { ...a, ...cambios };
    if (!nueva.desde || !nueva.hasta) return;
    if (nueva.hasta < nueva.desde) nueva.hasta = nueva.desde;
    modificar.mutate(nueva);
  };

  return (
    <div className={css.ausencias}>
      <span className="etiqueta">Ausencias</span>
      {ausencias.length === 0 && <span className="nota">Ninguna desde este mes</span>}
      {ausencias.map((a) => (
        <div key={a.id} className={css.ausencia}>
          <input type="date" aria-label="Desde" value={a.desde} onChange={(e) => cambiar(a, { desde: e.target.value })} />
          <span>a</span>
          <input type="date" aria-label="Hasta" value={a.hasta} min={a.desde} onChange={(e) => cambiar(a, { hasta: e.target.value })} />
          <select
            aria-label="Turnos de la ausencia"
            value={a.turno ?? ""}
            onChange={(e) => cambiar(a, { turno: (e.target.value || null) as Turno | null })}
          >
            {TURNO_AUSENCIA.map(([v, t]) => (
              <option key={v} value={v}>
                {t}
              </option>
            ))}
          </select>
          <button type="button" className="x" aria-label="Quitar ausencia" onClick={() => borrar.mutate(a.id)}>
            ×
          </button>
        </div>
      ))}
      <div>
        <button
          type="button"
          className="btn pequeno"
          disabled={!medico.activo}
          onClick={() => crear.mutate({ medico_id: medico.id, desde, hasta: desde, turno: null })}
        >
          Añadir ausencia
        </button>
      </div>
      <MensajeError error={crear.error ?? modificar.error ?? borrar.error} />
    </div>
  );
}
