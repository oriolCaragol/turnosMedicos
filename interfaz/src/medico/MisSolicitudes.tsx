import { useState } from "react";

import { useResponder, useRetirar, useSolicitudes } from "../api/solicitudes";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { TarjetaSolicitud } from "../componentes/TarjetaSolicitud";

/** «Mis solicitudes»: las suyas y los intercambios que le proponen (diseño del modo servidor, 6.4). */
export function MisSolicitudes() {
  const solicitudes = useSolicitudes();
  const retirar = useRetirar();
  const responder = useResponder();
  const tostada = useTostada();
  const [respuesta, setRespuesta] = useState<Record<number, string>>({});

  if (solicitudes.isError) return <MensajeError error={solicitudes.error} />;
  if (!solicitudes.data) return <Cargando />;
  const recibidas = solicitudes.data.filter((s) => s.me_toca_aceptar);
  const mias = solicitudes.data.filter((s) => !s.me_toca_aceptar);

  return (
    <>
      {recibidas.length > 0 && (
        <section className="panel">
          <h2>Te proponen un intercambio</h2>
          {recibidas.map((s) => (
            <TarjetaSolicitud key={s.id} solicitud={s} conMedico>
              <input
                aria-label="Comentario para tu compañero"
                placeholder="Comentario (opcional)"
                value={respuesta[s.id] ?? ""}
                onChange={(e) => setRespuesta({ ...respuesta, [s.id]: e.target.value })}
              />
              <div className="acciones">
                {[true, false].map((acepta) => (
                  <button
                    key={String(acepta)}
                    type="button"
                    className={`btn ${acepta ? "primario" : ""}`}
                    disabled={responder.isPending}
                    onClick={() =>
                      responder.mutate(
                        { id: s.id, acepta, comentario: respuesta[s.id] },
                        { onSuccess: () => tostada(acepta ? "Aceptado: ahora lo decide el planificador" : "No aceptado") },
                      )
                    }
                  >
                    {acepta ? "Aceptar" : "No aceptar"}
                  </button>
                ))}
              </div>
            </TarjetaSolicitud>
          ))}
          <MensajeError error={responder.error} />
        </section>
      )}
      <section className="panel">
        <h2>Mis solicitudes</h2>
        {mias.length === 0 ? (
          <p className="nota">
            Aún no has pedido nada. Puedes proponer cambios desde «Mis turnos» (en un turno tuyo) o desde «Mi ficha»
            (disponibilidad y ausencias).
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {mias.map((s) => (
              <TarjetaSolicitud key={s.id} solicitud={s} conMedico={!s.mia}>
                {s.mia && (s.estado === "PENDIENTE" || s.estado === "ESPERA_COMPANERO") && (
                  <div className="acciones">
                    <button
                      type="button"
                      className="btn pequeno"
                      disabled={retirar.isPending}
                      onClick={() => confirm("¿Retirar esta solicitud?") && retirar.mutate(s.id)}
                    >
                      Retirar
                    </button>
                  </div>
                )}
              </TarjetaSolicitud>
            ))}
          </div>
        )}
        <MensajeError error={retirar.error} />
      </section>
    </>
  );
}
