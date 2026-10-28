/**
 * Lo que ve un médico en el modo servidor, pensado para el móvil (diseño del modo
 * servidor, 11.1; D-S2): sus turnos, el calendario del equipo de los meses publicados
 * y su ficha. No modifica nada: los cambios se proponen (fase 4).
 */
import { NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useEventos } from "../api/eventos";
import { useMesesPublicados } from "../api/medico";
import { useSalir } from "../api/sesion";
import { useSolicitudes } from "../api/solicitudes";
import type { MesPublicado, Yo } from "../api/tipos";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { CambiarContrasena } from "../paginas/Acceso";
import { Imprimir } from "../paginas/Imprimir";
import { ImprimirCalendario } from "../paginas/ImprimirCalendario";
import { ImprimirRoles } from "../paginas/ImprimirRoles";
import { mesActual, nombreMes } from "../util/fechas";
import { CalendarioEquipo } from "./CalendarioEquipo";
import css from "./EspacioMedico.module.css";
import { MiFicha } from "./MiFicha";
import { MisSolicitudes } from "./MisSolicitudes";
import { MisTurnos } from "./MisTurnos";

const PESTANAS = [
  ["/", "Mis turnos"],
  ["/equipo", "Calendario"],
  ["/ficha", "Mi ficha"],
  ["/solicitudes", "Solicitudes"],
] as const;

const texto = (m: MesPublicado) => `${m.anio}-${String(m.mes).padStart(2, "0")}`;

/** El mes elegido (?mes=) si está publicado; si no, el actual o el último publicado. */
export function useMesPublicado() {
  const [parametros, setParametros] = useSearchParams();
  const meses = useMesesPublicados();
  const lista = (meses.data ?? []).map(texto);
  const pedido = parametros.get("mes");
  const mes = pedido && lista.includes(pedido) ? pedido : lista.includes(mesActual()) ? mesActual() : (lista[0] ?? null);
  const cambiar = (nuevo: string) => {
    const p = new URLSearchParams(parametros);
    p.set("mes", nuevo);
    setParametros(p);
  };
  return { meses, lista, mes, cambiar };
}

function Disposicion({ yo }: { yo: Yo }) {
  useEventos(); // un mes que se publica o se retoca aparece sin recargar
  const salir = useSalir();
  const { meses, lista, mes, cambiar } = useMesPublicado();
  const busqueda = mes ? `?mes=${mes}` : "";
  // El calendario del equipo necesita el ancho de la vista del planificador; lo demás, una columna.
  const amplio = useLocation().pathname === "/equipo";
  const porAceptar = (useSolicitudes().data ?? []).filter((s) => s.me_toca_aceptar).length;

  return (
    <div className={`${css.espacio} ${amplio ? css.amplio : ""}`}>
      <header className={css.cabecera}>
        <div className={css.fila}>
          <img src="/icono.svg" alt="" className={css.icono} />
          <div className={css.quien}>
            <strong>{yo.nombre_visible}</strong>
            <span>Turnos médicos</span>
          </div>
          <NavLink className="btn pequeno" to={{ pathname: "/cuenta", search: busqueda }}>
            Contraseña
          </NavLink>
          <button type="button" className="btn pequeno" onClick={() => salir.mutate()}>
            Salir
          </button>
        </div>
        {lista.length > 0 && (
          <label className={css.mes}>
            <span className="etiqueta">Mes</span>
            <select value={mes ?? ""} onChange={(e) => cambiar(e.target.value)}>
              {lista.map((m) => (
                <option key={m} value={m}>
                  {nombreMes(m).replace(/^./, (c) => c.toUpperCase())}
                </option>
              ))}
            </select>
          </label>
        )}
        <nav className={css.pestanas} aria-label="Secciones">
          {PESTANAS.map(([ruta, nombre]) => (
            <NavLink key={ruta} to={{ pathname: ruta, search: busqueda }} end>
              {nombre}
              {ruta === "/solicitudes" && porAceptar > 0 && (
                <span className={css.cuenta} title="Intercambios que te proponen">
                  {porAceptar}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className={css.contenido}>
        {meses.isPending ? <Cargando /> : meses.isError ? <MensajeError error={meses.error} /> : <Outlet />}
      </main>
    </div>
  );
}

function SinMeses() {
  return (
    <section className="panel">
      <h2>Aún no hay calendarios publicados</h2>
      <p className="nota">Cuando el planificador publique un mes, aparecerá aquí.</p>
    </section>
  );
}

/** El mes elegido, o el aviso de que aún no hay ninguno publicado. */
function ConMes({ hijo }: { hijo: (mes: string) => React.ReactNode }) {
  const { mes } = useMesPublicado();
  return mes ? <>{hijo(mes)}</> : <SinMeses />;
}

function FichaDelMes({ medico }: { medico: number }) {
  const { mes } = useMesPublicado();
  return <MiFicha medico={medico} mes={mes} />;
}

function Cuenta({ yo }: { yo: Yo }) {
  const volver = useNavigate();
  const tostada = useTostada();
  return (
    <CambiarContrasena
      yo={yo}
      alTerminar={() => {
        tostada("Contraseña cambiada");
        volver(-1);
      }}
    />
  );
}

export function EspacioMedico({ yo }: { yo: Yo }) {
  const medico = yo.medico_id;
  if (medico == null)
    return (
      <section className="panel">
        <h2>Hola, {yo.nombre_visible}</h2>
        <p className="nota">Tu cuenta aún no está vinculada a tu ficha de médico. Pídeselo al administrador.</p>
      </section>
    );
  return (
    <Routes>
      <Route path="imprimir" element={<Imprimir />} />
      <Route path="imprimir/urgencias-domicilios" element={<ImprimirRoles />} />
      <Route path="imprimir/calendario" element={<ImprimirCalendario />} />
      <Route element={<Disposicion yo={yo} />}>
        <Route index element={<ConMes hijo={(mes) => <MisTurnos medico={medico} mes={mes} />} />} />
        <Route path="equipo" element={<ConMes hijo={(mes) => <CalendarioEquipo medico={medico} mes={mes} />} />} />
        <Route path="ficha" element={<FichaDelMes medico={medico} />} />
        <Route path="solicitudes" element={<MisSolicitudes />} />
        <Route path="cuenta" element={<Cuenta yo={yo} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
