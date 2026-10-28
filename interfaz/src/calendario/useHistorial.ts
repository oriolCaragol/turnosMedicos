import { useCallback, useEffect, useRef, useState } from "react";

import type { EstadoManual } from "../api/tipos";

const LIMITE = 50;

/**
 * Deshacer / rehacer de los cambios del calendario. Guarda "fotos" del estado
 * (asignaciones y vetos) y, al deshacer, pide al servidor que lo restaure.
 * Atajos: Ctrl+Z, Ctrl+Y y Ctrl+Mayús+Z.
 */
export function useHistorial(
  clave: string,
  actual: () => EstadoManual | undefined,
  restaurar: (estado: EstadoManual) => Promise<unknown>,
  activo: boolean,
) {
  const [atras, setAtras] = useState<EstadoManual[]>([]);
  const [adelante, setAdelante] = useState<EstadoManual[]>([]);
  const ocupado = useRef(false);

  useEffect(() => {
    setAtras([]);
    setAdelante([]);
  }, [clave]);

  const registrar = useCallback((foto: EstadoManual) => {
    setAtras((a) => [...a.slice(-(LIMITE - 1)), foto]);
    setAdelante([]);
  }, []);

  const mover = useCallback(
    async (desde: EstadoManual[], setDesde: typeof setAtras, setHacia: typeof setAtras) => {
      const objetivo = desde.at(-1);
      const ahora = actual();
      if (!objetivo || !ahora || ocupado.current) return;
      ocupado.current = true;
      try {
        await restaurar(objetivo);
        setDesde((d) => d.slice(0, -1));
        setHacia((h) => [...h, ahora]);
      } finally {
        ocupado.current = false;
      }
    },
    [actual, restaurar],
  );

  const deshacer = useCallback(() => mover(atras, setAtras, setAdelante), [mover, atras]);
  const rehacer = useCallback(() => mover(adelante, setAdelante, setAtras), [mover, adelante]);

  useEffect(() => {
    if (!activo) return;
    const teclas = (e: KeyboardEvent) => {
      const destino = e.target as HTMLElement;
      if (!(e.ctrlKey || e.metaKey) || destino.closest("input, select, textarea")) return;
      const tecla = e.key.toLowerCase();
      if (tecla === "z" && !e.shiftKey) {
        e.preventDefault();
        void deshacer();
      } else if (tecla === "y" || (tecla === "z" && e.shiftKey)) {
        e.preventDefault();
        void rehacer();
      }
    };
    window.addEventListener("keydown", teclas);
    return () => window.removeEventListener("keydown", teclas);
  }, [activo, deshacer, rehacer]);

  return { registrar, deshacer, rehacer, puedeDeshacer: atras.length > 0, puedeRehacer: adelante.length > 0 };
}
