import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCalendario, useHorarios } from "../api/consultas";
import type { Mitad, Turno } from "../api/tipos";
import { NOMBRE_ROL, rolDe } from "../calendario/logica";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { diaSemana, formatearFecha, mesSiguiente, nombreMes } from "../util/fechas";
import { DIAS, MITADES_DE, NOMBRE_TURNO, TURNOS } from "../util/textos";
import css from "./Imprimir.module.css";

const JORNADA: Record<string, string> = {
  "M1,M2": "M",
  "T1,T2": "T",
  "M1,M2,T1": "M+½T",
  "M2,T1,T2": "½M+T",
  "M1,M2,T1,T2": "M+T",
};
const ORDEN: Mitad[] = ["M1", "M2", "T1", "T2"];

/**
 * Vista imprimible del mes (diseño, 8): A4 horizontal, sin menús. Con
 * `?auto=1` abre el diálogo de impresión al cargar, desde donde también se
 * puede guardar como PDF.
 */
export function Imprimir() {
  const [parametros] = useSearchParams();
  const mes = parametros.get("mes") ?? mesSiguiente();
  const [anio, numMes] = mes.split("-").map(Number);
  const calendario = useCalendario(anio, numMes);
  const horarios = useHorarios();
  const impreso = useRef(false);

  const listo = calendario.isSuccess && horarios.isSuccess;
  useEffect(() => {
    if (listo && parametros.get("auto") === "1" && !impreso.current) {
      impreso.current = true;
      setTimeout(() => window.print(), 300);
    }
  }, [listo, parametros]);

  if (calendario.isError) return <MensajeError error={calendario.error} />;
  if (!calendario.data || !horarios.data) return <Cargando />;
  const cal = calendario.data;
  const horario = Object.fromEntries(
    horarios.data.map((h) => [h.turno, `${h.inicio.slice(0, 5)}–${h.fin.slice(0, 5)}`]),
  ) as Record<Turno, string>;
  const titulo = nombreMes(mes).replace(/^./, (c) => c.toUpperCase());

  const mitades = new Map<string, Set<Mitad>>();
  for (const a of cal.asignaciones) {
    const clave = `${a.medico_id}|${a.fecha}`;
    if (!mitades.has(clave)) mitades.set(clave, new Set());
    mitades.get(clave)!.add(a.mitad);
  }
  const deDia = (medico: number, fecha: string) => mitades.get(`${medico}|${fecha}`) ?? new Set<Mitad>();
  const medicos = [...cal.medicos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  const laborables = cal.dias.filter((d) => !d.festivo);

  return (
    <div className={css.pagina}>
      <div className={`${css.herramientas} no-imprimir`}>
        <Link to={`/?mes=${mes}`}>← Volver al calendario</Link>
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
        <>
          <table className={css.tabla}>
            <thead>
              <tr>
                <th>Día</th>
                {TURNOS.map((t) => (
                  <th key={t}>
                    {NOMBRE_TURNO[t]} <span className={css.horario}>{horario[t]}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cal.dias.map((d) => (
                <tr key={d.fecha} className={diaSemana(d.fecha) === 0 ? css.lunes : undefined}>
                  <th scope="row">
                    {DIAS[diaSemana(d.fecha)]} {Number(d.fecha.slice(8))}
                  </th>
                  {d.festivo ? (
                    <td colSpan={2} className={css.festivo}>
                      Festivo: {d.festivo}
                    </td>
                  ) : (
                    TURNOS.map((t) => (
                      <td key={t}>
                        {medicos
                          .map((m) => ({ m, n: [...deDia(m.id, d.fecha)].filter((h) => MITADES_DE[t].includes(h)).length }))
                          .filter(({ n }) => n > 0)
                          .map(({ m, n }) => {
                            const rol = t === "TARDE" ? rolDe(cal, m.id, d.fecha) : null;
                            return `${m.nombre}${n === 1 ? " (½)" : ""}${rol ? ` (${NOMBRE_ROL[rol].toLowerCase()})` : ""}`;
                          })
                          .join(", ")}
                      </td>
                    ))
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <p className={css.leyenda}>½ = medio turno (la mitad contigua a la jornada).</p>

          <section className={css.porMedico}>
            <h2>Turnos por médico — {titulo}</h2>
            <table className={css.matriz}>
              <thead>
                <tr>
                  <th>Médico</th>
                  {laborables.map((d) => (
                    <th key={d.fecha}>
                      {"LMXJV"[diaSemana(d.fecha)]}
                      <br />
                      {Number(d.fecha.slice(8))}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {medicos
                  .filter((m) => m.asignado > 0)
                  .map((m) => (
                    <tr key={m.id}>
                      <th scope="row">{m.nombre}</th>
                      {laborables.map((d) => {
                        const clave = ORDEN.filter((h) => deDia(m.id, d.fecha).has(h)).join(",");
                        const rol = rolDe(cal, m.id, d.fecha);
                        return (
                          <td key={d.fecha}>
                            {JORNADA[clave] ?? clave}
                            {rol ? (rol === "URGENCIAS" ? " U" : " D") : ""}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
              </tbody>
            </table>
            <p className={css.leyenda}>M = mañana · T = tarde · ½ = medio turno · U = urgencias · D = domicilios. Los festivos no aparecen.</p>
          </section>
        </>
      )}
    </div>
  );
}
