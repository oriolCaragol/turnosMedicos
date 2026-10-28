import { Fragment, useState } from "react";
import { Link } from "react-router-dom";

import { useCalendario, useHorarios } from "../api/consultas";
import { useAusenciasDe } from "../api/medico";
import { NOMBRE_ROL } from "../calendario/logica";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { fechaCorta, hoy, primerDia, ultimoDia } from "../util/fechas";
import { NOMBRE_TURNO } from "../util/textos";
import { diasDe, textoTurno } from "./dias";
import { ProponerCambio } from "./ProponerCambio";
import css from "./EspacioMedico.module.css";

/** «Mis turnos»: los días que trabaja el médico en un mes publicado. */
export function MisTurnos({ medico, mes }: { medico: number; mes: string }) {
  const [anio, numMes] = mes.split("-").map(Number);
  const calendario = useCalendario(anio, numMes);
  const horarios = useHorarios();
  const ausencias = useAusenciasDe(medico, primerDia(mes), ultimoDia(mes));
  const [proponiendo, setProponiendo] = useState<string | null>(null);

  if (calendario.isError) return <MensajeError error={calendario.error} />;
  if (!calendario.data) return <Cargando />;
  const cal = calendario.data;
  const dias = diasDe(cal, medico, horarios.data);
  const yo = cal.medicos.find((m) => m.id === medico);
  const hoyIso = hoy();
  const manana = dias.filter((d) => d.turnos.some((t) => t.turno === "MANANA")).length;
  const tarde = dias.filter((d) => d.turnos.some((t) => t.turno === "TARDE")).length;

  return (
    <>
      <section className="panel">
        <dl className={css.resumen}>
          <div>
            <dt className="etiqueta">Días</dt>
            <dd>{dias.length}</dd>
          </div>
          <div>
            <dt className="etiqueta">Mañanas</dt>
            <dd>{manana}</dd>
          </div>
          <div>
            <dt className="etiqueta">Tardes</dt>
            <dd>{tarde}</dd>
          </div>
          <div>
            <dt className="etiqueta">Urgencias</dt>
            <dd>{yo?.urgencias ?? 0}</dd>
          </div>
          <div>
            <dt className="etiqueta">Domicilios</dt>
            <dd>{yo?.domicilios ?? 0}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <h2>Mis turnos</h2>
        {dias.length === 0 ? (
          <p className="nota">No tienes turnos este mes.</p>
        ) : (
          <ul className={css.dias}>
            {dias.map((d) => (
              <Fragment key={d.fecha}>
                <li
                  className={`${css.dia} ${d.fecha < hoyIso ? css.pasado : ""} ${d.fecha === hoyIso ? css.hoy : ""}`}
                  data-dia={d.fecha}
                >
                  <span className={css.fecha}>{fechaCorta(d.fecha)}</span>
                  <div className={css.conAccion}>
                    <div>
                      {d.turnos.map((t) => (
                        <div key={t.turno} className={css.turno}>
                          <span className={t.turno === "MANANA" ? css.manana : css.tarde}>{textoTurno(t)}</span>
                          <span className={css.horas}>{t.horas}</span>
                          {t.turno === "TARDE" && d.rol && <span className={css.rol}>{NOMBRE_ROL[d.rol]}</span>}
                        </div>
                      ))}
                    </div>
                    {d.fecha >= hoyIso && proponiendo !== d.fecha && (
                      <button type="button" className="btn pequeno" onClick={() => setProponiendo(d.fecha)}>
                        Proponer un cambio
                      </button>
                    )}
                  </div>
                </li>
                {proponiendo === d.fecha && (
                  <li>
                    <ProponerCambio cal={cal} medico={medico} dia={d} cerrar={() => setProponiendo(null)} />
                  </li>
                )}
              </Fragment>
            ))}
          </ul>
        )}
      </section>

      {(ausencias.data ?? []).length > 0 && (
        <section className="panel">
          <h2>Mis ausencias este mes</h2>
          <ul className={css.dias}>
            {ausencias.data!.map((a) => (
              <li key={a.id} className={css.dia}>
                <span className={css.fecha}>{fechaCorta(a.desde)}</span>
                <span>
                  {a.desde === a.hasta ? "" : `hasta el ${fechaCorta(a.hasta)} · `}
                  {a.turno ? `solo ${NOMBRE_TURNO[a.turno].toLowerCase()}` : "día completo"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="acciones">
        <Link className="btn" to={`/imprimir/calendario?mes=${mes}`}>
          Imprimir calendario / PDF
        </Link>
        <Link className="btn" to={`/imprimir?mes=${mes}`}>
          Imprimir tabla / PDF
        </Link>
        <Link className="btn" to={`/imprimir/urgencias-domicilios?mes=${mes}`}>
          Urgencias y domicilios
        </Link>
      </div>
    </>
  );
}
