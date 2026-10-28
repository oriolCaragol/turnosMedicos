import { useState } from "react";

import {
  useAjustes,
  useBuscarFestivosOficiales,
  useBuscarMunicipios,
  useCargarFestivosOficiales,
  useGuardarAjustes,
  useMunicipioActual,
} from "../api/consultas";
import type { Municipio } from "../api/tipos";
import { Aviso, MensajeError, useTostada } from "../componentes/Mensajes";
import { diaSemana, formatearFecha } from "../util/fechas";
import { DIAS, NOMBRE_AMBITO } from "../util/textos";
import css from "./Configuracion.module.css";

const ESTADO = { NUEVO: "Falta", IGUAL: "Ya está", DISTINTO: "Distinto" } as const;

function ElegirMunicipio({ alElegir, alCancelar }: { alElegir: (m: Municipio) => void; alCancelar: () => void }) {
  const [texto, setTexto] = useState("");
  const encontrados = useBuscarMunicipios(texto);
  return (
    <div>
      <div className="acciones">
        <label className="campo">
          <span>Municipio</span>
          <input
            autoFocus
            value={texto}
            placeholder="Escribe el nombre…"
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && alCancelar()}
          />
        </label>
        <button type="button" className="btn" style={{ alignSelf: "flex-end" }} onClick={alCancelar}>
          Cancelar
        </button>
      </div>
      {encontrados.data && (
        <ul className={css.sugerencias} aria-label="Municipios encontrados">
          {encontrados.data.length === 0 && <li className="nota" style={{ padding: "7px 10px" }}>Ningún municipio con ese nombre.</li>}
          {encontrados.data.map((m) => (
            <li key={m.ine}>
              <button type="button" onClick={() => alElegir(m)}>
                {m.nombre} <small>· {m.provincia} ({m.ccaa_nombre})</small>
              </button>
            </li>
          ))}
        </ul>
      )}
      <MensajeError error={encontrados.error} />
    </div>
  );
}

/** Municipio del centro y búsqueda de sus festivos en las fuentes oficiales. */
export function SeccionFestivosOficiales() {
  const ajustes = useAjustes();
  const guardar = useGuardarAjustes();
  const municipio = useMunicipioActual();
  const buscar = useBuscarFestivosOficiales();
  const cargar = useCargarFestivosOficiales();
  const tostada = useTostada();
  const hoy = new Date().getFullYear();
  const [anio, setAnio] = useState(new Date().getMonth() >= 9 ? hoy + 1 : hoy);
  const [cambiando, setCambiando] = useState(false);

  const elegir = (m: Municipio) => {
    if (!ajustes.data) return;
    guardar.mutate(
      { ...ajustes.data, municipio: m.ine },
      {
        onSuccess: () => {
          setCambiando(false);
          buscar.reset();
          tostada(`Municipio del centro: ${m.nombre}`);
        },
      },
    );
  };

  const resultado = buscar.data?.anio === anio ? buscar.data : undefined;
  const faltan = resultado?.festivos.filter((f) => f.estado === "NUEVO") ?? [];

  return (
    <section className="panel">
      <h2>Festivos oficiales</h2>
      <p className="entradilla">
        Busca los festivos nacionales, autonómicos y locales del municipio del centro en las fuentes oficiales y añade los que
        falten. Los festivos locales se publican, normalmente, a final del año anterior.
      </p>

      {cambiando ? (
        <ElegirMunicipio alElegir={elegir} alCancelar={() => setCambiando(false)} />
      ) : (
        <div className={css.municipio}>
          <span className="etiqueta">Municipio del centro</span>
          {municipio.data ? (
            <span>
              <b>{municipio.data.nombre}</b>{" "}
              <span className="nota">
                · {municipio.data.provincia} ({municipio.data.ccaa_nombre}) · INE {municipio.data.ine}
              </span>
            </span>
          ) : (
            <span className="nota">…</span>
          )}
          <button type="button" className="btn" onClick={() => setCambiando(true)}>
            Cambiar
          </button>
        </div>
      )}
      <MensajeError error={guardar.error ?? municipio.error} />

      <div className="acciones" style={{ alignItems: "flex-end" }}>
        <label className="campo">
          <span>Año</span>
          <select value={anio} onChange={(e) => setAnio(Number(e.target.value))}>
            {[hoy - 1, hoy, hoy + 1, hoy + 2].map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn primario" disabled={buscar.isPending || cambiando} onClick={() => buscar.mutate(anio)}>
          {buscar.isPending ? "Buscando…" : "Buscar festivos oficiales"}
        </button>
        {resultado && (
          <button
            type="button"
            className="btn"
            disabled={faltan.length === 0 || cargar.isPending}
            onClick={() =>
              cargar.mutate(anio, {
                onSuccess: (r) => {
                  tostada(r.length === 1 ? "Añadido 1 festivo" : `Añadidos ${r.length} festivos`);
                  buscar.mutate(anio);
                },
              })
            }
          >
            {faltan.length === 0 ? "No falta ninguno" : `Añadir los ${faltan.length} que faltan`}
          </button>
        )}
      </div>
      <MensajeError error={buscar.error ?? cargar.error} />

      {resultado && (
        <div style={{ marginTop: 12 }}>
          {resultado.avisos.map((a) => (
            <Aviso key={a}>{a}</Aviso>
          ))}
          {resultado.festivos.length > 0 && (
            <div className="tabla-desplazable" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Día</th>
                    <th>Nombre</th>
                    <th>Ámbito</th>
                    <th>Fuente</th>
                    <th>En tus festivos</th>
                  </tr>
                </thead>
                <tbody>
                  {resultado.festivos.map((f) => {
                    const d = diaSemana(f.fecha);
                    return (
                      <tr key={f.fecha}>
                        <td className="num">{formatearFecha(f.fecha)}</td>
                        <td>{d > 4 ? (d === 5 ? "Sábado" : "Domingo") : DIAS[d]}</td>
                        <td>{f.descripcion}</td>
                        <td>{NOMBRE_AMBITO[f.ambito]}</td>
                        <td className={css.fuente}>
                          {f.url ? (
                            <a href={f.url} target="_blank" rel="noreferrer">
                              {f.fuente}
                            </a>
                          ) : (
                            f.fuente
                          )}
                        </td>
                        <td>
                          <span className={`${css.estado} ${css[f.estado]}`}>
                            {ESTADO[f.estado as keyof typeof ESTADO] ?? f.estado}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {resultado.solo_en_tus_datos.length > 0 && (
            <p className="nota">
              En tus festivos de {anio}, pero no en las fuentes:{" "}
              {resultado.solo_en_tus_datos.map((f) => `${formatearFecha(f.fecha)} (${f.descripcion})`).join(", ")}. Si sobran,
              quítalos en la pestaña Festivos.
            </p>
          )}
          <p className="nota">
            «Distinto»: ya tienes un festivo ese día, con otro nombre o ámbito; no se cambia. Fuentes consultadas:{" "}
            {resultado.fuentes.join(" y ") || "ninguna"}. Son datos orientativos recopilados de los boletines oficiales:
            comprueba la fuente de cada festivo si hay dudas.
          </p>
        </div>
      )}
    </section>
  );
}
