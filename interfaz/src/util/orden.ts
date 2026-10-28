/**
 * Orden estable de una lista que se vuelve a pedir al servidor: los que ya estaban
 * conservan su sitio, los nuevos van al final y los que ya no están desaparecen. Así
 * una tarjeta que se está editando no salta de sitio al cambiarle el nombre; la lista
 * se vuelve a ordenar (como la devuelve el servidor) al entrar de nuevo en la pantalla.
 */
export function ordenEstable(previo: number[] | null, actuales: number[]): number[] {
  if (previo === null) return actuales;
  const presentes = new Set(actuales);
  const anteriores = new Set(previo);
  return [...previo.filter((id) => presentes.has(id)), ...actuales.filter((id) => !anteriores.has(id))];
}
