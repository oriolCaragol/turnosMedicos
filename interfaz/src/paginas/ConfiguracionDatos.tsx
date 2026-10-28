import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useImportar } from "../api/consultas";
import type { ResultadoImportar } from "../api/tipos";
import { Aviso, MensajeError } from "../componentes/Mensajes";

/** Exportar e importar todos los datos (médicos, reglas, ausencias, calendarios…). */
export function SeccionDatos() {
  const importar = useImportar();
  const cliente = useQueryClient();
  const selector = useRef<HTMLInputElement>(null);
  const [resultado, setResultado] = useState<ResultadoImportar | null>(null);

  const elegido = (fichero: File | undefined) => {
    if (selector.current) selector.current.value = "";
    if (!fichero) return;
    const pregunta =
      `¿Sustituir todos los datos por los de «${fichero.name}»?\n\n` +
      "Se reemplazan los médicos, sus reglas y ausencias, la cobertura, los festivos y los calendarios. " +
      "Antes se guarda una copia de los datos actuales.";
    if (!confirm(pregunta)) return;
    setResultado(null);
    importar.mutate(fichero, {
      onSuccess: (r) => {
        setResultado(r);
        void cliente.invalidateQueries(); // todo ha cambiado
      },
    });
  };

  return (
    <section className="panel">
      <h2>Datos: exportar e importar</h2>
      <p className="entradilla">
        Todos los datos (médicos, reglas, ausencias, cobertura, festivos y calendarios) están en un único fichero. Exporta una
        copia de vez en cuando y guárdala en otro sitio, o para llevarte los datos a otro ordenador o a otro usuario. También
        se hace una copia automática antes de cada actualización de la aplicación.
      </p>
      <div className="acciones">
        <a className="btn" href="/api/copia-de-seguridad" download>
          Exportar copia de los datos
        </a>
        <button type="button" className="btn" disabled={importar.isPending} onClick={() => selector.current?.click()}>
          {importar.isPending ? "Importando…" : "Importar una copia…"}
        </button>
        <input
          ref={selector}
          type="file"
          accept=".sqlite,.bak,application/vnd.sqlite3,application/x-sqlite3"
          hidden
          aria-label="Copia de los datos para importar"
          onChange={(e) => elegido(e.target.files?.[0])}
        />
      </div>
      <p className="nota">
        Importar sustituye todos los datos actuales por los de la copia. Se aceptan copias exportadas desde esta pantalla, también
        de versiones anteriores de la aplicación.
      </p>
      <MensajeError error={importar.error} />
      {resultado && (
        <Aviso>
          Datos importados: {resultado.medicos} {resultado.medicos === 1 ? "médico" : "médicos"} y {resultado.meses}{" "}
          {resultado.meses === 1 ? "mes planificado" : "meses planificados"}. Los datos que había antes están guardados en{" "}
          <code>{resultado.copia_anterior}</code>.
        </Aviso>
      )}
    </section>
  );
}
