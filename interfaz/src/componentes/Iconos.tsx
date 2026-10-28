/** Iconos SVG pequeños; heredan el color del texto (`currentColor`). */

interface Props {
  /** Nombre accesible; sin él, el icono es decorativo. */
  titulo?: string;
  tamano?: number;
}

function Svg({ titulo, tamano = 12, children }: Props & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={tamano}
      height={tamano}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={titulo ? "img" : undefined}
      aria-label={titulo}
      aria-hidden={titulo ? undefined : true}
      focusable="false"
    >
      {titulo && <title>{titulo}</title>}
      {children}
    </svg>
  );
}

/** Casa: asistencia a domicilios. */
export function IconoCasa(props: Props) {
  return (
    <Svg {...props}>
      <path d="M2 7.5 8 2.5l6 5" />
      <path d="M3.5 6.5V13.5h9V6.5" />
      <path d="M6.75 13.5v-3.5h2.5v3.5" />
    </Svg>
  );
}

/** Luz de emergencia (rotativo de ambulancia): urgencias. */
export function IconoEmergencia(props: Props) {
  return (
    <Svg {...props}>
      <path d="M4.5 12.5V9a3.5 3.5 0 0 1 7 0v3.5" fill="currentColor" fillOpacity="0.35" />
      <path d="M3 12.5h10v1.5H3z" fill="currentColor" />
      <path d="M8 1.5v1.6M3.2 3.4l1.1 1.1M12.8 3.4l-1.1 1.1M1.5 8h1.4M13.1 8h1.4" />
    </Svg>
  );
}
