import { useEffect, useState } from "react";

import { formatearMedios, turnosAMedios } from "../util/textos";

interface Props {
  etiqueta: string;
  /** Valor en medios turnos; null = vacío. */
  medios: number | null;
  onChange: (medios: number | null) => void;
  opcional?: boolean;
  /** Resalta el campo (p. ej. si falta un valor necesario). */
  resaltar?: boolean;
}

/** Campo numérico en turnos (múltiplos de 0,5) que trabaja en medios turnos. */
export function CampoTurnos({ etiqueta, medios, onChange, opcional = false, resaltar = false }: Props) {
  const [texto, setTexto] = useState(medios === null ? "" : formatearMedios(medios));
  const [error, setError] = useState(false);

  useEffect(() => {
    // Sincroniza cuando el valor cambia desde fuera (p. ej. al cargar otras reglas).
    if (medios !== turnosAMedios(texto)) setTexto(medios === null ? "" : formatearMedios(medios));
  }, [medios]);

  return (
    <label className="campo">
      <span>{etiqueta}</span>
      <input
        inputMode="decimal"
        value={texto}
        placeholder={opcional ? "sin límite" : undefined}
        aria-invalid={error}
        data-resaltado={resaltar && !error ? "" : undefined}
        onChange={(e) => {
          const nuevo = e.target.value;
          setTexto(nuevo);
          if (nuevo.trim() === "" && opcional) {
            setError(false);
            onChange(null);
            return;
          }
          const valor = turnosAMedios(nuevo);
          setError(valor === null);
          if (valor !== null) onChange(valor);
        }}
      />
      {error && <small className="error">Usa múltiplos de 0,5</small>}
    </label>
  );
}
