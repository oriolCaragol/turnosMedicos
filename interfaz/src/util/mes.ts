import { useSearchParams } from "react-router-dom";

import { mesSiguiente } from "./fechas";

/** Suma `delta` meses a "AAAA-MM". */
export function desplazarMes(mes: string, delta: number): string {
  const [a, m] = mes.split("-").map(Number);
  const total = a * 12 + (m - 1) + delta;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

/**
 * Mes de trabajo compartido por todas las pestañas, guardado en la URL
 * (`?mes=AAAA-MM`). Por defecto, el mes siguiente: el que se planifica.
 */
export function useMes() {
  const [parametros, setParametros] = useSearchParams();
  const texto = parametros.get("mes");
  const mes = texto && /^\d{4}-\d{2}$/.test(texto) ? texto : mesSiguiente();
  const [anio, numMes] = mes.split("-").map(Number);
  const cambiar = (nuevo: string) => {
    const p = new URLSearchParams(parametros);
    p.set("mes", nuevo);
    setParametros(p);
  };
  return { mes, anio, numMes, cambiar };
}
