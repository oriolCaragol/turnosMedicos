import { Link } from "react-router-dom";

import { useCalendario } from "../api/consultas";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { CalendarioSoloLectura } from "../paginas/Calendario";

/**
 * El calendario de todo el equipo de un mes publicado (D-S2), con el mismo formato que
 * la vista «Calendario» del planificador, solo para consultar. Su nombre, resaltado.
 */
export function CalendarioEquipo({ medico, mes }: { medico: number; mes: string }) {
  const [anio, numMes] = mes.split("-").map(Number);
  const calendario = useCalendario(anio, numMes);
  if (calendario.isError) return <MensajeError error={calendario.error} />;
  if (!calendario.data) return <Cargando />;

  return (
    <>
      <section className="panel">
        <div className="barra-titulo">
          <div>
            <h2>Calendario del equipo</h2>
            <p className="nota" style={{ margin: 0 }}>
              Tu nombre aparece resaltado.
            </p>
          </div>
          <div className="acciones">
            <Link className="btn" to={`/imprimir/calendario?mes=${mes}&auto=1`}>
              Imprimir calendario / PDF
            </Link>
          </div>
        </div>
      </section>
      <CalendarioSoloLectura cal={calendario.data} resaltar={medico} />
    </>
  );
}
