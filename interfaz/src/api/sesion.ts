/**
 * Sesión y administración del modo servidor (diseño del modo servidor, 6 y 10).
 *
 * `useYo` dice quién usa la aplicación: en el modo personal, siempre un administrador
 * sin cuenta; en el modo servidor, el usuario de la sesión, o un error 401 si no hay
 * sesión (entonces se muestra la página de entrada, ver App.tsx).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./cliente";
import type * as T from "./tipos";

export const CLAVE_YO = ["yo"] as const;

export const useYo = () =>
  useQuery({
    queryKey: CLAVE_YO,
    queryFn: () => api<T.Yo>("GET", "/yo"),
    retry: false,
    staleTime: Infinity,
  });

/** Un nombre corto del dispositivo, para la lista de «Dispositivos conectados». */
function dispositivo(): string {
  const agente = navigator.userAgent;
  const sistema =
    ["Android", "iPhone", "iPad", "Windows", "Mac", "Linux"].find((s) => agente.includes(s === "Mac" ? "Macintosh" : s)) ??
    "dispositivo";
  const navegador = ["Firefox", "Edg", "Chrome", "Safari"].find((n) => agente.includes(n)) ?? "Navegador";
  return `${navegador.replace("Edg", "Edge")} en ${sistema}`;
}

export function useEntrar() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos: { usuario: string; contrasena: string }) =>
      api<T.Yo>("POST", "/sesion", { ...datos, dispositivo: dispositivo() }),
    onSuccess: (yo) => {
      cliente.removeQueries({
        predicate: (q) => q.queryKey[0] !== CLAVE_YO[0],
      }); // nada de otro usuario
      cliente.setQueryData(CLAVE_YO, yo);
    },
  });
}

export function useSalir() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("DELETE", "/sesion"),
    onSettled: () => {
      // Fuera los datos de este usuario; «yo» vuelve a empezar y App.tsx muestra la entrada.
      cliente.removeQueries({ predicate: (q) => q.queryKey[0] !== CLAVE_YO[0] });
      void cliente.resetQueries({ queryKey: CLAVE_YO });
    },
  });
}

export function useCambiarContrasena() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos: { actual: string; nueva: string }) => api<void>("POST", "/yo/contrasena", datos),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_YO }),
  });
}

export const useServidorPublico = () =>
  useQuery({
    queryKey: ["servidor", "publico"],
    queryFn: () => api<T.ServidorPublico>("GET", "/servidor/publico"),
    retry: false,
  });

// --- Administración ----------------------------------------------------------------

export const useUsuarios = () =>
  useQuery({
    queryKey: ["usuarios"],
    queryFn: () => api<T.UsuarioSalida[]>("GET", "/usuarios"),
  });

export function useCrearUsuario() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (datos: T.UsuarioNuevo) => api<T.ContrasenaTemporal>("POST", "/usuarios", datos),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuarios"] }),
  });
}

export function useModificarUsuario() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...datos }: T.UsuarioEntrada & { id: number }) =>
      api<T.UsuarioSalida>("PUT", `/usuarios/${id}`, datos),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: ["usuarios"] });
      void cliente.invalidateQueries({ queryKey: ["sesiones"] });
    },
  });
}

export function useRestablecer() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<T.ContrasenaTemporal>("POST", `/usuarios/${id}/restablecer`),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: ["usuarios"] });
      void cliente.invalidateQueries({ queryKey: ["sesiones"] });
    },
  });
}

export const useSesiones = () =>
  useQuery({
    queryKey: ["sesiones"],
    queryFn: () => api<T.SesionAbierta[]>("GET", "/sesiones"),
  });

export function useCerrarSesion() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>("DELETE", `/sesiones/${id}`),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["sesiones"] }),
  });
}

export const useServidor = () =>
  useQuery({
    queryKey: ["servidor"],
    queryFn: () => api<T.InfoServidor>("GET", "/servidor"),
  });

export function useCopiaAhora() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: () => api<T.CopiaServidor>("POST", "/servidor/copias"),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["servidor"] }),
  });
}
