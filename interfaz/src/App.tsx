import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { useYo } from "./api/sesion";

import { Disposicion } from "./componentes/Disposicion";
import { Cargando, MensajeError, ProveedorTostadas, useTostada } from "./componentes/Mensajes";
import { EspacioMedico } from "./medico/EspacioMedico";
import { CambiarContrasena, Entrar, sinSesion } from "./paginas/Acceso";
import { Administracion } from "./paginas/Administracion";
import { Solicitudes } from "./paginas/Solicitudes";
import { Calendario } from "./paginas/Calendario";
import { Cobertura } from "./paginas/Cobertura";
import { Configuracion } from "./paginas/Configuracion";
import { Festivos } from "./paginas/Festivos";
import { Imprimir } from "./paginas/Imprimir";
import { ImprimirCalendario } from "./paginas/ImprimirCalendario";
import { ImprimirRoles } from "./paginas/ImprimirRoles";
import { Medicos } from "./paginas/Medicos";
import { Rotaciones } from "./paginas/Rotaciones";

/**
 * En el modo servidor, antes de nada: sin sesión, la página de entrada; con una
 * contraseña temporal, elegir la suya; los médicos, su vista (diseño del modo servidor, 6).
 */
function ConAcceso({ children }: { children: ReactNode }) {
  const yo = useYo();
  if (yo.isPending) return <Cargando />;
  if (yo.error) return sinSesion(yo.error) ? <Entrar /> : <MensajeError error={yo.error} />;
  if (yo.data.debe_cambiar) return <CambiarContrasena yo={yo.data} />;
  if (yo.data.rol === "MEDICO") return <EspacioMedico yo={yo.data} />;
  return children;
}

export function App() {
  return (
    <BrowserRouter>
      <ProveedorTostadas>
        <ConAcceso>
          <Rutas />
        </ConAcceso>
      </ProveedorTostadas>
    </BrowserRouter>
  );
}

/** Cambiar la propia contraseña desde la cabecera. */
function Cuenta() {
  const yo = useYo();
  const volver = useNavigate();
  const tostada = useTostada();
  if (!yo.data) return null;
  return (
    <CambiarContrasena
      yo={yo.data}
      alTerminar={() => {
        tostada("Contraseña cambiada");
        volver(-1);
      }}
    />
  );
}

function Rutas() {
  const yo = useYo();
  return (
    <Routes>
      <Route path="imprimir" element={<Imprimir />} />
      <Route path="imprimir/urgencias-domicilios" element={<ImprimirRoles />} />
      <Route path="imprimir/calendario" element={<ImprimirCalendario />} />
      <Route element={<Disposicion />}>
        <Route index element={<Calendario />} />
        <Route path="medicos" element={<Medicos />} />
        <Route path="medicos/rotaciones" element={<Rotaciones />} />
        <Route path="cobertura" element={<Cobertura />} />
        <Route path="festivos" element={<Festivos />} />
        <Route path="configuracion" element={<Configuracion />} />
        {yo.data?.modo === "servidor" && <Route path="cuenta" element={<Cuenta />} />}
        {yo.data?.modo === "servidor" && <Route path="solicitudes" element={<Solicitudes />} />}
        {yo.data?.modo === "servidor" && yo.data.rol === "ADMINISTRADOR" && (
          <Route path="administracion" element={<Administracion />} />
        )}
        {/* Direcciones de la versión anterior. */}
        <Route path="calendario" element={<Navigate to="/" replace />} />
        <Route path="ausencias" element={<Navigate to="/medicos" replace />} />
        <Route path="*" element={<p>Página no encontrada.</p>} />
      </Route>
    </Routes>
  );
}
