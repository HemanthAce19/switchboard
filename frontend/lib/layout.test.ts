import { describe, expect, it } from "vitest";
import { layoutLayers, placeNodes } from "./layout";

const node = (id: string, ...depends_on: string[]) => ({ id, depends_on });

describe("layoutLayers", () => {
  it("puts independent tasks in the first layer", () => {
    expect(layoutLayers([node("a"), node("b")])).toEqual([["a", "b"]]);
  });

  it("lays a chain out one task per layer", () => {
    expect(layoutLayers([node("a"), node("b", "a"), node("c", "b")])).toEqual([["a"], ["b"], ["c"]]);
  });

  it("uses the longest path, not the shortest", () => {
    // d depends on a root directly and on c, which is two steps deep.
    const layers = layoutLayers([node("a"), node("b", "a"), node("c", "b"), node("d", "a", "c")]);
    expect(layers).toEqual([["a"], ["b"], ["c"], ["d"]]);
  });

  it("handles parallel branches that join", () => {
    const layers = layoutLayers([
      node("t1"),
      node("t2"),
      node("t3", "t1", "t2"),
      node("t4"),
      node("t5", "t3", "t4"),
    ]);
    expect(layers).toEqual([["t1", "t2", "t4"], ["t3"], ["t5"]]);
  });

  it("does not depend on the order tasks are listed in", () => {
    expect(layoutLayers([node("c", "b"), node("b", "a"), node("a")])).toEqual([["a"], ["b"], ["c"]]);
  });
});

describe("placeNodes", () => {
  const layers = [["a", "b"], ["c"]];

  it("reads left to right on wide containers and centres short layers", () => {
    const { boxes, vertical, width } = placeNodes(layers, 1000);
    expect(vertical).toBe(false);
    expect(boxes.c.x).toBeGreaterThan(boxes.a.x + boxes.a.w);
    expect(boxes.a.x).toBe(boxes.b.x);
    // c sits halfway between a and b
    expect(boxes.c.y).toBe((boxes.a.y + boxes.b.y) / 2);
    expect(width).toBeLessThanOrEqual(1000);
  });

  it("flips to top to bottom on narrow containers", () => {
    const { boxes, vertical, width } = placeNodes(layers, 380);
    expect(vertical).toBe(true);
    expect(boxes.c.y).toBeGreaterThan(boxes.a.y + boxes.a.h);
    expect(boxes.a.y).toBe(boxes.b.y);
    expect(width).toBeLessThanOrEqual(380);
  });
});
