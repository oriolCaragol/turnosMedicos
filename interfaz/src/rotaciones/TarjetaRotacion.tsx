import { useEffect, useRef, useState } from "react";

import { useBorrarRotacion, useGuardarRotacion } from "../api/consultas";
import type { Medico, Rotacion, RotacionEntrada, Turno } from "../api/tipos";
import { MensajeError } from "../componentes/Mensajes";
import { estiloColor } from "../util/colores";
import { formatearFecha, nombreMes } from "../util/fechas";
import { DIAS, DIAS_CORTOS, NOMBRE_TURNO, TURNOS } from "../util/textos";
import { useAutoguardado } from "../util/useAutoguardado";
import css from "./TarjetaRotacion.module.css";
import { lunesDe, semanasDelMes, titularDeLaSemana } from "./semanas";

function sinId(r: Rotacion): RotacionEntrada {
  return { nombre: r.nombre, desde: r.desde, activa: r.activa, medicos: r.medicos, huecos: r.huecos };
}

/** Tarjeta de un turno rotativo; se guarda sola. */
export function TarjetaRotacion({ rotacion, medicos, mes }: { rotacion: Rotacion; medicos: Medico[]; mes: string }) {
  const guardado = useAutoguardado(useGuardarRotacion(rotacion.id));
  const borrar = useBorrarRotacion();
  const [r, setR] = useState<RotacionEntrada>(() => sinId(rotacion));
  const id = useRef(rotacion.id);
  useEffect(() => {
    if (id.current !== rotacion.id) {
      id.current = rotacion.id;
      setR(sinId(rotacion));
    }
  }, [rotacion]);

  const editar = (cambios: Partial<RotacionEntrada>) => {
    const nueva = { ...r, ...cambios };
    setR(nueva);
    if (nueva.nombre.trim() && nueva.desde) guardado.programar({ ...nueva, nombre: nueva.nombre.trim() });
  };

  const porId = new Map(medicos.map((m) => [m.id, m]));
  const miembros = r.medicos ?? [];
  const huecos = r.huecos ?? [];
  const tiene = (d: number, t: Turno) => huecos.some((h) => h.dia_semana === d && h.turno === t);
  const alternar = (d: number, t: Turno) =>
    editar({
      huecos: tiene(d, t)
        ? huecos.filter((h) => !(h.dia_semana === d && h.turno === t))
        : [...huecos, { dia_semana: d, turno: t }],
    });
  const mover = (i: number, delta: number) => {
    const lista = [...miembros];
    [lista[i], lista[i + delta]] = [lista[i + delta], lista[i]];
    editar({ medicos: lista });
  };
  const incompleta = miembros.length < 2 || huecos.length === 0;
  const estado =
    guardado.estado === "pendiente" || guardado.estado === "guardando"
      ? "Guardando…"
      : guardado.estado === "error"
        ? "No se ha podido guardar."
        : guardado.estado === "ok"
          ? "Guardado."
          : "";

  return (
    <article className={`${css.tarjeta} ${r.activa ? "" : css.inactiva}`} data-rotacion={rotacion.id}>
      <div className={css.fila}>
        <input
          className={css.nombre}
          aria-label="Nombre del turno rotativo"
          value={r.nombre}
          onChange={(e) => editar({ nombre: e.target.value })}
        />
        <button
          type="button"
          className="x"
          aria-label={`Borrar ${r.nombre}`}
          title="Borrar turno rotativo"
          onClick={() => confirm(`¿Borrar el turno rotativo «${r.nombre}»?`) && borrar.mutate(rotacion.id)}
        >
          ×
        </button>
      </div>
      <label className="campo-casilla nota">
        <input type="checkbox" checked={r.activa} onChange={(e) => editar({ activa: e.target.checked })} />
        Activo{r.activa ? "" : " — no se aplica al generar"}
      </label>

      <div>
        <span className="etiqueta">Médicos, por orden</span>
        <ol className={css.miembros}>
          {miembros.map((m, i) => (
            <li key={m}>
              <span className={css.orden}>{i + 1}.</span>
              <span className={css.ficha} style={estiloColor(porId.get(m)?.color)}>
                {porId.get(m)?.nombre ?? `Médico ${m}`}
              </span>
              <span className={css.botones}>
                <button type="button" className="x" disabled={i === 0} aria-label="Subir" onClick={() => mover(i, -1)}>
                  ↑
                </button>
                <button
                  type="button"
                  className="x"
                  disabled={i === miembros.length - 1}
                  aria-label="Bajar"
                  onClick={() => mover(i, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="x"
                  aria-label={`Quitar a ${porId.get(m)?.nombre ?? m}`}
                  onClick={() => editar({ medicos: miembros.filter((x) => x !== m) })}
                >
                  ×
                </button>
              </span>
            </li>
          ))}
        </ol>
        <select
          aria-label="Añadir médico al turno rotativo"
          value=""
          onChange={(e) => e.target.value && editar({ medicos: [...miembros, Number(e.target.value)] })}
        >
          <option value="">Añadir médico…</option>
          {medicos
            .filter((m) => m.activo && !miembros.includes(m.id))
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre}
              </option>
            ))}
        </select>
      </div>

      <div>
        <span className="etiqueta">Turnos que comparten</span>
        <div className={css.rejilla}>
          <span />
          {DIAS_CORTOS.map((d) => (
            <span key={d} className={css.dia}>
              {d}
            </span>
          ))}
          {TURNOS.map((t) => [
            <span key={t} className={`${css.turno} ${t === "MANANA" ? css.manana : css.tarde}`}>
              {t === "MANANA" ? "Mañ." : "Tar."}
            </span>,
            ...DIAS.map((dia, d) => (
              <button
                key={`${d}-${t}`}
                type="button"
                className={css.hueco}
                aria-pressed={tiene(d, t)}
                aria-label={`${dia}, ${NOMBRE_TURNO[t].toLowerCase()}`}
                onClick={() => alternar(d, t)}
              >
                {tiene(d, t) ? "✓" : ""}
              </button>
            )),
          ])}
        </div>
      </div>

      <label className="campo">
        <span>Empieza la semana del</span>
        <input type="date" value={r.desde} onChange={(e) => e.target.value && editar({ desde: e.target.value })} required />
        <span className="nota">
          Esa semana le toca al primero de la lista (semana del lunes {formatearFecha(lunesDe(r.desde))}).
        </span>
      </label>

      {incompleta ? (
        <p className={`nota ${css.aviso}`}>
          Incompleto: no se aplica hasta que tenga al menos dos médicos y un turno.
        </p>
      ) : (
        <div>
          <span className="etiqueta">{nombreMes(mes).replace(/^./, (c) => c.toUpperCase())}</span>
          <ul className={css.semanas}>
            {semanasDelMes(mes).map((lunes) => {
              const titular = titularDeLaSemana(miembros, r.desde, lunes);
              return (
                <li key={lunes}>
                  <span className="num">Semana del {formatearFecha(lunes).slice(0, 5)}</span>{" "}
                  {titular === null ? (
                    <span className="nota">aún no empieza</span>
                  ) : (
                    <span className={css.ficha} style={estiloColor(porId.get(titular)?.color)}>
                      {porId.get(titular)?.nombre ?? titular}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <p className="nota" aria-live="polite">
        {estado}
      </p>
      <MensajeError error={guardado.error ?? borrar.error} />
    </article>
  );
}
