import { useState } from "react";

import { useCrearSolicitud } from "../api/solicitudes";
import type { Ausencia, Turno } from "../api/tipos";
import { CuadriculaElegibilidad, type Cuadricula } from "../componentes/CuadriculaElegibilidad";
import { MensajeError, useTostada } from "../componentes/Mensajes";
import { desplazarMes } from "../util/mes";
import { hoy, mesActual, nombreMes } from "../util/fechas";
import { NOMBRE_TURNO } from "../util/textos";

const mayuscula = (t: string) => t.replace(/^./, (c) => c.toUpperCase());

/** Proponer otra disponibilidad semanal, desde un mes (sobre una copia de la actual). */
export function ProponerDisponibilidad({ actual, cerrar }: { actual: Cuadricula; cerrar: () => void }) {
  const crear = useCrearSolicitud();
  const tostada = useTostada();
  const [cuadricula, setCuadricula] = useState<Cuadricula>(actual);
  const meses = [0, 1, 2, 3].map((n) => desplazarMes(mesActual(), n));
  const [desde, setDesde] = useState(meses[1]);
  const [comentario, setComentario] = useState("");
  const cambiada = Object.entries(cuadricula).some(([k, v]) => actual[k as keyof Cuadricula] !== v);

  const enviar = () =>
    crear.mutate(
      {
        propuesta: {
          tipo: "DISPONIBILIDAD",
          desde: `${desde}-01`,
          elegibilidad: Object.entries(cuadricula).map(([k, valor]) => {
            const [dia, turno] = k.split("-");
            return { dia_semana: Number(dia), turno: turno as Turno, valor };
          }),
        },
        comentario,
      },
      {
        onSuccess: () => {
          tostada("Propuesta enviada al planificador");
          cerrar();
        },
      },
    );

  return (
    <section className="panel" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h2>Proponer otra disponibilidad</h2>
      <p className="nota">Toca cada casilla para cambiarla. El planificador la revisará antes de aplicarla.</p>
      <CuadriculaElegibilidad valor={cuadricula} onChange={setCuadricula} atajos={false} />
      <label className="campo">
        <span>Desde</span>
        <select value={desde} onChange={(e) => setDesde(e.target.value)}>
          {meses.map((m) => (
            <option key={m} value={m}>
              {mayuscula(nombreMes(m))}
            </option>
          ))}
        </select>
      </label>
      <label className="campo">
        <span>Comentario (opcional)</span>
        <input
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
          placeholder="p. ej. por el horario del colegio"
        />
      </label>
      <div className="acciones">
        <button type="button" className="btn primario" disabled={!cambiada || crear.isPending} onClick={enviar}>
          Enviar la propuesta
        </button>
        <button type="button" className="btn" onClick={cerrar}>
          Cancelar
        </button>
      </div>
      <MensajeError error={crear.error} />
    </section>
  );
}

/** Pedir una ausencia nueva. */
export function PedirAusencia({ cerrar }: { cerrar: () => void }) {
  const crear = useCrearSolicitud();
  const tostada = useTostada();
  const [desde, setDesde] = useState(hoy());
  const [hasta, setHasta] = useState(hoy());
  const [turno, setTurno] = useState<Turno | "">("");
  const [comentario, setComentario] = useState("");

  const enviar = () =>
    crear.mutate(
      { propuesta: { tipo: "AUSENCIA", accion: "CREAR", desde, hasta, turno: turno || null }, comentario },
      {
        onSuccess: () => {
          tostada("Ausencia pedida");
          cerrar();
        },
      },
    );

  return (
    <section className="panel" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h2>Pedir una ausencia</h2>
      <div className="fila-formulario">
        <label className="campo">
          <span>Desde</span>
          <input
            type="date"
            value={desde}
            onChange={(e) => {
              setDesde(e.target.value);
              if (e.target.value > hasta) setHasta(e.target.value);
            }}
          />
        </label>
        <label className="campo">
          <span>Hasta</span>
          <input type="date" value={hasta} min={desde} onChange={(e) => setHasta(e.target.value)} />
        </label>
        <label className="campo">
          <span>Qué</span>
          <select value={turno} onChange={(e) => setTurno(e.target.value as Turno | "")}>
            <option value="">Día completo</option>
            <option value="MANANA">Solo mañana</option>
            <option value="TARDE">Solo tarde</option>
          </select>
        </label>
      </div>
      <label className="campo">
        <span>Comentario (opcional)</span>
        <input value={comentario} onChange={(e) => setComentario(e.target.value)} />
      </label>
      <div className="acciones">
        <button type="button" className="btn primario" disabled={!desde || !hasta || crear.isPending} onClick={enviar}>
          Pedir la ausencia
        </button>
        <button type="button" className="btn" onClick={cerrar}>
          Cancelar
        </button>
      </div>
      <MensajeError error={crear.error} />
    </section>
  );
}

/** Pedir que se anule una ausencia propia. */
export function AnularAusencia({ ausencia }: { ausencia: Ausencia }) {
  const crear = useCrearSolicitud();
  const tostada = useTostada();
  return (
    <button
      type="button"
      className="btn pequeno"
      disabled={crear.isPending}
      onClick={() =>
        confirm("¿Pedir al planificador que anule esta ausencia?") &&
        crear.mutate(
          { propuesta: { tipo: "AUSENCIA", accion: "ANULAR", ausencia_id: ausencia.id }, comentario: "" },
          { onSuccess: () => tostada("Anulación pedida") },
        )
      }
      title={ausencia.turno ? `Solo ${NOMBRE_TURNO[ausencia.turno].toLowerCase()}` : "Día completo"}
    >
      Pedir anularla
    </button>
  );
}
