import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCalendario } from "../api/consultas";
import type { Calendario, Rol } from "../api/tipos";
import { IconoCasa, IconoEmergencia } from "../componentes/Iconos";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { diaSemana, formatearFecha, mesSiguiente, nombreMes } from "../util/fechas";
import { DIAS } from "../util/textos";
import css from "./Imprimir.module.css";

/** Las tardes que necesitan al menos dos médicos tienen urgencias y domicilios. */
function conServicio(cal: Calendario, fecha: string) {
  const tarde = cal.cobertura.filter((c) => c.fecha === fecha && (c.mitad === "T1" || c.mitad === "T2"));
  return tarde.length === 2 && tarde.every((c) => c.minimo >= 2);
}

/**
 * Urgencias y domicilios del mes para imprimir: quién hace cada papel cada día y
 * cuántas veces cada médico. A4 vertical; con `?auto=1` abre el diálogo de
 * impresión al cargar.
 */
export function ImprimirRoles() {
  const [parametros] = useSearchParams();
  const mes = parametros.get("mes") ?? mesSiguiente();
  const [anio, numMes] = mes.split("-").map(Number);
  const calendario = useCalendario(anio, numMes);
  const impreso = useRef(false);

  // Esta vista se imprime en vertical (el resto, en horizontal).
  useEffect(() => {
    const estilo = document.createElement("style");
    estilo.textContent = "@page { size: A4 portrait; margin: 12mm; }";
    document.head.appendChild(estilo);
    return () => estilo.remove();
  }, []);

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
  const nombre = Object.fromEntries(cal.medicos.map((m) => [m.id, m.nombre]));
  const papel = (fecha: string, rol: Rol) => {
    const r = (cal.roles ?? []).find((x) => x.fecha === fecha && x.rol === rol);
    return r ? nombre[r.medico_id] : null;
  };
  const conPapeles = [...cal.medicos]
    .filter((m) => (m.urgencias ?? 0) + (m.domicilios ?? 0) > 0)
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));

  return (
    <div className={`${css.pagina} ${css.vertical}`}>
      <div className={`${css.herramientas} no-imprimir`}>
        <Link to={`/?mes=${mes}`}>← Volver al calendario</Link>
        <button type="button" className="btn primario" onClick={() => window.print()}>
          Imprimir / Guardar como PDF
        </button>
      </div>

      <header className={css.cabecera}>
        <h1>Urgencias y domicilios — {titulo}</h1>
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
          <table className={`${css.tabla} ${css.roles}`}>
            <thead>
              <tr>
                <th>Día</th>
                <th>
                  <IconoEmergencia /> Urgencias
                </th>
                <th>
                  <IconoCasa /> Domicilios
                </th>
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
                  ) : !conServicio(cal, d.fecha) ? (
                    <td colSpan={2} className={css.festivo}>
                      Sin servicio (menos de dos médicos de tarde)
                    </td>
                  ) : (
                    (["URGENCIAS", "DOMICILIOS"] as const).map((rol) => {
                      const quien = papel(d.fecha, rol);
                      return (
                        <td key={rol} className={quien ? undefined : css.sinAsignar}>
                          {quien ?? "Sin asignar"}
                        </td>
                      );
                    })
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          <section className={css.resumenRoles}>
            <h2>Por médico</h2>
            <table className={css.tabla}>
              <thead>
                <tr>
                  <th>Médico</th>
                  <th className={css.n}>Urgencias</th>
                  <th className={css.n}>Domicilios</th>
                  <th className={css.n}>Total</th>
                </tr>
              </thead>
              <tbody>
                {conPapeles.map((m) => (
                  <tr key={m.id}>
                    <th scope="row">{m.nombre}</th>
                    <td className={css.n}>{m.urgencias ?? 0}</td>
                    <td className={css.n}>{m.domicilios ?? 0}</td>
                    <td className={css.n}>{(m.urgencias ?? 0) + (m.domicilios ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
