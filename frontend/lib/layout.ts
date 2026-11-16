import type { Task } from "./types";

type Node = Pick<Task, "id" | "depends_on">;
export type Box = { x: number; y: number; w: number; h: number };
export type Placement = {
  boxes: Record<string, Box>;
  width: number;
  height: number;
  vertical: boolean;
  layerGap: number; // space between one layer and the next, where edges bend
  laneGap: number; // space between neighbours inside a layer
};

// Layered layout: a node's layer is the length of the longest dependency path that reaches it,
// so roots sit in layer 0 and every edge points to a later layer. The plan is validated as
// acyclic by the back end, which is what lets the recursion terminate.
export function layoutLayers(nodes: Node[]): string[][] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depth = new Map<string, number>();

  function depthOf(id: string): number {
    const known = depth.get(id);
    if (known !== undefined) return known;
    const deps = byId.get(id)?.depends_on ?? [];
    const value = deps.length ? 1 + Math.max(...deps.map(depthOf)) : 0;
    depth.set(id, value);
    return value;
  }

  const layers: string[][] = [];
  for (const node of nodes) (layers[depthOf(node.id)] ??= []).push(node.id);
  return layers;
}

// Turns layers into pixel boxes that fit `width`. Wide containers read left to right;
// narrow ones (phones) flip to top to bottom so nodes stay wide enough to read.
export function placeNodes(layers: string[][], width: number): Placement {
  const vertical = width < 600;
  const widest = Math.max(...layers.map((layer) => layer.length));
  const columns = vertical ? widest : layers.length;
  const gapX = vertical ? 10 : 64;
  const gapY = vertical ? 44 : 20;
  const h = vertical ? 132 : 108;
  const fit = (width - gapX * (columns - 1)) / columns;
  const w = Math.max(vertical ? 104 : 160, Math.min(240, fit));

  const boxes: Record<string, Box> = {};
  layers.forEach((layer, along) => {
    layer.forEach((id, index) => {
      // Centre shorter layers against the widest one.
      const across = index + (widest - layer.length) / 2;
      const [column, row] = vertical ? [across, along] : [along, across];
      boxes[id] = { x: column * (w + gapX), y: row * (h + gapY), w, h };
    });
  });

  const rows = vertical ? layers.length : widest;
  return {
    boxes,
    vertical,
    layerGap: vertical ? gapY : gapX,
    laneGap: vertical ? gapX : gapY,
    width: columns * w + (columns - 1) * gapX,
    height: rows * h + (rows - 1) * gapY,
  };
}
