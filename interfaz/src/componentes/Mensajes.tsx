import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export function MensajeError({ error }: { error: unknown }) {
  if (!error) return null;
  const texto = error instanceof Error ? error.message : String(error);
  return (
    <p className="mensaje mensaje-error" role="alert">
      {texto}
    </p>
  );
}

export function Aviso({ children }: { children: ReactNode }) {
  return <div className="mensaje mensaje-aviso">{children}</div>;
}

export function Cargando() {
  return <p className="nota">Cargando…</p>;
}

const ContextoTostada = createContext<(mensaje: string) => void>(() => {});

/** Mensajes breves en la parte inferior («Guardado», «Festivo añadido»…). */
export function ProveedorTostadas({ children }: { children: ReactNode }) {
  const [mensaje, setMensaje] = useState<{ texto: string; id: number } | null>(null);
  const mostrar = useCallback((texto: string) => {
    const id = Date.now();
    setMensaje({ texto, id });
    setTimeout(() => setMensaje((m) => (m?.id === id ? null : m)), 1800);
  }, []);
  return (
    <ContextoTostada.Provider value={mostrar}>
      {children}
      {mensaje && (
        <div className="tostada" role="status">
          {mensaje.texto}
        </div>
      )}
    </ContextoTostada.Provider>
  );
}

export const useTostada = () => useContext(ContextoTostada);
