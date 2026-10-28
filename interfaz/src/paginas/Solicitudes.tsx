/**
 * Bandeja de solicitudes del planificador (diseño del modo servidor, 6.4): qué cambia,
 * qué efectos tendría aprobarla, y aprobar, rechazar o marcar como resuelta.
 */
import { useState } from "react";

import { useEfectos, useResolver, useSolicitudes } from "../api/solicitudes";
import type { Solicitud } from "../api/tipos";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { TarjetaSolicitud } from "../componentes/TarjetaSolicitud";

function Efectos({ solicitud }: { solicitud: Solicitud }) {
  const efectos = useEfectos(solicitud.id, solicitud.estado === "PENDIENTE");
  if (solicitud.estado !== "PENDIENTE") return null;
  if (efectos.isPending) return <p className="nota">Calculando qué pasaría al aprobarla…</p>;
  if (efectos.isError) return <MensajeError error={efectos.error} />;
  const { avisos, meses } = efectos.data;
  return (
    <div className="mensaje mensaje-aviso" data-efectos>
      {avisos.length === 0 && meses.length === 0 && <p>Aprobarla no produce avisos nuevos en el calendario.</p>}
      {avisos.length > 0 && (
        <>
          <p>Al aprobarla:</p>
          <ul>
            {avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </>
      )}
      {meses.map((m) => (
        <p key={m}>Afecta a {m}: revisa el calendario (no se regenera solo).</p>
      ))}
    </div>
  );
}

function Pendiente({ solicitud }: { solicitud: Solicitud }) {
  const resolver = useResolver();
  const tostada = useTostada();
  const [comentario, setComentario] = useState("");
  const accion = (accion: "aprobar" | "rechazar", aplicar = true, mensaje = "") =>
    resolver.mutate({ id: solicitud.id, accion, comentario, aplicar }, { onSuccess: () => tostada(mensaje) });

  return (
    <TarjetaSolicitud solicitud={solicitud} conMedico>
      <Efectos solicitud={solicitud} />
      {solicitud.estado === "PENDIENTE" && (
        <>
          <input
            aria-label="Comentario para el médico"
            placeholder="Comentario para el médico (opcional; para rechazar, el motivo)"
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
          />
          <div className="acciones">
            <button
              type="button"
              className="btn primario"
              disabled={resolver.isPending}
              onClick={() => accion("aprobar", true, "Aprobada y aplicada")}
            >
              Aprobar
            </button>
            <button
              type="button"
              className="btn peligro"
              disabled={resolver.isPending}
              onClick={() => accion("rechazar", true, "Rechazada")}
            >
              Rechazar
            </button>
            {solicitud.tipo === "CALENDARIO" && (
              <button
                type="button"
                className="btn"
                disabled={resolver.isPending}
                title="La has resuelto tú de otra forma en el calendario"
                onClick={() => accion("aprobar", false, "Marcada como resuelta")}
              >
                Resuelta de otra forma
              </button>
            )}
          </div>
          <MensajeError error={resolver.error} />
        </>
      )}
    </TarjetaSolicitud>
  );
}

export function Solicitudes() {
  const solicitudes = useSolicitudes();
  if (solicitudes.isError) return <MensajeError error={solicitudes.error} />;
  if (!solicitudes.data) return <Cargando />;
  const abiertas = solicitudes.data.filter((s) => s.estado === "PENDIENTE" || s.estado === "ESPERA_COMPANERO");
  const resueltas = solicitudes.data.filter((s) => !abiertas.includes(s));

  return (
    <>
      <section className="panel">
        <h2>Solicitudes pendientes</h2>
        <p className="entradilla">
          Lo que proponen los médicos: disponibilidad semanal, ausencias y cambios en meses publicados. Al aprobar, el cambio
          se aplica (en un mes publicado, sin reabrirlo) y el médico lo ve en el momento.
        </p>
        {abiertas.length === 0 ? (
          <p className="vacio-ok">No hay solicitudes pendientes.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {abiertas.map((s) => (
              <Pendiente key={s.id} solicitud={s} />
            ))}
          </div>
        )}
      </section>
      {resueltas.length > 0 && (
        <section className="panel">
          <details>
            <summary>
              <h2 style={{ display: "inline" }}>Historial ({resueltas.length})</h2>
            </summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
              {resueltas.map((s) => (
                <TarjetaSolicitud key={s.id} solicitud={s} conMedico />
              ))}
            </div>
          </details>
        </section>
      )}
    </>
  );
}
