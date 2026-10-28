import { useEffect, useRef, type ReactNode } from "react";

import css from "./Cajon.module.css";

/** Panel lateral sobre la página (como el del prototipo): Esc o clic fuera lo cierra. */
export function Cajon({
  titulo,
  cabecera,
  pie,
  cerrar,
  children,
}: {
  titulo: string;
  cabecera: ReactNode;
  pie?: ReactNode;
  cerrar: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const teclas = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    window.addEventListener("keydown", teclas);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", teclas);
  }, [cerrar]);

  return (
    <>
      <div className={css.velo} onClick={cerrar} />
      <aside ref={panel} className={css.cajon} role="dialog" aria-label={titulo} tabIndex={-1}>
        <div className={css.cabecera}>
          <div>{cabecera}</div>
          <button type="button" className="x" onClick={cerrar} aria-label="Cerrar" style={{ fontSize: 22 }}>
            ×
          </button>
        </div>
        <div className={css.cuerpo}>{children}</div>
        {pie && <div className={css.pie}>{pie}</div>}
      </aside>
    </>
  );
}
