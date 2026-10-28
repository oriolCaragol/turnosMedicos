import { useCrearRotacion, useMedicos, useRotaciones } from "../api/consultas";
import { Cargando, MensajeError } from "../componentes/Mensajes";
import { SubpestanasMedicos } from "../componentes/Subpestanas";
import { semanasDelMes } from "../rotaciones/semanas";
import { TarjetaRotacion } from "../rotaciones/TarjetaRotacion";
import { useMes } from "../util/mes";

export function Rotaciones() {
  const { mes } = useMes();
  const rotaciones = useRotaciones();
  const medicos = useMedicos();
  const crear = useCrearRotacion();

  return (
    <section>
      <SubpestanasMedicos />
      <h2>Turnos rotativos</h2>
      <p className="entradilla">
        Grupos de médicos que comparten unos turnos de la semana sin coincidir: cada semana los hace uno del grupo, por orden,
        como turno <b>fijo</b>, y los demás no los tienen. Si a quien le toca está ausente o es festivo, ese día lo cubre el
        resto del equipo. La cuenta de semanas sigue de un mes a otro.
      </p>
      {rotaciones.isPending || medicos.isPending ? (
        <Cargando />
      ) : rotaciones.isError ? (
        <MensajeError error={rotaciones.error} />
      ) : (
        <>
          {rotaciones.data.length === 0 && <p className="nota">Todavía no hay turnos rotativos.</p>}
          <div className="tarjetas-medicos">
            {rotaciones.data.map((r) => (
              <TarjetaRotacion key={r.id} rotacion={r} medicos={medicos.data ?? []} mes={mes} />
            ))}
          </div>
        </>
      )}
      <div className="acciones" style={{ marginTop: 12 }}>
        <button
          type="button"
          className="btn primario"
          disabled={crear.isPending}
          onClick={() =>
            crear.mutate({
              nombre: "Nuevo turno rotativo",
              // Primera semana del mes con días laborables (el día 1 puede caer en fin de semana).
              desde: semanasDelMes(mes)[0],
              activa: true,
              medicos: [],
              huecos: [],
            })
          }
        >
          Añadir turno rotativo
        </button>
      </div>
      <MensajeError error={crear.error} />
    </section>
  );
}
