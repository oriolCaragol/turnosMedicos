import { NavLink } from "react-router-dom";

import { useMes } from "../util/mes";

/** Subpestañas de «Médicos y reglas». */
export function SubpestanasMedicos() {
  const { mes } = useMes();
  return (
    <nav className="subpestanas" aria-label="Médicos y reglas">
      <NavLink to={{ pathname: "/medicos", search: `?mes=${mes}` }} end>
        Médicos
      </NavLink>
      <NavLink to={{ pathname: "/medicos/rotaciones", search: `?mes=${mes}` }}>Turnos rotativos</NavLink>
    </nav>
  );
}
