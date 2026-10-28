import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ErrorApi } from "./api/cliente";
import { CLAVE_YO } from "./api/sesion";
import type { Yo } from "./api/tipos";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import "./estilos/global.css";

// Modo servidor: si la sesión caduca o la cierra el administrador, cualquier petición
// recibe 401; se vuelve a preguntar quién es y App.tsx muestra la página de entrada.
// Solo si había sesión: el 401 de una contraseña mala lo muestra la propia página de entrada.
const alFallar = (error: Error, clave?: readonly unknown[]) => {
  const conSesion = cliente.getQueryData<Yo>(CLAVE_YO)?.modo === "servidor";
  if (error instanceof ErrorApi && error.estado === 401 && conSesion && clave?.[0] !== CLAVE_YO[0])
    void cliente.invalidateQueries({ queryKey: CLAVE_YO });
};

const cliente = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, consulta) => alFallar(error, consulta.queryKey),
  }),
  mutationCache: new MutationCache({ onError: (error) => alFallar(error) }),
  defaultOptions: {
    queries: {
      retry: (intentos, error) => !(error instanceof ErrorApi && [401, 403].includes(error.estado)) && intentos < 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
