import { isTerminal, pollInterval } from "./polling";

describe("pollInterval", () => {
  it("starts at one second and backs off to a five second cap", () => {
    expect([0, 1, 2, 3, 4, 20].map(pollInterval)).toEqual([1000, 1500, 2250, 3375, 5000, 5000]);
  });
});

describe("isTerminal", () => {
  it("treats only SUCCESS and FAILED as terminal", () => {
    expect(isTerminal("SUCCESS")).toBe(true);
    expect(isTerminal("FAILED")).toBe(true);
    expect(isTerminal("QUEUED")).toBe(false);
    expect(isTerminal("RUNNING")).toBe(false);
  });
});
