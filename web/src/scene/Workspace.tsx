import { useEffect, useRef, type RefObject } from "react";
import type { Selection } from "../state/selection";
import { mountWorkspace, type AnchorPoint, type WorkspaceHandle } from "./mountWorkspace";
import type { WorkspaceModel } from "./model";

interface Props {
  stageRef: RefObject<HTMLDivElement | null>;
  model: WorkspaceModel;
  onSelect(selection: Extract<Selection, { type: "attacker" | "deployment" | "area" }>): void;
  onAnchors(anchors: Record<string, AnchorPoint>): void;
}

export function Workspace({ stageRef, model, onSelect, onAnchors }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<WorkspaceHandle | null>(null);
  const modelRef = useRef(model);
  const selectRef = useRef(onSelect);
  const anchorRef = useRef(onAnchors);
  modelRef.current = model;
  selectRef.current = onSelect;
  anchorRef.current = onAnchors;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let dead = false;
    let handle: WorkspaceHandle | null = null;
    mountWorkspace(host, {
      onSelect: (selection) => selectRef.current(selection),
      onAnchors: (local) => {
        const stage = stageRef.current;
        const hostBox = host.getBoundingClientRect();
        const stageBox = stage?.getBoundingClientRect();
        if (!stageBox) {
          anchorRef.current(local);
          return;
        }
        const mapped: Record<string, AnchorPoint> = {};
        for (const [key, point] of Object.entries(local)) {
          mapped[key] = { x: point.x + hostBox.left - stageBox.left, y: point.y + hostBox.top - stageBox.top };
        }
        anchorRef.current(mapped);
      },
    })
      .then((next) => {
        if (dead) {
          next.destroy();
          return;
        }
        handle = next;
        handleRef.current = next;
        next.update(modelRef.current);
      })
      .catch(() => {
        host.dataset.renderer = "failed";
      });
    return () => {
      dead = true;
      handle?.destroy();
      handleRef.current = null;
    };
  }, [stageRef]);

  useEffect(() => {
    handleRef.current?.update(model);
  }, [model]);

  return <div ref={hostRef} className="workspace-canvas" data-testid="workspace" />;
}
