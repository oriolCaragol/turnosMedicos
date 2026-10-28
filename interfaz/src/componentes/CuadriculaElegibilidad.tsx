import { useEffect, useRef } from "react";

import type { Elegibilidad, Turno } from "../api/tipos";
import { DIAS, DIAS_CORTOS, NOMBRE_ELEGIBILIDAD, NOMBRE_TURNO, TURNOS } from "../util/textos";
import css from "./CuadriculaElegibilidad.module.css";

export type Cuadricula = Record<`${number}-${Turno}`, Elegibilidad>;

export const clave = (dia: number, turno: Turno) => `${dia}-${turno}` as const;

const SIGUIENTE: Record<Elegibilidad, Elegibilidad> = {
  DISPONIBLE: "HABITUAL",
  HABITUAL: "FIJO",
  FIJO: "NO_DISPONIBLE",
  NO_DISPONIBLE: "DISPONIBLE",
};

const TEXTO: Record<Elegibilidad, string> = { FIJO: "Fijo", HABITUAL: "Hab.", DISPONIBLE: "Disp.", NO_DISPONIBLE: "—" };
const CLASE: Record<Elegibilidad, string> = {
  FIJO: css.fijo,
  HABITUAL: css.habitual,
  DISPONIBLE: css.disponible,
  NO_DISPONIBLE: css.no,
};
const FILA: Record<Turno, string> = { MANANA: "Mañ.", TARDE: "Tar." };

export function cuadriculaUniforme(valor: (turno: Turno) => Elegibilidad): Cuadricula {
  const c = {} as Cuadricula;
  for (let d = 0; d < 5; d++) for (const t of TURNOS) c[clave(d, t)] = valor(t);
  return c;
}

/**
 * Cuadrícula día × turno (especificaciones, 5.1).
 * Clic: Disponible → Habitual → Fijo → No disponible. Arrastrar: pinta con el mismo valor.
 * `soloLectura`: solo se muestra (la ficha de un médico en su móvil).
 */
export function CuadriculaElegibilidad({
  valor,
  onChange = () => {},
  atajos = true,
  soloLectura = false,
}: {
  valor: Cuadricula;
  onChange?: (valor: Cuadricula) => void;
  atajos?: boolean;
  soloLectura?: boolean;
}) {
  const pincel = useRef<Elegibilidad | null>(null);
  const actual = useRef(valor);
  actual.current = valor;

  useEffect(() => {
    const soltar = () => (pincel.current = null);
    window.addEventListener("pointerup", soltar);
    return () => window.removeEventListener("pointerup", soltar);
  }, []);

  const pintar = (k: keyof Cuadricula, v: Elegibilidad) => {
    if (!soloLectura && actual.current[k] !== v) onChange({ ...actual.current, [k]: v });
  };

  return (
    <div className={css.contenedor}>
      <div className={css.rejilla} onPointerLeave={() => (pincel.current = null)}>
        <span />
        {DIAS_CORTOS.map((d, i) => (
          <span key={d} className={css.dia} title={DIAS[i]}>
            {d}
          </span>
        ))}
        {TURNOS.map((t) => [
          <span key={t} className={`${css.turno} ${t === "MANANA" ? css.manana : css.tarde}`}>
            {FILA[t]}
          </span>,
          ...DIAS.map((dia, d) => {
            const k = clave(d, t);
            const v = valor[k];
            return (
              <button
                key={k}
                type="button"
                className={`${css.celda} ${CLASE[v]}`}
                aria-label={`${dia}, ${NOMBRE_TURNO[t].toLowerCase()}: ${NOMBRE_ELEGIBILIDAD[v]}`}
                aria-disabled={soloLectura || undefined}
                tabIndex={soloLectura ? -1 : undefined}
                onPointerDown={(e) => {
                  if (e.button !== 0 || soloLectura) return;
                  e.preventDefault();
                  pincel.current = SIGUIENTE[v];
                  pintar(k, SIGUIENTE[v]);
                }}
                onPointerEnter={() => pincel.current && pintar(k, pincel.current)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    pintar(k, SIGUIENTE[v]);
                  }
                }}
              >
                {TEXTO[v]}
              </button>
            );
          }),
        ])}
      </div>
      {atajos && !soloLectura && (
        <div className={css.atajos}>
          <button type="button" className="btn pequeno" onClick={() => onChange(cuadriculaUniforme(() => "DISPONIBLE"))}>
            Cualquiera
          </button>
          <button
            type="button"
            className="btn pequeno"
            onClick={() => onChange(cuadriculaUniforme((t) => (t === "MANANA" ? "DISPONIBLE" : "NO_DISPONIBLE")))}
          >
            Solo mañanas
          </button>
          <button
            type="button"
            className="btn pequeno"
            onClick={() => onChange(cuadriculaUniforme((t) => (t === "TARDE" ? "DISPONIBLE" : "NO_DISPONIBLE")))}
          >
            Solo tardes
          </button>
        </div>
      )}
    </div>
  );
}
