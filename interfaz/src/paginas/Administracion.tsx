/**
 * Administración del modo servidor (diseño del modo servidor, 6.3 y 10.2): cuentas,
 * dispositivos conectados, direcciones con su QR, certificado y copias. Solo para el
 * administrador.
 */
import { useState, type FormEvent } from "react";

import { useMedicos } from "../api/consultas";
import {
  useCerrarSesion,
  useCopiaAhora,
  useCrearUsuario,
  useModificarUsuario,
  useRestablecer,
  useServidor,
  useSesiones,
  useUsuarios,
} from "../api/sesion";
import type { ContrasenaTemporal, RolUsuario, UsuarioSalida } from "../api/tipos";
import { Cargando, MensajeError, useTostada } from "../componentes/Mensajes";
import { InstruccionesCertificado } from "./Acceso";

const ROLES: Record<RolUsuario, string> = {
  ADMINISTRADOR: "Administrador",
  PLANIFICADOR: "Planificador",
  MEDICO: "Médico",
};

const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString("es-ES", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

export function Administracion() {
  return (
    <>
      <SeccionUsuarios />
      <SeccionSesiones />
      <SeccionServidor />
    </>
  );
}

/** La contraseña temporal solo se ve una vez: hay que dársela a la persona. */
function Temporal({ datos, cerrar }: { datos: ContrasenaTemporal; cerrar: () => void }) {
  return (
    <div className="mensaje mensaje-aviso" role="status">
      <p>
        Contraseña temporal de <strong>{datos.usuario.nombre_visible}</strong> (usuario{" "}
        <strong>{datos.usuario.nombre}</strong>):{" "}
        <span className="num" data-temporal>
          {datos.contrasena_temporal}
        </span>
      </p>
      <p className="nota">Dásela en persona; al entrar, elegirá la suya. No se volverá a mostrar.</p>
      <button type="button" className="btn pequeno" onClick={cerrar}>
        Hecho
      </button>
    </div>
  );
}

function SeccionUsuarios() {
  const usuarios = useUsuarios();
  const medicos = useMedicos();
  const crear = useCrearUsuario();
  const restablecer = useRestablecer();
  const [temporal, setTemporal] = useState<ContrasenaTemporal | null>(null);
  const [editando, setEditando] = useState<number | null>(null);
  const vacio = {
    nombre: "",
    nombre_visible: "",
    rol: "MEDICO" as RolUsuario,
    medico_id: null as number | null,
  };
  const [nuevo, setNuevo] = useState(vacio);

  const vinculados = new Set((usuarios.data ?? []).map((u) => u.medico_id));
  const nombreMedico = (id: number | null) => medicos.data?.find((m) => m.id === id)?.nombre;

  const elegirMedico = (id: number | null) => {
    const medico = medicos.data?.find((m) => m.id === id);
    setNuevo((n) => ({
      ...n,
      medico_id: id,
      nombre_visible: n.nombre_visible || medico?.nombre || "",
      nombre: n.nombre || (medico?.codigo ?? "").toLowerCase(),
    }));
  };

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    crear.mutate(
      {
        ...nuevo,
        activo: true,
        medico_id: nuevo.rol === "MEDICO" ? nuevo.medico_id : null,
      },
      {
        onSuccess: (r) => {
          setTemporal(r);
          setNuevo(vacio);
        },
      },
    );
  };

  return (
    <section className="panel">
      <h2>Usuarios</h2>
      <p className="entradilla">
        Cada persona tiene su cuenta. Los médicos consultan sus turnos y su ficha; el planificador prepara los calendarios;
        el administrador, además, gestiona las cuentas y el servidor.
      </p>
      {temporal && <Temporal datos={temporal} cerrar={() => setTemporal(null)} />}
      {usuarios.isPending ? (
        <Cargando />
      ) : (
        <div className="tabla-desplazable">
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Ficha</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(usuarios.data ?? []).map((u) =>
                editando === u.id ? (
                  <FilaEdicion key={u.id} usuario={u} cerrar={() => setEditando(null)} />
                ) : (
                  <tr key={u.id} data-usuario={u.nombre}>
                    <td>{u.nombre_visible}</td>
                    <td className="num">{u.nombre}</td>
                    <td>{ROLES[u.rol]}</td>
                    <td>
                      {nombreMedico(u.medico_id) ?? (u.rol === "MEDICO" ? <span className="error">sin vincular</span> : "—")}
                    </td>
                    <td>{!u.activo ? "Desactivada" : u.debe_cambiar ? "Contraseña temporal" : "Activa"}</td>
                    <td>
                      <div className="acciones">
                        <button type="button" className="btn pequeno" onClick={() => setEditando(u.id)}>
                          Editar
                        </button>
                        <button
                          type="button"
                          className="btn pequeno"
                          disabled={restablecer.isPending}
                          onClick={() => {
                            if (
                              confirm(`¿Dar una contraseña temporal nueva a ${u.nombre_visible}? Se cerrarán sus sesiones.`)
                            )
                              restablecer.mutate(u.id, {
                                onSuccess: setTemporal,
                              });
                          }}
                        >
                          Nueva contraseña
                        </button>
                      </div>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
      <MensajeError error={restablecer.error} />

      <h3>Cuenta nueva</h3>
      <form className="fila-formulario" onSubmit={enviar}>
        <label className="campo">
          <span>Rol</span>
          <select value={nuevo.rol} onChange={(e) => setNuevo({ ...nuevo, rol: e.target.value as RolUsuario })}>
            {Object.entries(ROLES).map(([valor, texto]) => (
              <option key={valor} value={valor}>
                {texto}
              </option>
            ))}
          </select>
        </label>
        {nuevo.rol === "MEDICO" && (
          <label className="campo">
            <span>Ficha del médico</span>
            <select
              value={nuevo.medico_id ?? ""}
              onChange={(e) => elegirMedico(e.target.value ? Number(e.target.value) : null)}
              required
            >
              <option value="">Elige…</option>
              {(medicos.data ?? [])
                .filter((m) => m.activo && !vinculados.has(m.id))
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nombre}
                  </option>
                ))}
            </select>
          </label>
        )}
        <label className="campo">
          <span>Nombre visible</span>
          <input
            value={nuevo.nombre_visible}
            onChange={(e) => setNuevo({ ...nuevo, nombre_visible: e.target.value })}
            required
          />
        </label>
        <label className="campo">
          <span>Usuario</span>
          <input
            value={nuevo.nombre}
            onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })}
            autoCapitalize="none"
            pattern="[A-Za-z0-9._\-]+"
            title="Letras, números, «.», «_» y «-»"
            required
          />
        </label>
        <button type="submit" className="btn primario" disabled={crear.isPending}>
          Crear cuenta
        </button>
      </form>
      <MensajeError error={crear.error} />
    </section>
  );
}

function FilaEdicion({ usuario, cerrar }: { usuario: UsuarioSalida; cerrar: () => void }) {
  const medicos = useMedicos();
  const modificar = useModificarUsuario();
  const [datos, setDatos] = useState({
    nombre_visible: usuario.nombre_visible,
    rol: usuario.rol,
    medico_id: usuario.medico_id,
    activo: usuario.activo,
  });
  return (
    <tr data-usuario={usuario.nombre}>
      <td>
        <input
          aria-label="Nombre visible"
          value={datos.nombre_visible}
          onChange={(e) => setDatos({ ...datos, nombre_visible: e.target.value })}
        />
      </td>
      <td className="num">{usuario.nombre}</td>
      <td>
        <select
          aria-label="Rol"
          value={datos.rol}
          onChange={(e) => setDatos({ ...datos, rol: e.target.value as RolUsuario })}
        >
          {Object.entries(ROLES).map(([valor, texto]) => (
            <option key={valor} value={valor}>
              {texto}
            </option>
          ))}
        </select>
      </td>
      <td>
        {datos.rol === "MEDICO" ? (
          <select
            aria-label="Ficha del médico"
            value={datos.medico_id ?? ""}
            onChange={(e) =>
              setDatos({
                ...datos,
                medico_id: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">Sin vincular</option>
            {(medicos.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre}
              </option>
            ))}
          </select>
        ) : (
          "—"
        )}
      </td>
      <td>
        <label className="campo-casilla">
          <input type="checkbox" checked={datos.activo} onChange={(e) => setDatos({ ...datos, activo: e.target.checked })} />
          Activa
        </label>
      </td>
      <td>
        <div className="acciones">
          <button
            type="button"
            className="btn pequeno primario"
            disabled={modificar.isPending}
            onClick={() => modificar.mutate({ id: usuario.id, ...datos }, { onSuccess: cerrar })}
          >
            Guardar
          </button>
          <button type="button" className="btn pequeno" onClick={cerrar}>
            Cancelar
          </button>
        </div>
        <MensajeError error={modificar.error} />
      </td>
    </tr>
  );
}

function SeccionSesiones() {
  const sesiones = useSesiones();
  const cerrar = useCerrarSesion();
  return (
    <section className="panel">
      <h2>Dispositivos conectados</h2>
      <p className="entradilla">
        Cada sesión dura 30 días desde su último uso. Cierra la de un dispositivo perdido o que ya no se usa.
      </p>
      {sesiones.isPending ? (
        <Cargando />
      ) : (
        <div className="tabla-desplazable">
          <table>
            <thead>
              <tr>
                <th>Persona</th>
                <th>Dispositivo</th>
                <th>Desde</th>
                <th>Último uso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(sesiones.data ?? []).map((s) => (
                <tr key={s.id}>
                  <td>{s.nombre_visible}</td>
                  <td>{s.dispositivo}</td>
                  <td>{fechaHora(s.creada)}</td>
                  <td>{fechaHora(s.ultimo_uso)}</td>
                  <td>
                    {s.actual ? (
                      <span className="nota">Este dispositivo</span>
                    ) : (
                      <button type="button" className="btn pequeno" onClick={() => cerrar.mutate(s.id)}>
                        Cerrar sesión
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <MensajeError error={cerrar.error} />
    </section>
  );
}

function SeccionServidor() {
  const servidor = useServidor();
  const copia = useCopiaAhora();
  const tostada = useTostada();
  const info = servidor.data;
  if (!info) return servidor.isPending ? <Cargando /> : <MensajeError error={servidor.error} />;
  return (
    <section className="panel">
      <h2>Servidor</h2>
      <p className="entradilla">
        Abre una de estas direcciones desde cualquier dispositivo de la red de casa. Si el móvil no encuentra el nombre
        «.local», usa la de los números o escanea su código.
      </p>
      <div className="acciones" style={{ alignItems: "flex-start" }}>
        {info.direcciones.map((d) => (
          <figure key={d} style={{ margin: 0, textAlign: "center" }}>
            <img
              src={`/api/servidor/qr.svg?direccion=${encodeURIComponent(d)}`}
              alt={`Código QR de ${d}`}
              width={150}
              height={150}
            />
            <figcaption className="num">
              <a href={d}>{d}</a>
            </figcaption>
          </figure>
        ))}
      </div>
      {!info.https && (
        <p className="mensaje mensaje-error">
          Sin HTTPS: los datos y las contraseñas viajan sin cifrar. Úsalo solo para pruebas.
        </p>
      )}
      {info.https && (
        <>
          <h3>Certificado</h3>
          <p className="nota">
            El del servidor caduca el{" "}
            {info.certificado_caduca ? new Date(info.certificado_caduca).toLocaleDateString("es-ES") : "—"} y se renueva solo
            un mes antes. La autoridad, que es lo que se instala en cada dispositivo, dura 10 años.
          </p>
          <InstruccionesCertificado huella={info.huella_autoridad} />
        </>
      )}
      <h3>Copias de seguridad</h3>
      <p className="nota">
        Una al día, automática; se conservan las de los últimos {info.conservar_copias} días, además de las hechas a mano.
        Datos: <span className="num">{info.datos}</span>
      </p>
      <div className="acciones">
        <button
          type="button"
          className="btn"
          disabled={copia.isPending}
          onClick={() =>
            copia.mutate(undefined, {
              onSuccess: (c) => tostada(`Copia hecha: ${c.nombre}`),
            })
          }
        >
          Hacer una copia ahora
        </button>
      </div>
      <MensajeError error={copia.error} />
      <ul className="nota">
        {info.copias.slice(0, 20).map((c) => (
          <li key={c.nombre}>
            <span className="num">{c.nombre}</span> · {(c.tamano / 1024).toFixed(0)} KB · {fechaHora(c.fecha)}
          </li>
        ))}
      </ul>
    </section>
  );
}
