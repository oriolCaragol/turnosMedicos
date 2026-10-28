/** Llamadas a la API JSON del servidor Python. */

export class ErrorApi extends Error {
  constructor(
    public estado: number,
    mensaje: string,
  ) {
    super(mensaje);
  }
}

type Detalle = string | { msg: string; loc?: (string | number)[] }[];

function mensajeDeError(detalle: Detalle | undefined, estado: number): string {
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle) && detalle.length > 0) {
    // Errores de validación de FastAPI: "Value error, El máximo no puede…"
    return detalle.map((d) => d.msg.replace(/^Value error, /, "")).join(". ");
  }
  return `Error del servidor (${estado})`;
}

/**
 * Identificador de esta pestaña: el servidor lo devuelve en los eventos de los cambios
 * que hace, para distinguirlos de los de otros usuarios (api/eventos.ts).
 */
export const CLIENTE_ID: string =
  globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

/**
 * Llamada a la API. `keepalive` permite que la petición termine aunque se esté
 * cerrando la página (para no perder un guardado pendiente). `cabeceras`: por
 * ejemplo, la versión del mes que se conoce (X-Version-Mes).
 */
export async function api<T>(
  metodo: string,
  ruta: string,
  cuerpo?: unknown,
  keepalive = false,
  cabeceras: Record<string, string> = {},
): Promise<T> {
  // Un fichero (Blob) se envía tal cual; lo demás, como JSON.
  const fichero = cuerpo instanceof Blob;
  const respuesta = await fetch(`/api${ruta}`, {
    method: metodo,
    keepalive,
    headers: {
      "X-Cliente": CLIENTE_ID,
      ...(cuerpo === undefined
        ? {}
        : { "Content-Type": fichero ? cuerpo.type || "application/octet-stream" : "application/json" }),
      ...cabeceras,
    },
    body: cuerpo === undefined ? undefined : fichero ? cuerpo : JSON.stringify(cuerpo),
  });
  if (!respuesta.ok) {
    let detalle: Detalle | undefined;
    try {
      detalle = (await respuesta.json()).detail;
    } catch {
      detalle = undefined;
    }
    throw new ErrorApi(respuesta.status, mensajeDeError(detalle, respuesta.status));
  }
  return respuesta.status === 204 ? (undefined as T) : respuesta.json();
}

export function consulta(parametros: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== undefined) p.set(clave, String(valor));
  }
  const texto = p.toString();
  return texto ? `?${texto}` : "";
}
