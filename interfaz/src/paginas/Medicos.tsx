import { useRef } from "react";

import { useAusenciasDesde, useCrearMedico, useMedicos } from "../api/consultas";
import type { Ausencia } from "../api/tipos";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { SubpestanasMedicos } from "../componentes/Subpestanas";
import { TarjetaMedico } from "../medicos/TarjetaMedico";
import { colorLibre } from "../util/colores";
import { nombreMes, primerDia } from "../util/fechas";
import { useMes } from "../util/mes";
import { ordenEstable } from "../util/orden";

export function Medicos() {
  const { mes } = useMes();
  const desde = primerDia(mes);
  const medicos = useMedicos();
  const ausencias = useAusenciasDesde(desde);
  const crear = useCrearMedico();
  // Mientras se está en la pestaña, cada tarjeta se queda en su sitio (un médico nuevo, al
  // final, aunque se le cambie el nombre); al volver a entrar, el orden alfabético.
  const orden = useRef<number[] | null>(null);
  if (medicos.data) orden.current = ordenEstable(orden.current, medicos.data.map((m) => m.id));
  const porId = new Map((medicos.data ?? []).map((m) => [m.id, m]));
  const lista = (orden.current ?? []).flatMap((id) => porId.get(id) ?? []);

  const porMedico = new Map<number, Ausencia[]>();
  for (const a of ausencias.data ?? []) porMedico.set(a.medico_id, [...(porMedico.get(a.medico_id) ?? []), a]);

  const anadir = () => {
    const codigos = new Set((medicos.data ?? []).map((m) => m.codigo));
    let n = 1;
    while (codigos.has(`NUEVO${n}`)) n++;
    const color = colorLibre((medicos.data ?? []).map((m) => m.color));
    crear.mutate({ nombre: "Nuevo médico", codigo: `NUEVO${n}`, activo: true, color });
  };

  return (
    <section>
      <SubpestanasMedicos />
      <h2>Médicos y sus reglas</h2>
      <p className="entradilla">
        Pulsa una casilla para cambiarla: <b>Disp.</b> (se le puede asignar), <b>Hab.</b> (su turno habitual: si trabaja ese
        día, mejor ese turno), <b>Fijo</b> (lo hace siempre, todas las semanas) o <b>—</b> (nunca); arrastra para cambiar
        varias. Se muestran las reglas vigentes en <b>{nombreMes(mes)}</b>: los cambios se guardan
        solos y valen desde ese mes en adelante, sin tocar los anteriores. Las ausencias reducen la carga del mes en proporción.
      </p>
      {medicos.isPending ? (
        <Cargando />
      ) : medicos.isError ? (
        <MensajeError error={medicos.error} />
      ) : (
        <div className="tarjetas-medicos">
          {lista.map((m) => (
            <TarjetaMedico key={m.id} medico={m} desde={desde} ausencias={porMedico.get(m.id) ?? []} />
          ))}
        </div>
      )}
      <div className="acciones" style={{ marginTop: 12 }}>
        <button type="button" className="btn primario" onClick={anadir} disabled={crear.isPending}>
          Añadir médico
        </button>
      </div>
      <MensajeError error={crear.error} />
    </section>
  );
}
