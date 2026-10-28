import { describe, expect, it } from "vitest";

import { ordenEstable } from "./orden";

describe("orden estable", () => {
  it("la primera vez, el del servidor", () => {
    expect(ordenEstable(null, [3, 1, 2])).toEqual([3, 1, 2]);
  });

  it("un médico nuevo va al final aunque el servidor lo ordene antes", () => {
    expect(ordenEstable([1, 2, 3], [4, 1, 2, 3])).toEqual([1, 2, 3, 4]);
  });

  it("cambiar un nombre no lo mueve", () => {
    expect(ordenEstable([1, 2, 3, 4], [1, 4, 2, 3])).toEqual([1, 2, 3, 4]);
  });

  it("uno que se borra desaparece sin mover a los demás", () => {
    expect(ordenEstable([1, 2, 3], [3, 1])).toEqual([1, 3]);
  });
});
