/** Consultas y modificaciones de datos con TanStack Query. */

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback, useRef } from "react";

import { api, consulta, ErrorApi } from "./cliente";
import { marcarCambioExterno } from "./eventos";
import type * as T from "./tipos";

/** Modificación de configuración: además de lo indicado, refresca el calendario y el estado,
 * que dependen de toda la configuración. */
function useModificacion<E, S = unknown>(
  funcion: (entrada: E) => Promise<S>,
  invalidar: QueryKey[],
) {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: funcion,
    onSuccess: () =>
      Promise.all(
        [...invalidar, ["calendario"], ["estado"]].map((clave) => cliente.invalidateQueries({ queryKey: clave })),
      ),
  });
}

// --- Guardados que no se pierden al cambiar de pestaña -----------------------------

/** Guardados en curso por clave: las lecturas los esperan para no mostrar datos antiguos. */
const guardadosEnCurso = new Map<string, Promise<unknown>>();

const esperarGuardado = (clave: string) => guardadosEnCurso.get(clave)?.catch(() => undefined);

/** Espera a todos los guardados en curso (de cualquier pestaña): el calendario depende
 * de toda la configuración, así que no se genera ni se lee con cambios a medio guardar. */
const esperarTodosLosGuardados = () =>
  Promise.all([...guardadosEnCurso.values()].map((p) => p.catch(() => undefined)));

/**
 * Guardado para formularios que se guardan solos. A diferencia de un hook de
 * mutación, la función devuelta sigue funcionando aunque el componente ya se haya
 * cerrado, de modo que un cambio hecho justo antes de cambiar de pestaña se envía
 * igualmente. Los guardados de una misma clave van en orden, y al terminar se
 * refrescan las consultas indicadas, el calendario y el estado.
 */
function useGuardadoSeguro<E, S>(
  clave: string,
  funcion: (entrada: E, keepalive: boolean) => Promise<S>,
  invalidar: QueryKey[],
) {
  const cliente = useQueryClient();
  const funcionRef = useRef(funcion);
  funcionRef.current = funcion;
  const invalidarRef = useRef(invalidar);
  invalidarRef.current = invalidar;
  return useCallback(
    (entrada: E, keepalive = false): Promise<S> => {
      const anterior = guardadosEnCurso.get(clave) ?? Promise.resolve();
      const promesa: Promise<S> = anterior
        .catch(() => undefined)
        .then(() => funcionRef.current(entrada, keepalive))
        .finally(() => {
          if (guardadosEnCurso.get(clave) === promesa) guardadosEnCurso.delete(clave);
          void Promise.all(
            [...invalidarRef.current, ["calendario"], ["estado"]].map((c) => cliente.invalidateQueries({ queryKey: c })),
          );
        });
      guardadosEnCurso.set(clave, promesa);
      return promesa;
    },
    [cliente, clave],
  );
}

// --- Estado ----------------------------------------------------------------------

export const useEstado = () =>
  useQuery({ queryKey: ["estado"], queryFn: () => api<T.Estado>("GET", "/estado") });

// --- Médicos ---------------------------------------------------------------------

export const useMedicos = () =>
  useQuery({ queryKey: ["medicos"], queryFn: () => api<T.Medico[]>("GET", "/medicos") });

export const useMedico = (id: number) =>
  useQuery({ queryKey: ["medicos", id], queryFn: () => api<T.Medico>("GET", `/medicos/${id}`) });

export const useCrearMedico = () =>
  useModificacion((m: T.MedicoEntrada) => api<T.Medico>("POST", "/medicos", m), [["medicos"], ["estado"]]);

export const useModificarMedico = (id: number) =>
  useModificacion(
    (m: T.MedicoEntrada) => api<T.Medico>("PUT", `/medicos/${id}`, m),
    [["medicos"], ["estado"]],
  );

export const useBorrarMedico = () =>
  useModificacion((id: number) => api<void>("DELETE", `/medicos/${id}`), [["medicos"], ["estado"]]);

export const useReglas = (id: number, fecha: string) =>
  useQuery({
    queryKey: ["reglas", id, fecha],
    queryFn: async () => {
      await esperarGuardado(`reglas:${id}`);
      return api<T.ReglasLeidas>("GET", `/medicos/${id}/reglas${consulta({ fecha })}`);
    },
  });

/** Guarda las reglas de un médico (ver `useGuardadoSeguro`). */
export const useGuardarReglas = (id: number) =>
  useGuardadoSeguro(
    `reglas:${id}`,
    (reglas: T.ReglasGuardar, keepalive) => api<T.ReglasLeidas>("PUT", `/medicos/${id}/reglas`, reglas, keepalive),
    [["reglas", id]],
  );

// --- Ausencias -------------------------------------------------------------------

export const useAusencias = (desde: string, hasta: string) =>
  useQuery({
    queryKey: ["ausencias", desde, hasta],
    queryFn: () => api<T.Ausencia[]>("GET", `/ausencias${consulta({ desde, hasta })}`),
  });

/** Ausencias de todos los médicos que terminan en `desde` o después. */
export const useAusenciasDesde = (desde: string) =>
  useQuery({
    queryKey: ["ausencias", desde, ""],
    queryFn: () => api<T.Ausencia[]>("GET", `/ausencias${consulta({ desde })}`),
  });

export const useModificarAusencia = () =>
  useModificacion(
    ({ id, ...a }: T.AusenciaEntrada & { id: number }) => api<T.Ausencia>("PUT", `/ausencias/${id}`, a),
    [["ausencias"]],
  );

export const useCrearAusencia = () =>
  useModificacion((a: T.AusenciaEntrada) => api<T.Ausencia>("POST", "/ausencias", a), [["ausencias"]]);

export const useBorrarAusencia = () =>
  useModificacion((id: number) => api<void>("DELETE", `/ausencias/${id}`), [["ausencias"]]);

// --- Festivos --------------------------------------------------------------------

export const useFestivos = (anio: number) =>
  useQuery({
    queryKey: ["festivos", anio],
    queryFn: () => api<T.Festivo[]>("GET", `/festivos${consulta({ anio })}`),
  });

export const useAniosFestivos = () =>
  useQuery({ queryKey: ["festivos-anios"], queryFn: () => api<T.AnioFestivos[]>("GET", "/festivos/anios") });

export const useCrearFestivo = () =>
  useModificacion((f: T.FestivoEntrada) => api<T.Festivo>("POST", "/festivos", f), [["festivos"]]);

export const useBorrarFestivo = () =>
  useModificacion((id: number) => api<void>("DELETE", `/festivos/${id}`), [["festivos"]]);

export const useRestaurarFestivos = () =>
  useModificacion((anio: number) => api<T.Festivo[]>("POST", `/festivos/restaurar/${anio}`), [["festivos"]]);

// --- Municipio y festivos oficiales (Configuración) ---------------------------------

export const useMunicipio = (ine: string | undefined) =>
  useQuery({
    queryKey: ["municipio", ine],
    queryFn: () => api<T.Municipio>("GET", `/festivos/municipios/${ine}`),
    enabled: !!ine,
    staleTime: Infinity,
  });

export const useBuscarMunicipios = (texto: string) =>
  useQuery({
    queryKey: ["municipios", texto],
    queryFn: () => api<T.Municipio[]>("GET", `/festivos/municipios${consulta({ q: texto })}`),
    enabled: texto.trim().length >= 2,
    staleTime: Infinity,
  });

/** Municipio del centro (de los ajustes). */
export function useMunicipioActual() {
  const ajustes = useAjustes();
  return useMunicipio(ajustes.data?.municipio);
}

/** Consulta las fuentes en línea solo al pulsar «Buscar» (no al cargar la página). */
export const useBuscarFestivosOficiales = () =>
  useMutation({ mutationFn: (anio: number) => api<T.BusquedaFestivos>("GET", `/festivos/oficiales/${anio}`) });

export const useCargarFestivosOficiales = () =>
  useModificacion(
    (anio: number) => api<T.Festivo[]>("POST", `/festivos/oficiales/${anio}`),
    [["festivos"], ["festivos-anios"]],
  );

// --- Importar datos --------------------------------------------------------------

export const useImportar = () =>
  useMutation({ mutationFn: (fichero: File) => api<T.ResultadoImportar>("POST", "/importar", fichero) });

// --- Cobertura -------------------------------------------------------------------

export const useCoberturaSemanal = () =>
  useQuery({
    queryKey: ["cobertura-semanal"],
    queryFn: async () => {
      await esperarGuardado("cobertura");
      return api<T.CoberturaSemanal[]>("GET", "/cobertura/semanal");
    },
  });

/** Guarda la cobertura semanal (ver `useGuardadoSeguro`). */
export const useGuardarCoberturaSemanal = () =>
  useGuardadoSeguro(
    "cobertura",
    (c: T.CoberturaSemanal[], keepalive) => api<T.CoberturaSemanal[]>("PUT", "/cobertura/semanal", c, keepalive),
    [["cobertura-semanal"]],
  );

export const useCoberturaFechas = () =>
  useQuery({
    queryKey: ["cobertura-fechas"],
    queryFn: () => api<T.CoberturaFecha[]>("GET", "/cobertura/fechas"),
  });

export const useGuardarCoberturaFecha = () =>
  useModificacion(
    ({ fecha, mitades }: { fecha: string; mitades: T.CoberturaMitad[] }) =>
      api<T.CoberturaFecha[]>("PUT", `/cobertura/fechas/${fecha}`, mitades),
    [["cobertura-fechas"]],
  );

export const useBorrarCoberturaFecha = () =>
  useModificacion((fecha: string) => api<void>("DELETE", `/cobertura/fechas/${fecha}`), [["cobertura-fechas"]]);

// --- Turnos rotativos ------------------------------------------------------------------

export const useRotaciones = () =>
  useQuery({
    queryKey: ["rotaciones"],
    queryFn: async () => {
      await esperarGuardado("rotaciones");
      return api<T.Rotacion[]>("GET", "/rotaciones");
    },
  });

export const useCrearRotacion = () =>
  useModificacion((r: T.RotacionEntrada) => api<T.Rotacion>("POST", "/rotaciones", r), [["rotaciones"]]);

/** Guarda un turno rotativo (ver `useGuardadoSeguro`). */
export const useGuardarRotacion = (id: number) =>
  useGuardadoSeguro(
    "rotaciones",
    (r: T.RotacionEntrada, keepalive) => api<T.Rotacion>("PUT", `/rotaciones/${id}`, r, keepalive),
    [["rotaciones"]],
  );

export const useBorrarRotacion = () =>
  useModificacion((id: number) => api<void>("DELETE", `/rotaciones/${id}`), [["rotaciones"]]);

// --- Ajustes generales ---------------------------------------------------------------

export const useAjustes = () =>
  useQuery({ queryKey: ["ajustes"], queryFn: () => api<T.Ajustes>("GET", "/ajustes") });

export const useGuardarAjustes = () =>
  useModificacion((a: T.Ajustes) => api<T.Ajustes>("PUT", "/ajustes", a), [["ajustes"]]);

// --- Horarios --------------------------------------------------------------------

export const useHorarios = () =>
  useQuery({ queryKey: ["horarios"], queryFn: () => api<T.HorarioTurno[]>("GET", "/horarios") });

export const useGuardarHorarios = () =>
  useModificacion((h: T.HorarioTurno[]) => api<T.HorarioTurno[]>("PUT", "/horarios", h), [["horarios"]]);

// --- Calendario del mes ----------------------------------------------------------

const claveCalendario = (anio: number, mes: number) => ["calendario", anio, mes];

export const useCalendario = (anio: number, mes: number) =>
  useQuery({
    queryKey: claveCalendario(anio, mes),
    queryFn: async () => {
      await esperarTodosLosGuardados();
      return api<T.Calendario>("GET", `/periodos/${anio}/${mes}`);
    },
  });

/**
 * Modificaciones del calendario: la API devuelve el calendario completo ya validado.
 * Cada una envía la versión del mes que se está viendo (X-Version-Mes): si otro
 * usuario lo ha cambiado mientras tanto, el servidor la rechaza (409) y se vuelve a
 * pedir el calendario actual.
 */
/** Cambios del calendario en curso por mes: van uno tras otro, para que cada uno envíe la versión que dejó el anterior. */
const colaCalendario = new Map<string, Promise<unknown>>();

function useAccionCalendario<E>(
  anio: number,
  mes: number,
  funcion: (entrada: E, version: Record<string, string>) => Promise<T.Calendario>,
) {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: (entrada: E) => {
      const clave = `${anio}-${mes}`;
      const turno = (colaCalendario.get(clave) ?? Promise.resolve())
        .catch(() => undefined)
        .then(() => {
          const actual = cliente.getQueryData<T.Calendario>(claveCalendario(anio, mes));
          return funcion(entrada, actual ? { "X-Version-Mes": String(actual.version ?? 0) } : {});
        })
        .then(async (calendario) => {
          // Se guarda aquí (no solo en onSuccess) para que el siguiente de la cola lea esta versión.
          await cliente.cancelQueries({ queryKey: claveCalendario(anio, mes) });
          cliente.setQueryData(claveCalendario(anio, mes), calendario);
          return calendario;
        });
      colaCalendario.set(clave, turno);
      return turno;
    },
    // Una lectura del mes que estuviera en curso traería la versión anterior y, si llegara
    // después, pisaría la respuesta del cambio: se cancela antes y después (arriba).
    onMutate: () => cliente.cancelQueries({ queryKey: claveCalendario(anio, mes) }),
    onError: (error) => {
      if (error instanceof ErrorApi && error.estado === 409) {
        marcarCambioExterno(anio, mes);
        void cliente.invalidateQueries({ queryKey: claveCalendario(anio, mes) });
      }
    },
  });
}

export function useAccionesCalendario(anio: number, mes: number) {
  const base = `/periodos/${anio}/${mes}`;
  return {
    generar: useAccionCalendario(anio, mes, async (alternativa: boolean, v) => {
      await esperarTodosLosGuardados();
      return api<T.Calendario>("POST", `${base}/generar`, { alternativa }, false, v);
    }),
    cambiar: useAccionCalendario(anio, mes, (cambios: T.Cambio[], v) =>
      api<T.Calendario>("POST", `${base}/cambios`, cambios, false, v),
    ),
    restaurar: useAccionCalendario(anio, mes, (estado: T.EstadoManual, v) =>
      api<T.Calendario>("PUT", `${base}/manual`, estado, false, v),
    ),
    cargaManual: useAccionCalendario(anio, mes, ({ medico, carga }: { medico: number; carga: T.CargaManual }, v) =>
      api<T.Calendario>("PUT", `${base}/carga/${medico}`, carga, false, v),
    ),
    liberar: useAccionCalendario(anio, mes, (alcance: T.Liberar, v) =>
      api<T.Calendario>("POST", `${base}/liberar`, alcance, false, v),
    ),
    publicar: useAccionCalendario(anio, mes, (publicar: boolean, v) =>
      api<T.Calendario>("POST", `${base}/${publicar ? "publicar" : "reabrir"}`, undefined, false, v),
    ),
  };
}
