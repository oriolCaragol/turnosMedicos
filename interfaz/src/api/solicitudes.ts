/** Solicitudes de los médicos (diseño del modo servidor, 6.4). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./cliente";
import type * as T from "./tipos";

/** `activa`: en el modo personal no hay solicitudes (ni la ruta). */
export const useSolicitudes = (activa = true) =>
  useQuery({ queryKey: ["solicitudes"], queryFn: () => api<T.Solicitud[]>("GET", "/solicitudes"), enabled: activa });

export const useEfectos = (id: number, activo: boolean) =>
  useQuery({
    queryKey: ["solicitudes", id, "efectos"],
    queryFn: () => api<T.EfectosSolicitud>("GET", `/solicitudes/${id}/efectos`),
    enabled: activo,
  });

function useAccion<E>(funcion: (entrada: E) => Promise<T.Solicitud>) {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: funcion,
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["solicitudes"] }),
  });
}

export const useCrearSolicitud = () =>
  useAccion((datos: T.SolicitudEntrada) => api<T.Solicitud>("POST", "/solicitudes", datos));

export const useRetirar = () => useAccion((id: number) => api<T.Solicitud>("POST", `/solicitudes/${id}/retirar`));

export const useResponder = () =>
  useAccion(({ id, acepta, comentario }: { id: number; acepta: boolean; comentario?: string }) =>
    api<T.Solicitud>("POST", `/solicitudes/${id}/aceptar`, { acepta, comentario: comentario ?? "" }),
  );

export const useResolver = () =>
  useAccion(
    ({
      id,
      accion,
      comentario,
      aplicar,
    }: {
      id: number;
      accion: "aprobar" | "rechazar";
      comentario: string;
      aplicar?: boolean;
    }) => api<T.Solicitud>("POST", `/solicitudes/${id}/${accion}`, { comentario, aplicar: aplicar ?? true }),
  );

export const NOMBRE_ESTADO: Record<T.Solicitud["estado"], string> = {
  ESPERA_COMPANERO: "Esperando al compañero",
  PENDIENTE: "Pendiente",
  APROBADA: "Aprobada",
  RESUELTA: "Resuelta",
  RECHAZADA: "Rechazada",
  RETIRADA: "Retirada",
};

export const NOMBRE_TIPO: Record<T.Solicitud["tipo"], string> = {
  DISPONIBILIDAD: "Disponibilidad semanal",
  AUSENCIA: "Ausencia",
  CALENDARIO: "Cambio en el calendario",
};
