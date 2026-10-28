import { useState } from "react";

export type Vista = "cuadricula" | "lista";

const CLAVE = "turnos-vista-calendario";

function leer(): Vista {
  try {
    return localStorage.getItem(CLAVE) === "lista" ? "lista" : "cuadricula";
  } catch {
    return "cuadricula"; // almacenamiento no disponible: vista por defecto
  }
}

/** Vista del calendario elegida por el usuario; se recuerda en este navegador. */
export function useVista(): [Vista, (v: Vista) => void] {
  const [vista, setVista] = useState<Vista>(leer);
  const cambiar = (v: Vista) => {
    setVista(v);
    try {
      localStorage.setItem(CLAVE, v);
    } catch {
      // Sin almacenamiento la elección dura hasta recargar la página.
    }
  };
  return [vista, cambiar];
}
