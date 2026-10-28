/**
 * Cambios de otros usuarios en vivo (diseño del modo servidor, 9).
 *
 * El servidor envía un evento por cada cambio (`GET /api/eventos`); aquí se vuelve a
 * pedir lo que ha cambiado. Los eventos de esta misma pestaña se ignoran: sus cambios
 * ya se reflejan al hacerlos. Un cambio de otro usuario en un mes vacía el historial
 * de deshacer de ese mes (no se deshace lo que hizo otro).
 */
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { CLIENTE_ID } from "./cliente";

interface Evento {
  tipo:
    | "calendario"
    | "medicos"
    | "ausencias"
    | "festivos"
    | "cobertura"
    | "configuracion"
    | "rotaciones"
    | "solicitudes"
    | "todo";
  anio?: number;
  mes?: number;
  origen?: string | null;
}

/** Qué consultas cambian con cada tipo de evento (además del calendario, que casi todo afecta). */
const AFECTA: Record<Exclude<Evento["tipo"], "calendario" | "todo">, QueryKey[]> = {
  medicos: [["medicos"], ["reglas"]],
  ausencias: [["ausencias"]],
  festivos: [["festivos"], ["festivos-anios"]],
  cobertura: [["cobertura-semanal"], ["cobertura-fechas"]],
  configuracion: [["ajustes"], ["horarios"], ["municipio"]],
  rotaciones: [["rotaciones"]],
  solicitudes: [["solicitudes"]],
};

// --- Cambios externos por mes (para vaciar el historial de deshacer) -------------------

const externos = new Map<string, number>();
const avisar = new Set<() => void>();

export function marcarCambioExterno(anio: number, mes: number) {
  const clave = `${anio}-${mes}`;
  externos.set(clave, (externos.get(clave) ?? 0) + 1);
  avisar.forEach((f) => f());
}

/** Sube cada vez que otro usuario cambia ese mes. */
export function useCambiosExternos(anio: number, mes: number): number {
  return useSyncExternalStore(
    (f) => {
      avisar.add(f);
      return () => avisar.delete(f);
    },
    () => externos.get(`${anio}-${mes}`) ?? 0,
  );
}

export function aplicarEvento(cliente: QueryClient, evento: Evento) {
  if (evento.origen === CLIENTE_ID) return;
  if (evento.tipo === "todo") {
    void cliente.invalidateQueries();
    return;
  }
  if (evento.tipo === "calendario") {
    if (evento.anio && evento.mes) marcarCambioExterno(evento.anio, evento.mes);
    void cliente.invalidateQueries({ queryKey: ["calendario", evento.anio, evento.mes] });
    void cliente.invalidateQueries({ queryKey: ["calendario", "publicados"] }); // vista de los médicos
  } else if (evento.tipo === "solicitudes") {
    void cliente.invalidateQueries({ queryKey: ["solicitudes"] });
    return; // por sí sola no cambia otros datos (si se aprueba, llega además su evento)
  } else {
    for (const clave of AFECTA[evento.tipo] ?? []) void cliente.invalidateQueries({ queryKey: clave });
    void cliente.invalidateQueries({ queryKey: ["calendario"] });
  }
  void cliente.invalidateQueries({ queryKey: ["estado"] });
}

/** Escucha los eventos del servidor mientras la aplicación está abierta. */
export function useEventos() {
  const cliente = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const fuente = new EventSource("/api/eventos");
    let perdida = false;
    fuente.onmessage = (m) => {
      try {
        aplicarEvento(cliente, JSON.parse(m.data) as Evento);
      } catch {
        // un evento que no se entiende no debe romper la página
      }
    };
    fuente.onerror = () => {
      perdida = true; // EventSource reconecta solo
    };
    fuente.onopen = () => {
      // Tras una desconexión pueden haberse perdido eventos: se vuelve a pedir todo.
      if (perdida) void cliente.invalidateQueries();
      perdida = false;
    };
    return () => fuente.close();
  }, [cliente]);
}
