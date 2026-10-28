/**
 * Entrar, elegir contraseña y certificado del servidor (diseño del modo servidor, 6.3 y 7).
 * Solo aparecen en el modo servidor.
 */
import { useState, type FormEvent, type ReactNode } from "react";

import { ErrorApi } from "../api/cliente";
import { useCambiarContrasena, useEntrar, useSalir, useServidorPublico } from "../api/sesion";
import type { Yo } from "../api/tipos";
import { MensajeError } from "../componentes/Mensajes";
import css from "./Acceso.module.css";

function Marco({ children }: { children: ReactNode }) {
  return (
    <div className={css.pagina}>
      <div className={css.marca}>
        <img src="/icono.svg" alt="" />
        <h1>Turnos médicos</h1>
      </div>
      {children}
    </div>
  );
}

export function Entrar() {
  const entrar = useEntrar();
  const publico = useServidorPublico();
  const [usuario, setUsuario] = useState("");
  const [contrasena, setContrasena] = useState("");

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    entrar.mutate({ usuario, contrasena });
  };

  return (
    <Marco>
      <form className={`panel ${css.caja}`} onSubmit={enviar}>
        <h2>Entrar</h2>
        <label className="campo">
          <span>Usuario</span>
          <input
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            required
            autoFocus
          />
        </label>
        <label className="campo">
          <span>Contraseña</span>
          <input
            type="password"
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <button type="submit" className="btn primario" disabled={entrar.isPending}>
          {entrar.isPending ? "Entrando…" : "Entrar"}
        </button>
        <MensajeError error={entrar.error} />
        <p className="nota">Si has olvidado la contraseña, pide al administrador una temporal.</p>
      </form>
      {publico.data?.hay_certificado && <InstruccionesCertificado />}
    </Marco>
  );
}

/** Instalar la autoridad del servidor para que el navegador no avise (D-S1). */
export function InstruccionesCertificado({ abierto = false, huella }: { abierto?: boolean; huella?: string | null }) {
  return (
    <details className={`panel ${css.certificado}`} open={abierto}>
      <summary>¿El navegador avisa de que la conexión no es segura?</summary>
      <p className="nota">
        El servidor usa un certificado propio de esta red. Instálalo una vez en cada dispositivo y el aviso desaparece.
      </p>
      <h3>iPhone o iPad</h3>
      <ol>
        <li>
          Abre esta página en <strong>Safari</strong> y descarga el{" "}
          <a href="/certificado/turnos.mobileconfig">perfil de Turnos médicos</a>.
        </li>
        <li>Ajustes › General › VPN y gestión de dispositivos › «Turnos médicos» › Instalar.</li>
        <li>
          Ajustes › General › Información › Ajustes de confianza de certificados › activa «Autoridad de Turnos médicos».
        </li>
      </ol>
      <h3>Android</h3>
      <ol>
        <li>
          Descarga el <a href="/certificado/turnos-autoridad.crt">certificado de la autoridad</a>.
        </li>
        <li>Ajustes › Seguridad › Más ajustes › Cifrado y credenciales › Instalar un certificado › Certificado de CA.</li>
      </ol>
      <h3>Windows, Mac o Linux</h3>
      <ol>
        <li>
          Descarga el <a href="/certificado/turnos-autoridad.crt">certificado de la autoridad</a>.
        </li>
        <li>
          Windows: ábrelo › Instalar certificado › «Entidades de certificación raíz de confianza». Mac: ábrelo en Acceso a
          Llaveros y márcalo como «Confiar siempre». Linux (Firefox o Chrome): Ajustes › Certificados › Autoridades ›
          Importar.
        </li>
      </ol>
      {huella && (
        <p className="nota">
          Huella (SHA-256) para comprobar que es el de este servidor: <span className={css.huella}>{huella}</span>
        </p>
      )}
    </details>
  );
}

/** Cambiar la contraseña: obligatorio con una temporal; si no, desde el menú del usuario. */
export function CambiarContrasena({ yo, alTerminar }: { yo: Yo; alTerminar?: () => void }) {
  const cambiar = useCambiarContrasena();
  const salir = useSalir();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const distintas = repetida !== "" && nueva !== repetida;

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (distintas) return;
    cambiar.mutate({ actual, nueva }, { onSuccess: () => alTerminar?.() });
  };

  const formulario = (
    <form className={`panel ${css.caja}`} onSubmit={enviar}>
      <h2>{yo.debe_cambiar ? `Hola, ${yo.nombre_visible}: elige tu contraseña` : "Cambiar la contraseña"}</h2>
      {yo.debe_cambiar && <p className="nota">Tienes una contraseña temporal. Elige una tuya para continuar.</p>}
      <label className="campo">
        <span>{yo.debe_cambiar ? "Contraseña temporal" : "Contraseña actual"}</span>
        <input
          type="password"
          value={actual}
          onChange={(e) => setActual(e.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      <input type="text" value={yo.nombre ?? ""} autoComplete="username" hidden readOnly />
      <label className="campo">
        <span>Contraseña nueva (8 caracteres o más)</span>
        <input
          type="password"
          value={nueva}
          minLength={8}
          onChange={(e) => setNueva(e.target.value)}
          autoComplete="new-password"
          required
        />
      </label>
      <label className="campo">
        <span>Repite la contraseña nueva</span>
        <input
          type="password"
          value={repetida}
          onChange={(e) => setRepetida(e.target.value)}
          autoComplete="new-password"
          aria-invalid={distintas}
          required
        />
      </label>
      {distintas && <p className="nota error">Las dos contraseñas nuevas no coinciden.</p>}
      <div className="acciones">
        <button type="submit" className="btn primario" disabled={cambiar.isPending || distintas}>
          Guardar contraseña
        </button>
        {yo.debe_cambiar ? (
          <button type="button" className="btn" onClick={() => salir.mutate()}>
            Salir
          </button>
        ) : (
          alTerminar && (
            <button type="button" className="btn" onClick={alTerminar}>
              Cancelar
            </button>
          )
        )}
      </div>
      <MensajeError error={cambiar.error} />
    </form>
  );
  return yo.debe_cambiar ? <Marco>{formulario}</Marco> : formulario;
}

export const sinSesion = (error: unknown) => error instanceof ErrorApi && error.estado === 401;
