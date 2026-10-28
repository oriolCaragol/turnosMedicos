import { useState } from "react";

import { useCrearSolicitud } from "../api/solicitudes";
import type { Calendario, Turno } from "../api/tipos";
import { MensajeError, useTostada } from "../componentes/Mensajes";
import { fechaCorta } from "../util/fechas";
import { NOMBRE_TURNO } from "../util/textos";
import { diasDe, type DiaMedico } from "./dias";

type Cambio = "NO_PUEDO" | "OTRA_MITAD" | "INTERCAMBIO";

/**
 * Proponer un cambio sobre un turno propio de un mes publicado (diseño del modo
 * servidor, 6.4): no puedo, prefiero la otra mitad del día o intercambiarlo.
 */
export function ProponerCambio({
  cal,
  medico,
  dia,
  cerrar,
}: {
  cal: Calendario;
  medico: number;
  dia: DiaMedico;
  cerrar: () => void;
}) {
  const crear = useCrearSolicitud();
  const tostada = useTostada();
  const [turno, setTurno] = useState<Turno>(dia.turnos[0].turno);
  const [cambio, setCambio] = useState<Cambio>("NO_PUEDO");
  const [companero, setCompanero] = useState<number | null>(null);
  const [suyo, setSuyo] = useState("");
  const [comentario, setComentario] = useState("");

  const otro: Turno = turno === "MANANA" ? "TARDE" : "MANANA";
  const yaHaceElOtro = dia.turnos.some((t) => t.turno === otro);
  const companeros = cal.medicos.filter((m) => m.id !== medico).sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  const turnosDelCompanero = companero
    ? diasDe(cal, companero).flatMap((d) => d.turnos.map((t) => ({ valor: `${d.fecha}|${t.turno}`, d, t })))
    : [];

  const enviar = () => {
    const [fecha_companero, turno_companero] = suyo.split("|");
    crear.mutate(
      {
        propuesta: {
          tipo: "CALENDARIO",
          cambio,
          fecha: dia.fecha,
          turno,
          ...(cambio === "INTERCAMBIO"
            ? { companero_id: companero, fecha_companero, turno_companero: turno_companero as Turno }
            : {}),
        },
        comentario,
      },
      {
        onSuccess: () => {
          tostada(cambio === "INTERCAMBIO" ? "Enviada: primero la verá tu compañero" : "Solicitud enviada");
          cerrar();
        },
      },
    );
  };

  const completo = cambio !== "INTERCAMBIO" || (companero !== null && suyo !== "");
  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", gap: 10, gridColumn: "1 / -1" }}>
      <strong>Proponer un cambio · {fechaCorta(dia.fecha)}</strong>
      {dia.turnos.length > 1 && (
        <label className="campo">
          <span>Turno</span>
          <select value={turno} onChange={(e) => setTurno(e.target.value as Turno)}>
            {dia.turnos.map((t) => (
              <option key={t.turno} value={t.turno}>
                {NOMBRE_TURNO[t.turno]}
              </option>
            ))}
          </select>
        </label>
      )}
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
        <legend className="etiqueta">¿Qué propones?</legend>
        {(
          [
            ["NO_PUEDO", `No puedo hacer la ${NOMBRE_TURNO[turno].toLowerCase()}`],
            ...(yaHaceElOtro ? [] : [["OTRA_MITAD", `Prefiero la ${NOMBRE_TURNO[otro].toLowerCase()} ese día`]]),
            ["INTERCAMBIO", "Intercambiarla con un compañero"],
          ] as [Cambio, string][]
        ).map(([valor, texto]) => (
          <label key={valor} className="campo-casilla">
            <input type="radio" name={`cambio-${dia.fecha}`} checked={cambio === valor} onChange={() => setCambio(valor)} />
            {texto}
          </label>
        ))}
      </fieldset>
      {cambio === "INTERCAMBIO" && (
        <>
          <label className="campo">
            <span>Compañero</span>
            <select
              value={companero ?? ""}
              onChange={(e) => {
                setCompanero(e.target.value ? Number(e.target.value) : null);
                setSuyo("");
              }}
            >
              <option value="">Elige…</option>
              {companeros.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nombre}
                </option>
              ))}
            </select>
          </label>
          {companero !== null && (
            <label className="campo">
              <span>Su turno que harías tú</span>
              <select value={suyo} onChange={(e) => setSuyo(e.target.value)}>
                <option value="">Elige…</option>
                {turnosDelCompanero.map(({ valor, d, t }) => (
                  <option key={valor} value={valor}>
                    {fechaCorta(d.fecha)} · {NOMBRE_TURNO[t.turno]}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}
      <label className="campo">
        <span>Comentario para el planificador (opcional)</span>
        <input value={comentario} onChange={(e) => setComentario(e.target.value)} />
      </label>
      <div className="acciones">
        <button type="button" className="btn primario" disabled={!completo || crear.isPending} onClick={enviar}>
          Enviar la propuesta
        </button>
        <button type="button" className="btn" onClick={cerrar}>
          Cancelar
        </button>
      </div>
      <MensajeError error={crear.error} />
    </div>
  );
}
