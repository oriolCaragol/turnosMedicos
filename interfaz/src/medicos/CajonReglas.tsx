import type { Preferencia, TipoJornada } from "../api/tipos";
import { Cajon } from "../componentes/Cajon";
import { CampoTurnos } from "../componentes/CampoTurnos";
import { clave } from "../componentes/CuadriculaElegibilidad";
import { DIAS, DIAS_CORTOS, NOMBRE_JORNADA, NOMBRE_PREFERENCIA, NOMBRE_TURNO, TURNOS } from "../util/textos";
import type { Formulario } from "./formulario";

/** Reglas menos habituales de un médico: jornadas largas, límites por turno y preferencias. */
export function CajonReglas({
  nombre,
  f,
  setF,
  estado,
  conRangos = true,
  cerrar,
}: {
  nombre: string;
  f: Formulario;
  setF: (f: Formulario) => void;
  estado: string;
  /** Con el modo de carga «según la presencia» no hay límites por tipo de turno. */
  conRangos?: boolean;
  cerrar: () => void;
}) {
  return (
    <Cajon
      titulo={`Más reglas de ${nombre}`}
      cerrar={cerrar}
      cabecera={
        <>
          <div className="etiqueta">Más reglas</div>
          <h2 style={{ fontSize: 17 }}>{nombre}</h2>
          <div className="nota">{estado}</div>
        </>
      }
      pie={
        <button type="button" className="btn primario" onClick={cerrar} style={{ marginLeft: "auto" }}>
          Hecho
        </button>
      }
    >
      <h3>Jornadas de más de un turno</h3>
      <p className="nota">El generador nunca las crea por su cuenta: solo se aplican los días que indiques aquí.</p>
      <div className="fila-formulario">
        {DIAS.map((dia, d) => (
          <label className="campo" key={dia}>
            <span>{DIAS_CORTOS[d]}</span>
            <select
              aria-label={`Jornada del ${dia.toLowerCase()}`}
              value={f.jornadas[d] ?? ""}
              onChange={(e) => setF({ ...f, jornadas: { ...f.jornadas, [d]: e.target.value as TipoJornada | "" } })}
            >
              <option value="">Normal</option>
              {Object.entries(NOMBRE_JORNADA).map(([valor, texto]) => (
                <option key={valor} value={valor}>
                  {texto}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      {conRangos && (
        <>
          <h3>Límites por tipo de turno</h3>
          <p className="nota">Opcional, en turnos al mes. Deja el máximo vacío si no hay límite.</p>
          {TURNOS.map((t) => (
            <div className="fila-formulario" key={t} style={{ marginBottom: 6 }}>
              <strong style={{ minWidth: 70, alignSelf: "center", color: `var(--${t === "MANANA" ? "manana" : "tarde"})` }}>
                {NOMBRE_TURNO[t]}s
              </strong>
              <CampoTurnos
                etiqueta="Mínimo"
                opcional
                medios={f.porTurno[t].minimo}
                onChange={(minimo) => setF({ ...f, porTurno: { ...f.porTurno, [t]: { ...f.porTurno[t], minimo } } })}
              />
              <CampoTurnos
                etiqueta="Máximo"
                opcional
                medios={f.porTurno[t].maximo}
                onChange={(maximo) => setF({ ...f, porTurno: { ...f.porTurno, [t]: { ...f.porTurno[t], maximo } } })}
              />
            </div>
          ))}
        </>
      )}

      <h3>Preferencias</h3>
      <p className="nota">Se respetan siempre que no impidan cumplir las demás reglas.</p>
      <table>
        <thead>
          <tr>
            <th />
            {DIAS_CORTOS.map((d) => (
              <th key={d}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {TURNOS.map((t) => (
            <tr key={t}>
              <th scope="row" style={{ color: `var(--${t === "MANANA" ? "manana" : "tarde"})` }}>
                {NOMBRE_TURNO[t]}
              </th>
              {DIAS.map((dia, d) => (
                <td key={dia} style={{ padding: "4px 2px" }}>
                  <select
                    aria-label={`Preferencia ${dia.toLowerCase()} ${NOMBRE_TURNO[t].toLowerCase()}`}
                    value={f.preferencias[clave(d, t)] ?? ""}
                    onChange={(e) =>
                      setF({ ...f, preferencias: { ...f.preferencias, [clave(d, t)]: e.target.value as Preferencia | "" } })
                    }
                  >
                    <option value="">—</option>
                    {Object.entries(NOMBRE_PREFERENCIA).map(([valor, texto]) => (
                      <option key={valor} value={valor}>
                        {texto}
                      </option>
                    ))}
                  </select>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Cajon>
  );
}
