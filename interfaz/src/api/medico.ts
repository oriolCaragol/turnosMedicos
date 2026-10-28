/** Lo que consultan los médicos en el modo servidor (diseño del modo servidor, 11.1). */
import { useQuery } from "@tanstack/react-query";

import { api, consulta } from "./cliente";
import type * as T from "./tipos";

export const useMesesPublicados = () =>
  useQuery({ queryKey: ["calendario", "publicados"], queryFn: () => api<T.MesPublicado[]>("GET", "/periodos/publicados") });

/** Ausencias de un médico (a un médico solo se le permiten las suyas, con `medico_id`). */
export const useAusenciasDe = (medico: number, desde: string, hasta?: string) =>
  useQuery({
    queryKey: ["ausencias", "medico", medico, desde, hasta ?? ""],
    queryFn: () => api<T.Ausencia[]>("GET", `/ausencias${consulta({ medico_id: medico, desde, hasta })}`),
  });
