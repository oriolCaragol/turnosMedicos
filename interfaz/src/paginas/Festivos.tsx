import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  useAniosFestivos,
  useBorrarFestivo,
  useCrearFestivo,
  useFestivos,
  useMunicipioActual,
  useRestaurarFestivos,
} from "../api/consultas";
import type { AmbitoFestivo } from "../api/tipos";
import { Aviso, Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { diaSemana, formatearFecha } from "../util/fechas";
import { desplazarMes, useMes } from "../util/mes";
import { DIAS, NOMBRE_AMBITO } from "../util/textos";

export function Festivos() {
  const { mes, anio, cambiar } = useMes();
  const festivos = useFestivos(anio);
  const anios = useAniosFestivos();
  const crear = useCrearFestivo();
  const borrar = useBorrarFestivo();
  const restaurar = useRestaurarFestivos();
  const tostada = useTostada();
  const [nuevo, setNuevo] = useState({ fecha: "", descripcion: "", ambito: "LOCAL" as AmbitoFestivo });
  const carga = anios.data?.find((a) => a.anio === anio);
  const municipio = useMunicipioActual().data?.nombre ?? "tu municipio";

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    crear.mutate(nuevo, {
      onSuccess: () => {
        setNuevo({ ...nuevo, fecha: "", descripcion: "" });
        tostada("Festivo añadido");
      },
    });
  };

  return (
    <section className="panel">
      <div className="barra-titulo">
        <div>
          <h2>Festivos de {anio}</h2>
          <p className="entradilla" style={{ margin: 0 }}>
            Nacionales, autonómicos y locales de {municipio}. Los festivos entre semana no se planifican. Para buscarlos
            en las fuentes oficiales o cambiar el municipio, ve a <Link to="/configuracion">Configuración</Link>.
          </p>
        </div>
        <div className="acciones">
          <button type="button" className="btn" onClick={() => cambiar(desplazarMes(mes, -12))}>
            ‹ {anio - 1}
          </button>
          <button type="button" className="btn" onClick={() => cambiar(desplazarMes(mes, 12))}>
            {anio + 1} ›
          </button>
          {carga?.precargado && (
            <button
              type="button"
              className="btn"
              disabled={restaurar.isPending}
              onClick={() =>
                restaurar.mutate(anio, {
                  onSuccess: (r) => tostada(r.length ? `Restaurados ${r.length} festivos` : "No faltaba ningún festivo"),
                })
              }
            >
              Restaurar los precargados
            </button>
          )}
        </div>
      </div>

      <div style={{ margin: "12px 0" }}>
        {carga && !carga.completo && (
          <Aviso>
            Faltan festivos de {anio} por publicar, normalmente las dos fiestas locales de {municipio}. Búscalas en{" "}
            <Link to="/configuracion">Configuración → Festivos oficiales</Link> cuando se publiquen, o añádelas aquí.
          </Aviso>
        )}
        {!carga && !festivos.isPending && (
          <Aviso>
            No se han cargado los festivos de {anio}: búscalos en{" "}
            <Link to="/configuracion">Configuración → Festivos oficiales</Link> o añádelos a mano.
          </Aviso>
        )}
      </div>

      <form className="fila-formulario" onSubmit={enviar} style={{ marginBottom: 12 }}>
        <label className="campo">
          <span>Fecha</span>
          <input type="date" value={nuevo.fecha} onChange={(e) => setNuevo({ ...nuevo, fecha: e.target.value })} required />
        </label>
        <label className="campo">
          <span>Nombre</span>
          <input
            value={nuevo.descripcion}
            placeholder="p. ej. Fiesta local"
            onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })}
            required
          />
        </label>
        <label className="campo">
          <span>Ámbito</span>
          <select value={nuevo.ambito} onChange={(e) => setNuevo({ ...nuevo, ambito: e.target.value as AmbitoFestivo })}>
            {Object.entries(NOMBRE_AMBITO).map(([valor, texto]) => (
              <option key={valor} value={valor}>
                {texto}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn primario" disabled={crear.isPending}>
          Añadir festivo
        </button>
      </form>
      <MensajeError error={crear.error ?? borrar.error ?? restaurar.error} />

      {festivos.isPending ? (
        <Cargando />
      ) : festivos.isError ? (
        <MensajeError error={festivos.error} />
      ) : (
        <div className="tabla-desplazable">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Día</th>
                <th>Nombre</th>
                <th>Ámbito</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {festivos.data.map((f) => {
                const d = diaSemana(f.fecha);
                return (
                  <tr key={f.id}>
                    <td className="num">{formatearFecha(f.fecha)}</td>
                    <td>
                      {d > 4 ? (d === 5 ? "Sábado" : "Domingo") : DIAS[d]}
                      {d > 4 && <span className="nota"> (fin de semana)</span>}
                    </td>
                    <td>{f.descripcion}</td>
                    <td>{NOMBRE_AMBITO[f.ambito]}</td>
                    <td>
                      <button type="button" className="x" aria-label={`Quitar ${f.descripcion}`} onClick={() => borrar.mutate(f.id)}>
                        ×
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
