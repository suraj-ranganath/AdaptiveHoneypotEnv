import type { Arc } from "../events/reduce";
import { attackerColor } from "../scene/palette";

interface Point {
  x: number;
  y: number;
}

export function Arcs({
  arcs,
  anchors,
  attackerIndex,
}: {
  arcs: Arc[];
  anchors: Record<string, Point>;
  attackerIndex: Record<string, number>;
}) {
  const latest = arcs.reduce((max, arc) => Math.max(max, arc.sequence), 0);
  return (
    <svg className="arcs" aria-hidden="true">
      <defs>
        <marker id="arc-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L7,3 L0,6 Z" fill="#1a1814" />
        </marker>
      </defs>
      {arcs.map((arc) => {
        const fromKey = arc.kind === "post" ? `attacker:${arc.actorId}` : arc.postId ? `post:${arc.postId}` : "board";
        const toKey = arc.kind === "post" ? (arc.postId ? `post:${arc.postId}` : "board") : `attacker:${arc.actorId}`;
        const from = anchors[fromKey] ?? (arc.kind === "read" ? anchors.board : undefined);
        const to = anchors[toKey] ?? (arc.kind === "post" ? anchors.board : undefined);
        if (!from || !to) return null;
        const midX = (from.x + to.x) / 2;
        const midY = Math.min(from.y, to.y) - 28;
        const color = attackerColor(attackerIndex[arc.actorId] ?? 0);
        const fresh = arc.sequence === latest;
        return (
          <path
            key={arc.id}
            d={`M ${from.x} ${from.y} Q ${midX} ${midY} ${to.x} ${to.y}`}
            fill="none"
            stroke={arc.kind === "post" ? color : "#1a1814"}
            strokeWidth={fresh ? 2.25 : 1.4}
            strokeDasharray={arc.kind === "read" ? "5 4" : undefined}
            opacity={fresh ? 0.95 : 0.4}
            markerEnd="url(#arc-arrow)"
          >
            <title>{arc.kind === "post" ? "post" : "read"} · seq {arc.sequence}</title>
          </path>
        );
      })}
    </svg>
  );
}
