import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { CuadriculaElegibilidad, cuadriculaUniforme, type Cuadricula } from "./CuadriculaElegibilidad";

function Envoltorio({ alCambiar }: { alCambiar?: (c: Cuadricula) => void }) {
  const [valor, setValor] = useState(cuadriculaUniforme(() => "DISPONIBLE"));
  return (
    <CuadriculaElegibilidad
      valor={valor}
      onChange={(c) => {
        setValor(c);
        alCambiar?.(c);
      }}
    />
  );
}

const celda = (nombre: RegExp) => screen.getByRole("button", { name: nombre });

test("pulsar una celda pasa al siguiente valor", () => {
  render(<Envoltorio />);
  const lunes = celda(/Lunes, mañana/);
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Disponible");
  fireEvent.pointerDown(lunes, { button: 0 });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Habitual");
  fireEvent.pointerDown(lunes, { button: 0 });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Fijo");
  fireEvent.pointerDown(lunes, { button: 0 });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: No disponible");
  fireEvent.pointerDown(lunes, { button: 0 });
  expect(lunes).toHaveAccessibleName("Lunes, mañana: Disponible");
});

test("arrastrar pinta con el mismo valor", () => {
  render(<Envoltorio />);
  fireEvent.pointerDown(celda(/Lunes, mañana/), { button: 0 });
  fireEvent.pointerEnter(celda(/Martes, mañana/));
  fireEvent.pointerEnter(celda(/Miércoles, mañana/));
  fireEvent.pointerUp(window);
  fireEvent.pointerEnter(celda(/Jueves, mañana/)); // ya soltado: no pinta
  expect(celda(/Martes, mañana/)).toHaveAccessibleName("Martes, mañana: Habitual");
  expect(celda(/Miércoles, mañana/)).toHaveAccessibleName("Miércoles, mañana: Habitual");
  expect(celda(/Jueves, mañana/)).toHaveAccessibleName("Jueves, mañana: Disponible");
});

test("se puede usar con el teclado", async () => {
  render(<Envoltorio />);
  celda(/Viernes, tarde/).focus();
  await userEvent.keyboard("{Enter}");
  expect(celda(/Viernes, tarde/)).toHaveAccessibleName("Viernes, tarde: Habitual");
});

test("atajos", async () => {
  render(<Envoltorio />);
  await userEvent.click(screen.getByRole("button", { name: "Solo mañanas" }));
  expect(celda(/Lunes, tarde/)).toHaveAccessibleName("Lunes, tarde: No disponible");
  expect(celda(/Lunes, mañana/)).toHaveAccessibleName("Lunes, mañana: Disponible");
  await userEvent.click(screen.getByRole("button", { name: "Cualquiera" }));
  expect(celda(/Lunes, tarde/)).toHaveAccessibleName("Lunes, tarde: Disponible");
});
