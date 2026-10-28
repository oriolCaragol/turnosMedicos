import { useEffect, useState, type FormEvent } from "react";

import {
  useBorrarCoberturaFecha,
  useCoberturaFechas,
  useCoberturaSemanal,
  useGuardarCoberturaFecha,
  useGuardarCoberturaSemanal,
} from "../api/consultas";
import type { CoberturaSemanal, Mitad, Turno } from "../api/tipos";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { useAutoguardado } from "../util/useAutoguardado";
import { formatearFecha } from "../util/fechas";
import { DIAS, MITADES, MITADES_DE, NOMBRE_TURNO, TURNOS } from "../util/textos";

type Valores = Record<`${number}-${Mitad}`, { minimo: number; maximo: number }>;
const k = (d: number, h: Mitad) => `${d}-${h}` as const;
const COLOR: Record<Turno, string> = { MANANA: "var(--manana)", TARDE: "var(--tarde)" };
const MITAD_CORTA: Record<Mitad, string> = { M1: "1.ª mitad", M2: "2.ª mitad", T1: "1.ª mitad", T2: "2.ª mitad" };

function Numero({ valor, onChange, etiqueta }: { valor: number; onChange: (v: number) => void; etiqueta: string }) {
  return (
    <input
      type="number"
      min={0}
      max={50}
      aria-label={etiqueta}
      value={valor}
      onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
    />
  );
}

export function Cobertura() {
  return (
    <>
      <CoberturaSemanalPanel />
      <Excepciones />
    </>
  );
}

function CoberturaSemanalPanel() {
  const datos = useCoberturaSemanal();
  const tostada = useTostada();
  const guardado = useAutoguardado(useGuardarCoberturaSemanal(), 500, () => tostada("Cobertura guardada"));
  const [valores, setValores] = useState<Valores | null>(null);
  const [porMitades, setPorMitades] = useState(false);

  // Espera a la lectura fresca (que espera a un guardado en curso), no a la copia en caché.
  useEffect(() => {
    if (!datos.data || datos.isFetching || valores) return;
    const v = {} as Valores;
    for (const c of datos.data) v[k(c.dia_semana, c.mitad)] = { minimo: c.minimo, maximo: c.maximo };
    setValores(v);
    setPorMitades(
      [0, 1, 2, 3, 4].some((d) =>
        TURNOS.some((t) => {
          const [a, b] = MITADES_DE[t].map((h) => v[k(d, h)]);
          return a.minimo !== b.minimo || a.maximo !== b.maximo;
        }),
      ),
    );
  }, [datos.data, datos.isFetching, valores]);

  if (datos.isError) return <MensajeError error={datos.error} />;
  if (!valores) return <Cargando />;

  /** Cambia los valores y programa el guardado automático. */
  const editar = (nuevo: Valores) => {
    setValores(nuevo);
    const lista: CoberturaSemanal[] = [];
    for (let d = 0; d < 5; d++) for (const h of MITADES) lista.push({ dia_semana: d, mitad: h, ...nuevo[k(d, h)] });
    guardado.programar(lista);
  };

  const cambiar = (d: number, mitades: Mitad[], campo: "minimo" | "maximo", valor: number) => {
    const nuevo = { ...valores };
    for (const h of mitades) {
      const actual = { ...nuevo[k(d, h)], [campo]: valor };
      if (campo === "minimo" && actual.maximo < valor) actual.maximo = valor;
      if (campo === "maximo" && actual.minimo > valor) actual.minimo = valor;
      nuevo[k(d, h)] = actual;
    }
    editar(nuevo);
  };

  const copiarLunes = () => {
    const nuevo = { ...valores };
    for (let d = 1; d < 5; d++) for (const h of MITADES) nuevo[k(d, h)] = { ...valores[k(0, h)] };
    editar(nuevo);
  };

  const grupos = TURNOS.map((t) => ({
    turno: t,
    columnas: porMitades ? MITADES_DE[t].map((h) => ({ titulo: MITAD_CORTA[h], mitades: [h] })) : [{ titulo: "", mitades: MITADES_DE[t] }],
  }));

  return (
    <section className="panel">
      <h2>Médicos necesarios por turno</h2>
      <p className="entradilla">
        El mínimo es obligatorio: el calendario avisa de cualquier turno por debajo. El máximo no se supera salvo por turnos
        fijos o cambios a mano, que también se avisan. Los cambios se guardan solos.
      </p>
      <div className="tabla-desplazable">
        <table>
          <thead>
            <tr>
              <th />
              {grupos.map((g) => (
                <th key={g.turno} colSpan={g.columnas.length * 2} style={{ color: COLOR[g.turno] }}>
                  {NOMBRE_TURNO[g.turno]}
                </th>
              ))}
            </tr>
            <tr>
              <th>Día</th>
              {grupos.flatMap((g) =>
                g.columnas.flatMap((c) => [
                  <th key={`${g.turno}${c.titulo}min`}>{c.titulo ? `${c.titulo} · mín.` : "Mín."}</th>,
                  <th key={`${g.turno}${c.titulo}max`}>{c.titulo ? `${c.titulo} · máx.` : "Máx."}</th>,
                ]),
              )}
            </tr>
          </thead>
          <tbody>
            {DIAS.map((dia, d) => (
              <tr key={dia}>
                <td style={{ fontWeight: 600 }}>{dia}</td>
                {grupos.flatMap((g) =>
                  g.columnas.flatMap((c) =>
                    (["minimo", "maximo"] as const).map((campo) => (
                      <td key={`${g.turno}${c.titulo}${campo}`}>
                        <Numero
                          etiqueta={`${dia}, ${NOMBRE_TURNO[g.turno].toLowerCase()}${c.titulo ? ` (${c.titulo})` : ""}, ${campo === "minimo" ? "mínimo" : "máximo"}`}
                          valor={valores[k(d, c.mitades[0])][campo]}
                          onChange={(v) => cambiar(d, c.mitades, campo, v)}
                        />
                      </td>
                    )),
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="acciones" style={{ marginTop: 12 }}>
        <button type="button" className="btn" onClick={copiarLunes}>
          Copiar el lunes a toda la semana
        </button>
        <label className="campo-casilla">
          <input type="checkbox" checked={porMitades} onChange={(e) => setPorMitades(e.target.checked)} />
          Detallar por mitades de turno
        </label>
        <span className="nota">
          {guardado.estado === "pendiente" || guardado.estado === "guardando" ? "Guardando…" : ""}
        </span>
      </div>
      <p className="nota">
        Por mitades: útil con jornadas de turno y medio, que cubren solo la primera mitad de la tarde o la segunda de la mañana.
      </p>
      <MensajeError error={guardado.error} />
    </section>
  );
}

function Excepciones() {
  const fechas = useCoberturaFechas();
  const guardar = useGuardarCoberturaFecha();
  const borrar = useBorrarCoberturaFecha();
  const tostada = useTostada();
  const [fecha, setFecha] = useState("");
  const [turnos, setTurnos] = useState({ MANANA: { minimo: 1, maximo: 1 }, TARDE: { minimo: 1, maximo: 1 } });

  const porFecha = new Map<string, Record<Mitad, { minimo: number; maximo: number }>>();
  for (const c of fechas.data ?? []) {
    const fila = porFecha.get(c.fecha) ?? ({} as Record<Mitad, { minimo: number; maximo: number }>);
    fila[c.mitad] = { minimo: c.minimo, maximo: c.maximo };
    porFecha.set(c.fecha, fila);
  }
  const rango = (a?: { minimo: number; maximo: number }, b?: { minimo: number; maximo: number }) => {
    const texto = (v?: { minimo: number; maximo: number }) => (v ? `${v.minimo}–${v.maximo}` : "");
    return texto(a) === texto(b) ? texto(a) : `${texto(a)} / ${texto(b)}`;
  };

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    guardar.mutate(
      { fecha, mitades: MITADES.map((h) => ({ mitad: h, ...turnos[h.startsWith("M") ? "MANANA" : "TARDE"] })) },
      { onSuccess: () => tostada("Excepción guardada") },
    );
  };

  return (
    <section className="panel">
      <h2>Excepciones por fecha</h2>
      <p className="entradilla">Sustituyen la cobertura semanal en un día concreto, por ejemplo con plantilla reducida el 24 de diciembre.</p>
      <form className="fila-formulario" onSubmit={enviar} style={{ marginBottom: 12 }}>
        <label className="campo">
          <span>Fecha</span>
          <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required />
        </label>
        {TURNOS.map((t) =>
          (["minimo", "maximo"] as const).map((campo) => (
            <label className="campo" key={`${t}-${campo}`}>
              <span style={{ color: COLOR[t] }}>
                {NOMBRE_TURNO[t]} {campo === "minimo" ? "mín." : "máx."}
              </span>
              <Numero
                etiqueta={`${NOMBRE_TURNO[t]} ${campo === "minimo" ? "mínimo" : "máximo"}`}
                valor={turnos[t][campo]}
                onChange={(v) => setTurnos({ ...turnos, [t]: { ...turnos[t], [campo]: v } })}
              />
            </label>
          )),
        )}
        <button type="submit" className="btn primario" disabled={guardar.isPending}>
          Guardar excepción
        </button>
      </form>
      <MensajeError error={guardar.error ?? borrar.error} />
      {fechas.isPending ? (
        <Cargando />
      ) : porFecha.size === 0 ? (
        <p className="nota">No hay excepciones.</p>
      ) : (
        <div className="tabla-desplazable">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th style={{ color: COLOR.MANANA }}>Mañana</th>
                <th style={{ color: COLOR.TARDE }}>Tarde</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {[...porFecha.entries()].map(([f, m]) => (
                <tr key={f}>
                  <td className="num">{formatearFecha(f)}</td>
                  <td className="num">{rango(m.M1, m.M2)}</td>
                  <td className="num">{rango(m.T1, m.T2)}</td>
                  <td>
                    <button type="button" className="x" aria-label={`Quitar la excepción del ${formatearFecha(f)}`} onClick={() => borrar.mutate(f)}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
