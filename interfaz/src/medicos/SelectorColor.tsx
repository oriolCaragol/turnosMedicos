import { useEffect, useRef, useState } from "react";

import { PALETA, textoSobre } from "../util/colores";
import css from "./SelectorColor.module.css";

/** Muestra de color que abre una paleta para elegir el color del médico. */
export function SelectorColor({
  color,
  nombre,
  onChange,
}: {
  color: string | null | undefined;
  nombre: string;
  onChange: (color: string | null) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  const libre = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: PointerEvent) => !caja.current?.contains(e.target as Node) && setAbierto(false);
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && setAbierto(false);
    window.addEventListener("pointerdown", fuera);
    window.addEventListener("keydown", tecla);
    return () => {
      window.removeEventListener("pointerdown", fuera);
      window.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  const elegir = (nuevo: string | null) => {
    onChange(nuevo);
    setAbierto(false);
  };

  return (
    <div className={css.selector} ref={caja}>
      <button
        type="button"
        className={css.muestra}
        style={color ? { background: color, color: textoSobre(color) } : undefined}
        aria-label={`Color de ${nombre}: ${color ? (PALETA.find(([c]) => c === color)?.[1] ?? color) : "sin color"}`}
        aria-expanded={abierto}
        title="Color en el calendario"
        onClick={() => setAbierto(!abierto)}
      >
        {color ? "" : "∅"}
      </button>
      {abierto && (
        <div className={css.paleta} role="dialog" aria-label={`Elegir el color de ${nombre}`}>
          <div className={css.colores}>
            {PALETA.map(([c, texto]) => (
              <button
                key={c}
                type="button"
                className={css.color}
                style={{ background: c }}
                aria-label={texto}
                aria-pressed={c === color}
                title={texto}
                onClick={() => elegir(c)}
              />
            ))}
          </div>
          <div className={css.otras}>
            <label className="nota">
              Otro:{" "}
              <input
                type="color"
                aria-label="Otro color"
                value={color ?? "#888888"}
                onChange={(e) => {
                  const valor = e.target.value;
                  window.clearTimeout(libre.current);
                  libre.current = window.setTimeout(() => onChange(valor), 300);
                }}
              />
            </label>
            <button type="button" className="btn pequeno" onClick={() => elegir(null)}>
              Sin color
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
