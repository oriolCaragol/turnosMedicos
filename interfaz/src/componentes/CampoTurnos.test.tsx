import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CampoTurnos } from "./CampoTurnos";

test("convierte turnos a medios turnos", async () => {
  const cambios: (number | null)[] = [];
  render(<CampoTurnos etiqueta="Mínimo" medios={null} onChange={(m) => cambios.push(m)} />);
  await userEvent.type(screen.getByLabelText("Mínimo"), "12,5");
  expect(cambios.at(-1)).toBe(25);
});

test("muestra el valor inicial en turnos", () => {
  render(<CampoTurnos etiqueta="Máximo" medios={37} onChange={() => {}} />);
  expect(screen.getByLabelText("Máximo")).toHaveValue("18,5");
});

test("rechaza valores que no son múltiplos de medio turno", async () => {
  render(<CampoTurnos etiqueta="Mínimo" medios={null} onChange={() => {}} />);
  await userEvent.type(screen.getByLabelText("Mínimo"), "3,2");
  expect(screen.getByText("Usa múltiplos de 0,5")).toBeInTheDocument();
});

test("opcional: vacío significa sin límite", async () => {
  const cambios: (number | null)[] = [];
  render(<CampoTurnos etiqueta="Máximo" opcional medios={8} onChange={(m) => cambios.push(m)} />);
  await userEvent.clear(screen.getByLabelText("Máximo"));
  expect(cambios.at(-1)).toBeNull();
});
