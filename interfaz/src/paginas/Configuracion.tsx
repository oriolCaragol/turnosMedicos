import { useEffect, useState, type FormEvent } from "react";

import { useAjustes, useGuardarAjustes, useGuardarHorarios, useHorarios } from "../api/consultas";
import type { Ajustes, HorarioTurno } from "../api/tipos";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { NOMBRE_TURNO } from "../util/textos";
import { SeccionDatos } from "./ConfiguracionDatos";
import { SeccionFestivosOficiales } from "./ConfiguracionFestivos";

const hhmm = (hora: string) => hora.slice(0, 5);

function ReglasGenerales() {
  const ajustes = useAjustes();
  const guardar = useGuardarAjustes();
  const tostada = useTostada();
  // Se muestra el valor nuevo al instante, mientras se guarda.
  const [local, setLocal] = useState<Ajustes | null>(null);
  if (ajustes.isError) return <MensajeError error={ajustes.error} />;
  if (!ajustes.data) return <Cargando />;
  const valores = local ?? ajustes.data;
  const cambiar = (cambios: Partial<Ajustes>) => {
    const nuevos = { ...valores, ...cambios };
    setLocal(nuevos);
    guardar.mutate(nuevos, {
      onSuccess: () => tostada("Ajuste guardado"),
      onSettled: () => setLocal(null),
    });
  };

  const porPresencia = valores.modo_carga === "PRESENCIA";
  return (
    <section className="panel">
      <h2>Reglas generales</h2>
      <p className="entradilla">Se aplican al generar o regenerar el calendario.</p>
      <label className="campo" style={{ maxWidth: 520, marginBottom: 6 }}>
        <span>Cuánto trabaja cada médico</span>
        <select
          value={valores.modo_carga}
          onChange={(e) => cambiar({ modo_carga: e.target.value as Ajustes["modo_carga"] })}
        >
          <option value="RANGOS">Según un rango de turnos al mes (mínimo y máximo) en su ficha</option>
          <option value="PRESENCIA">Todos los días laborables, salvo ausencia</option>
        </select>
      </label>
      <p className="nota">
        {porPresencia
          ? "Cada médico tiene al menos un turno cada día que no está ausente; los turnos que sobran se reparten por igual, en proporción a los días que está. No hacen falta rangos: no se piden en las fichas ni aparecen en la carga del calendario."
          : "Cada médico recibe entre el mínimo y el máximo de su ficha, reducidos en proporción a sus ausencias del mes."}
      </p>
      <label className="campo-casilla">
        <input
          type="checkbox"
          checked={valores.todos_trabajan || porPresencia}
          disabled={porPresencia}
          onChange={(e) => cambiar({ todos_trabajan: e.target.checked })}
        />
        <b>Todos los médicos trabajan cada día laborable</b>
        {porPresencia && <span className="nota"> (va incluido en «todos los días laborables»)</span>}
      </label>
      <p className="nota" style={{ marginLeft: 22 }}>
        Cada médico tiene al menos un turno cada día, salvo los días que está ausente o en que no tiene ningún turno posible
        (los dos marcados «—» en su tarjeta). Va por delante de la cobertura máxima y de la carga mensual: si chocan, se avisa
        en el calendario. Desactivada, cada médico trabaja solo los días necesarios para cubrir los turnos y su carga.
      </p>
      <label className="campo-casilla">
        <input
          type="checkbox"
          checked={valores.roles_segun_presencia}
          onChange={(e) => cambiar({ roles_segun_presencia: e.target.checked })}
        />
        <b>Urgencias y domicilios según la presencia de cada médico en el mes</b>
      </label>
      <p className="nota" style={{ marginLeft: 22 }}>
        Quien tiene ausencias ese mes recibe menos urgencias y domicilios, en proporción a las tardes en que está (por
        ejemplo, la mitad si falta medio mes). Entre médicos con la misma presencia, nunca hay más de una de diferencia.
        Desactivada, se reparten por igual entre todos, aunque tengan ausencias, siempre que tengan tardes suficientes.
      </p>
      <label className="campo" style={{ marginTop: 10, maxWidth: 520 }}>
        <span>Si no se pueden repartir las dos cosas por igual</span>
        <select
          value={valores.prioridad_roles}
          onChange={(e) => cambiar({ prioridad_roles: e.target.value as Ajustes["prioridad_roles"] })}
        >
          <option value="URGENCIAS">Urgencias siempre iguales; la diferencia, en domicilios</option>
          <option value="DOMICILIOS">Domicilios siempre iguales; la diferencia, en urgencias</option>
          <option value="IGUAL">Sin preferencia: repartir la diferencia entre los dos</option>
        </select>
      </label>
      <p className="nota">
        Las urgencias y los domicilios se reparten por igual (o según la presencia). A veces no se puede del todo: por
        ejemplo, si alguien solo puede trabajar unas pocas tardes, no le da para su parte de los dos papeles. Aquí eliges cuál
        se mantiene igual para todos.
      </p>
      <h3 style={{ marginTop: 18 }}>Vista del calendario</h3>
      <label className="campo-casilla">
        <input
          type="checkbox"
          checked={valores.mostrar_cobertura}
          onChange={(e) => cambiar({ mostrar_cobertura: e.target.checked })}
        />
        <b>Mostrar en cada turno los médicos asignados frente a los necesarios</b>
      </label>
      <p className="nota" style={{ marginLeft: 22 }}>
        Por ejemplo, «6/0–7»: 6 médicos asignados para un mínimo de 0 y un máximo de 7. Los turnos por debajo del mínimo o por
        encima del máximo se resaltan igualmente aunque no se muestre.
      </p>
      <MensajeError error={guardar.error} />
    </section>
  );
}

export function Configuracion() {
  const horarios = useHorarios();
  const guardar = useGuardarHorarios();
  const tostada = useTostada();
  const [valores, setValores] = useState<HorarioTurno[] | null>(null);
  useEffect(() => setValores(horarios.data ?? null), [horarios.data]);

  if (horarios.isError) return <MensajeError error={horarios.error} />;
  if (!valores) return <Cargando />;

  const cambiar = (i: number, campo: "inicio" | "corte" | "fin", hora: string) =>
    setValores(valores.map((h, j) => (j === i ? { ...h, [campo]: hora } : h)));

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    guardar.mutate(valores, { onSuccess: () => tostada("Horarios guardados") });
  };

  return (
    <>
      <ReglasGenerales />
      <form className="panel" onSubmit={enviar}>
        <h2>Horario de los turnos</h2>
        <p className="entradilla">
          Aparece en el calendario impreso y en la hoja de cálculo. El corte separa las dos mitades de cada turno, que se usan en
          las jornadas de turno y medio.
        </p>
        <div className="tabla-desplazable">
          <table style={{ width: "auto" }}>
            <thead>
              <tr>
                <th />
                <th>Inicio</th>
                <th>Corte</th>
                <th>Fin</th>
              </tr>
            </thead>
            <tbody>
              {valores.map((h, i) => (
                <tr key={h.turno}>
                  <th scope="row" style={{ color: `var(--${h.turno === "MANANA" ? "manana" : "tarde"})` }}>
                    {NOMBRE_TURNO[h.turno]}
                  </th>
                  {(["inicio", "corte", "fin"] as const).map((campo) => (
                    <td key={campo}>
                      <input
                        type="time"
                        aria-label={`${NOMBRE_TURNO[h.turno]}, ${campo}`}
                        value={hhmm(h[campo])}
                        onChange={(e) => cambiar(i, campo, e.target.value)}
                        required
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="acciones" style={{ marginTop: 12 }}>
          <button type="submit" className="btn primario" disabled={guardar.isPending}>
            Guardar horarios
          </button>
        </div>
        <MensajeError error={guardar.error} />
      </form>

      <SeccionFestivosOficiales />
      <SeccionDatos />
    </>
  );
}
