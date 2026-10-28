import { Link, NavLink, Outlet } from "react-router-dom";

import { useCalendario, useMunicipioActual } from "../api/consultas";
import { useEventos } from "../api/eventos";
import { useSalir, useYo } from "../api/sesion";
import { useSolicitudes } from "../api/solicitudes";
import { nombreMes } from "../util/fechas";
import { desplazarMes, useMes } from "../util/mes";
import css from "./Disposicion.module.css";

const PESTANAS = [
  ["/", "Calendario"],
  ["/medicos", "Médicos y reglas"],
  ["/cobertura", "Cobertura"],
  ["/festivos", "Festivos"],
  ["/configuracion", "Configuración"],
] as const;

export const mayuscula = (texto: string) => texto.replace(/^./, (c) => c.toUpperCase());

export function Disposicion() {
  const { mes, anio, numMes, cambiar } = useMes();
  useEventos(); // cambios de otros usuarios en vivo
  const calendario = useCalendario(anio, numMes);
  const municipio = useMunicipioActual();
  const incumplidas = (calendario.data?.avisos ?? []).filter((a) => a.tipo === "INCUMPLIMIENTO").length;
  const yo = useYo().data;
  const salir = useSalir();
  const enServidor = yo?.modo === "servidor";
  const pestanas = [
    ...PESTANAS,
    ...(enServidor ? [["/solicitudes", "Solicitudes"] as const] : []),
    ...(enServidor && yo.rol === "ADMINISTRADOR" ? [["/administracion", "Administración"] as const] : []),
  ];
  const pendientes = (useSolicitudes(enServidor).data ?? []).filter((s) => s.estado === "PENDIENTE").length;

  return (
    <>
      <header className={css.cabecera}>
        <div className={`envoltura ${css.interior}`}>
          <div className="barra-titulo">
            <h1>
              Turnos médicos
              <small>
                Mañana y tarde, de lunes a viernes
                {municipio.data && ` · festivos de ${municipio.data.nombre} (${municipio.data.ccaa_nombre})`}
              </small>
            </h1>
            {enServidor && (
              <div className={css.usuario}>
                <span title={`Usuario ${yo.nombre}`}>{yo.nombre_visible}</span>
                <Link className="btn pequeno" to={{ pathname: "/cuenta", search: `?mes=${mes}` }}>
                  Contraseña
                </Link>
                <button type="button" className="btn pequeno" onClick={() => salir.mutate()}>
                  Salir
                </button>
              </div>
            )}
            <div className={css.mes}>
              <button
                type="button"
                className="btn icono"
                aria-label="Mes anterior"
                onClick={() => cambiar(desplazarMes(mes, -1))}
              >
                ‹
              </button>
              <output aria-live="polite">{mayuscula(nombreMes(mes)).replace(" de ", " ")}</output>
              <button
                type="button"
                className="btn icono"
                aria-label="Mes siguiente"
                onClick={() => cambiar(desplazarMes(mes, 1))}
              >
                ›
              </button>
            </div>
          </div>
          <nav className={css.pestanas} aria-label="Secciones">
            {pestanas.map(([ruta, nombre]) => (
              <NavLink key={ruta} to={{ pathname: ruta, search: `?mes=${mes}` }} end={ruta === "/"}>
                {nombre}
                {ruta === "/" && incumplidas > 0 && (
                  <span className={css.cuenta} title="Reglas que no se cumplen">
                    {incumplidas}
                  </span>
                )}
                {ruta === "/solicitudes" && pendientes > 0 && (
                  <span className={`${css.cuenta} ${css.cuentaAviso}`} title="Solicitudes pendientes">
                    {pendientes}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <div className="envoltura">
        <main className="principal">
          <Outlet />
        </main>
      </div>
    </>
  );
}
