"use client";

import { useEffect, useRef, useState } from "react";
import { AGENT_LABEL, STATUS_LABEL } from "@/lib/format";
import { layoutLayers, placeNodes, type Box, type Placement } from "@/lib/layout";
import type { Task } from "@/lib/types";
import { AgentBadge, StatusTag } from "./Badges";

type Props = {
  tasks: Task[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

// What a dependency edge is doing right now, used for styling.
function edgeState(from: Task, to: Task): "idle" | "flowing" | "done" | "dead" {
  if (from.status === "failed" || from.status === "skipped") return "dead";
  if (from.status !== "completed") return "idle";
  return to.status === "running" ? "flowing" : "done";
}

// Draws one dependency edge. Neighbouring layers get a single S-curve. An edge that skips
// layers bends into a free "lane", runs straight past the layers in between, then bends into
// its target, so it never hides behind an unrelated node.
function edgePath(from: Box, to: Box, all: Box[], place: Placement): { d: string; ends: string[] } {
  const { vertical, layerGap: gap, laneGap } = place;
  // Flow coordinates: `a` runs along the direction the graph reads, `c` across it.
  const flow = (box: Box) =>
    vertical ? { a: box.y, c: box.x, size: box.w } : { a: box.x, c: box.y, size: box.h };
  const point = (a: number, c: number) => (vertical ? `${c} ${a}` : `${a} ${c}`);
  const curve = (a: number, c1: number, c2: number) =>
    `C${point(a + gap / 2, c1)} ${point(a + gap / 2, c2)} ${point(a + gap, c2)}`;

  const [source, target] = [flow(from), flow(to)];
  const a1 = source.a + (vertical ? from.h : from.w);
  const c1 = source.c + source.size / 2;
  const c2 = target.c + target.size / 2;
  const bend = target.a - gap; // where the final curve into the target starts
  const ends = [point(a1, c1), point(target.a, c2)];
  if (bend <= a1) return { d: `M${ends[0]} ${curve(a1, c1, c2)}`, ends };

  // Prefer going straight on; otherwise use the gap just after or just before the source.
  const passed = all.map(flow).filter((box) => box.a > a1 && box.a < bend);
  const lanes = [c1, source.c + source.size + laneGap / 2, source.c - laneGap / 2];
  const lane = lanes.find((c) => passed.every((box) => c < box.c || c > box.c + box.size)) ?? c1;
  return { d: `M${ends[0]} ${curve(a1, c1, lane)} L${point(bend, lane)} ${curve(bend, lane, c2)}`, ends };
}

export function TaskGraph({ tasks, selectedId, onSelect }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  const [frameWidth, setFrameWidth] = useState(0);

  // The layout needs the real pixel width, which only the browser knows.
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setFrameWidth(entry.contentRect.width));
    observer.observe(frame.current!);
    return () => observer.disconnect();
  }, []);

  const byId = new Map(tasks.map((task) => [task.id, task]));
  const placement = placeNodes(layoutLayers(tasks), frameWidth);
  const { boxes, width, height, vertical } = placement;
  const allBoxes = Object.values(boxes);

  return (
    <div className="graph-frame" ref={frame}>
      {frameWidth > 0 && (
        <div className="graph" data-vertical={vertical} style={{ width, height }}>
          {/* Edges are decorative for assistive tech: each node's label lists its dependencies. */}
          <svg width={width} height={height} aria-hidden="true">
            {tasks.flatMap((to) =>
              to.depends_on.map((fromId) => {
                const from = byId.get(fromId)!;
                const { d, ends } = edgePath(boxes[fromId], boxes[to.id], allBoxes, placement);
                return (
                  <g key={`${fromId}-${to.id}`} className="edge" data-role={from.role} data-state={edgeState(from, to)}>
                    <path d={d} />
                    {ends.map((end) => (
                      <circle key={end} cx={end.split(" ")[0]} cy={end.split(" ")[1]} r="5" />
                    ))}
                  </g>
                );
              }),
            )}
          </svg>
          {tasks.map((task) => {
            const box = boxes[task.id];
            const needs = task.depends_on.map((id) => byId.get(id)!.title).join(", ");
            return (
              <button
                key={task.id}
                type="button"
                className="node"
                data-role={task.role}
                data-status={task.status}
                aria-pressed={task.id === selectedId}
                aria-label={`${task.title}. ${AGENT_LABEL[task.role]}. ${STATUS_LABEL[task.status]}.${needs ? ` Depends on ${needs}.` : ""}`}
                style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
                onClick={() => onSelect(task.id)}
              >
                <span className="node-top">
                  <AgentBadge agent={task.role} />
                  <StatusTag status={task.status} />
                </span>
                <span className="node-title">{task.title}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
