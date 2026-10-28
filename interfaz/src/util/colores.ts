/** Colores para distinguir a los médicos en el calendario. */

export const PALETA: [string, string][] = [
  ["#f4a6a6", "Rosa"],
  ["#f7c59f", "Melocotón"],
  ["#f6e27f", "Amarillo"],
  ["#c9e4a5", "Pistacho"],
  ["#8fd6b5", "Menta"],
  ["#96d7e8", "Celeste"],
  ["#a8c1f0", "Azul"],
  ["#c8b3ef", "Lavanda"],
  ["#efb3dc", "Malva"],
  ["#dcc9a8", "Arena"],
  ["#2f6f9f", "Azul oscuro"],
  ["#2e7d4f", "Verde oscuro"],
  ["#9c2f3f", "Granate"],
  ["#6e3f9e", "Morado"],
  ["#b5532a", "Teja"],
  ["#4a5560", "Pizarra"],
];

/** Color de texto legible (oscuro o blanco) sobre un fondo "#rrggbb". */
export function textoSobre(fondo: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(fondo.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminancia > 0.36 ? "#15232a" : "#ffffff";
}

/** Estilo de una ficha con el color del médico (o nada si no tiene). */
export function estiloColor(color?: string | null): React.CSSProperties | undefined {
  return color ? { background: color, color: textoSobre(color) } : undefined;
}

/** Primer color de la paleta que aún no usa nadie (para médicos nuevos). */
export function colorLibre(usados: (string | null | undefined)[]): string {
  const ocupados = new Set(usados.map((c) => c?.toLowerCase()));
  return (PALETA.find(([c]) => !ocupados.has(c)) ?? PALETA[0])[0];
}
