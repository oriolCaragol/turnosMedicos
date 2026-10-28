import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCalendario } from "../api/consultas";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { formatearFecha, mesSiguiente, nombreMes } from "../util/fechas";
import { CalendarioSoloLectura } from "./Calendario";
import css from "./Imprimir.module.css";

/**
 * El calendario del mes para imprimir (o guardar como PDF) con el mismo formato que la
 * vista «Calendario»: semanas en filas, mañana y tarde en cada día. A4 horizontal. Con
 * `?auto=1` abre el diálogo de impresión al cargar. Lo usan el planificador y los médicos.
 */
export function ImprimirCalendario() {
  const [parametros] = useSearchParams();
  const mes = parametros.get("mes") ?? mesSiguiente();
  const [anio, numMes] = mes.split("-").map(Number);
  const calendario = useCalendario(anio, numMes);
  const impreso = useRef(false);

  useEffect(() => {
    if (calendario.isSuccess && parametros.get("auto") === "1" && !impreso.current) {
      impreso.current = true;
      setTimeout(() => window.print(), 300);
    }
  }, [calendario.isSuccess, parametros]);

  if (calendario.isError) return <MensajeError error={calendario.error} />;
  if (!calendario.data) return <Cargando />;
  const cal = calendario.data;
  const titulo = nombreMes(mes).replace(/^./, (c) => c.toUpperCase());

  return (
    <div className={css.pagina}>
      <div className={`${css.herramientas} no-imprimir`}>
        <Link to={`/?mes=${mes}`}>← Volver</Link>
        <button type="button" className="btn primario" onClick={() => window.print()}>
          Imprimir / Guardar como PDF
        </button>
      </div>
      <header className={css.cabecera}>
        <h1>Turnos — {titulo}</h1>
        <p className={cal.estado === "PUBLICADO" ? css.publicado : css.borrador}>
          {cal.estado === "PUBLICADO" && cal.publicado_en
            ? `Publicado el ${formatearFecha(cal.publicado_en.slice(0, 10))}`
            : "BORRADOR — calendario no publicado"}
        </p>
      </header>
      {cal.estado === "SIN_GENERAR" ? (
        <p>Este mes aún no tiene calendario.</p>
      ) : (
        <div className={css.calendarioImpreso}>
          <CalendarioSoloLectura cal={cal} vistaFija="cuadricula" />
        </div>
      )}
    </div>
  );
}
