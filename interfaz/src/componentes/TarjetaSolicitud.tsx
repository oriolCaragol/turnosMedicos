import type { ReactNode } from "react";

import { NOMBRE_ESTADO, NOMBRE_TIPO } from "../api/solicitudes";
import type { Solicitud } from "../api/tipos";
import css from "./TarjetaSolicitud.module.css";

const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Una solicitud: qué se pide, quién, cuándo, su estado y los comentarios. `children`: las acciones. */
export function TarjetaSolicitud({
  solicitud: s,
  conMedico = false,
  children,
}: {
  solicitud: Solicitud;
  conMedico?: boolean;
  children?: ReactNode;
}) {
  return (
    <article className={css.tarjeta} data-solicitud={s.id} data-estado={s.estado}>
      <header className={css.cabecera}>
        <span className="etiqueta">{NOMBRE_TIPO[s.tipo]}</span>
        <span className={`${css.estado} ${css[s.estado.toLowerCase()] ?? ""}`}>
          {s.estado === "ESPERA_COMPANERO" && s.companero ? `Esperando a ${s.companero}` : NOMBRE_ESTADO[s.estado]}
        </span>
      </header>
      {conMedico && <strong>{s.medico}</strong>}
      <ul className={css.descripcion}>
        {s.descripcion.map((linea, i) => (
          <li key={i}>{linea}</li>
        ))}
      </ul>
      {s.comentario && <p className={css.comentario}>«{s.comentario}»</p>}
      {s.respuesta_companero && (
        <p className={css.comentario}>
          {s.companero}: «{s.respuesta_companero}»
        </p>
      )}
      {s.comentario_resolucion && (
        <p className={css.resolucion}>
          {s.resuelta_por ? `${s.resuelta_por}: ` : ""}«{s.comentario_resolucion}»
        </p>
      )}
      <p className="nota">
        Pedida el {fechaHora(s.creada)}
        {s.resuelta_en && ` · ${NOMBRE_ESTADO[s.estado].toLowerCase()} el ${fechaHora(s.resuelta_en)}`}
      </p>
      {children}
    </article>
  );
}
