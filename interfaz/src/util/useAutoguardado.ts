import { useCallback, useEffect, useRef, useState } from "react";

export type EstadoGuardado = "" | "pendiente" | "guardando" | "ok" | "error";

/**
 * Guardado automático con retraso para formularios que se guardan solos.
 *
 * `programar(datos)` espera `retraso` ms sin cambios y guarda. Si antes de eso el
 * componente se cierra (cambio de pestaña) o se cierra la página, lo pendiente se
 * envía en ese momento en lugar de perderse. `enviar()` fuerza el envío.
 */
export function useAutoguardado<T>(
  guardar: (datos: T, keepalive: boolean) => Promise<unknown>,
  retraso = 450,
  alGuardar?: () => void,
) {
  const [estado, setEstado] = useState<EstadoGuardado>("");
  const [error, setError] = useState<unknown>(null);
  const pendiente = useRef<{ datos: T } | null>(null);
  const temporizador = useRef<number | undefined>(undefined);
  const guardarRef = useRef(guardar);
  guardarRef.current = guardar;
  const alGuardarRef = useRef(alGuardar);
  alGuardarRef.current = alGuardar;

  const enviar = useCallback((keepalive = false) => {
    window.clearTimeout(temporizador.current);
    const actual = pendiente.current;
    pendiente.current = null;
    if (!actual) return;
    setEstado("guardando");
    guardarRef.current(actual.datos, keepalive).then(
      () => {
        setEstado(pendiente.current ? "pendiente" : "ok");
        alGuardarRef.current?.();
      },
      (e) => {
        setError(e);
        setEstado("error");
      },
    );
  }, []);

  const programar = useCallback(
    (datos: T) => {
      pendiente.current = { datos };
      setEstado("pendiente");
      setError(null);
      window.clearTimeout(temporizador.current);
      temporizador.current = window.setTimeout(() => enviar(), retraso);
    },
    [enviar, retraso],
  );

  useEffect(() => {
    const alSalir = () => enviar(true);
    window.addEventListener("pagehide", alSalir);
    return () => {
      window.removeEventListener("pagehide", alSalir);
      enviar();
    };
  }, [enviar]);

  const reiniciar = useCallback(() => setEstado(""), []);

  return { programar, enviar, estado, error, reiniciar };
}
