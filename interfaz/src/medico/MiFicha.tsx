import { useState } from "react";

import { useAjustes, useMedico, useReglas } from "../api/consultas";
import { useAusenciasDe } from "../api/medico";
import { CuadriculaElegibilidad } from "../componentes/CuadriculaElegibilidad";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { aFormulario } from "../medicos/formulario";
import { AnularAusencia, PedirAusencia, ProponerDisponibilidad } from "./ProponerFicha";
import { fechaCorta, hoy, mesActual, mesSiguiente, nombreMes, primerDia } from "../util/fechas";
import { desplazarMes } from "../util/mes";
import { DIAS, formatearMedios, NOMBRE_JORNADA, NOMBRE_PREFERENCIA, NOMBRE_TURNO } from "../util/textos";
import css from "./EspacioMedico.module.css";

/**
 * «Mi ficha»: disponibilidad semanal, carga, jornadas, preferencias y ausencias (solo
 * consulta). Las reglas cambian con el tiempo (versiones por fecha): se muestran las de
 * un mes, que se elige aquí mismo. Por defecto, el mes publicado que se está viendo o,
 * si no hay, el siguiente (el que se suele estar preparando). La ficha no depende de
 * que haya meses publicados.
 */
export function MiFicha({ medico, mes: mesPublicado }: { medico: number; mes: string | null }) {
  const hoyIso = hoy();
  const meses = [...new Set([0, 1, 2, 3].map((n) => desplazarMes(mesActual(), n)).concat(mesPublicado ?? []))].sort();
  const [mes, setMes] = useState(mesPublicado ?? mesSiguiente());
  const ficha = useMedico(medico);
  const reglas = useReglas(medico, primerDia(mes));
  const conRangos = useAjustes().data?.modo_carga !== "PRESENCIA";
  const ausencias = useAusenciasDe(medico, hoyIso);
  const [abierto, setAbierto] = useState<"disponibilidad" | "ausencia" | null>(null);

  if (reglas.isError) return <MensajeError error={reglas.error} />;
  if (!reglas.data || !ficha.data) return <Cargando />;
  const r = reglas.data;
  const formulario = aFormulario(r);

  return (
    <>
      <section className="panel">
        <h2>{ficha.data.nombre}</h2>
        <label className="campo">
          <span>Reglas de</span>
          <select aria-label="Mes de las reglas" value={mes} onChange={(e) => setMes(e.target.value)}>
            {meses.map((m) => (
              <option key={m} value={m}>
                {nombreMes(m).replace(/^./, (c) => c.toUpperCase())}
              </option>
            ))}
          </select>
        </label>
        <p className="nota">
          {r.vigente_desde
            ? `Vigentes desde el ${fechaCorta(r.vigente_desde)}. `
            : `Para ${nombreMes(mes)} aún no tienes reglas guardadas (prueba con un mes posterior). `}
          {conRangos ? "La carga y las jornadas las decide el planificador." : "Las jornadas las decide el planificador."}
        </p>
        <h3>Disponibilidad semanal</h3>
        <CuadriculaElegibilidad valor={formulario.elegibilidad} soloLectura />
        <p className="nota">Fijo: siempre ese turno · Hab.: habitual · Disp.: disponible · —: no disponible.</p>
        {abierto !== "disponibilidad" && (
          <div className="acciones">
            <button type="button" className="btn" onClick={() => setAbierto("disponibilidad")}>
              Proponer otra disponibilidad
            </button>
          </div>
        )}
        {conRangos && (
          <>
            <h3>Carga mensual</h3>
            <p>
              {r.carga
                ? `Entre ${formatearMedios(r.carga.minimo)} y ${formatearMedios(r.carga.maximo)} turnos al mes`
                : "Sin definir"}
              {r.carga_por_turno.map((c) => (
                <span key={c.turno} className="nota">
                  {" "}
                  · {NOMBRE_TURNO[c.turno]}: {formatearMedios(c.minimo)}
                  {c.maximo != null ? `–${formatearMedios(c.maximo)}` : " o más"}
                </span>
              ))}
            </p>
          </>
        )}
        {r.jornadas.length > 0 && (
          <>
            <h3>Jornadas especiales</h3>
            <ul>
              {r.jornadas.map((j) => (
                <li key={j.dia_semana}>
                  {DIAS[j.dia_semana]}: {NOMBRE_JORNADA[j.tipo]}
                </li>
              ))}
            </ul>
          </>
        )}
        {r.preferencias.length > 0 && (
          <>
            <h3>Preferencias</h3>
            <ul>
              {r.preferencias.map((p) => (
                <li key={`${p.dia_semana}-${p.turno}`}>
                  {NOMBRE_PREFERENCIA[p.valor]} {DIAS[p.dia_semana].toLowerCase()} por la{" "}
                  {NOMBRE_TURNO[p.turno].toLowerCase()}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {abierto === "disponibilidad" && (
        <ProponerDisponibilidad actual={formulario.elegibilidad} cerrar={() => setAbierto(null)} />
      )}
      {abierto === "ausencia" && <PedirAusencia cerrar={() => setAbierto(null)} />}

      <section className="panel">
        <h2>Mis próximas ausencias</h2>
        {abierto !== "ausencia" && (
          <div className="acciones">
            <button type="button" className="btn" onClick={() => setAbierto("ausencia")}>
              Pedir una ausencia
            </button>
          </div>
        )}
        {ausencias.isPending ? (
          <Cargando />
        ) : (ausencias.data ?? []).length === 0 ? (
          <p className="nota">No tienes ausencias previstas.</p>
        ) : (
          <ul className={css.dias}>
            {ausencias.data!.map((a) => (
              <li key={a.id} className={css.dia}>
                <span className={css.fecha}>{fechaCorta(a.desde)}</span>
                <span className={css.conAccion}>
                  <span>
                    {a.desde === a.hasta ? "" : `hasta el ${fechaCorta(a.hasta)} · `}
                    {a.turno ? `solo ${NOMBRE_TURNO[a.turno].toLowerCase()}` : "día completo"}
                  </span>
                  <AnularAusencia ausencia={a} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
