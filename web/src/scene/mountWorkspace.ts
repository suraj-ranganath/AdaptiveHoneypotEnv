import { Application, Container, Graphics, Text, type FederatedPointerEvent } from "pixi.js";
import { AREA_IDS, AREA_LABEL, type AreaId, type StandId } from "../events/areas";
import { ALERT_HEX, BRASS_HEX, COMPROMISE_HEX } from "./palette";
import type { DeploymentModel, TokenModel, WorkspaceModel } from "./model";

const TILE_W = 198;
const TILE_H = 114;
const HALF_W = TILE_W / 2;
const HALF_H = TILE_H / 2;

const AREA_FILL: Record<AreaId, number> = {
  source: 0xf7f1e6,
  ci: 0xe5eef6,
  deploy: 0xf8f0e4,
  runbooks: 0xe7f1e4,
  integrations: 0xf2ebf6,
  service: 0xeeeae4,
};

const GRID: Record<AreaId, { col: number; row: number }> = {
  source: { col: 0, row: 0 },
  ci: { col: 1, row: 0 },
  deploy: { col: 2, row: 0 },
  runbooks: { col: 0, row: 1 },
  integrations: { col: 1, row: 1 },
  service: { col: 2, row: 1 },
};

const ROOM_ORDER: AreaId[] = [...AREA_IDS].sort((a, b) => {
  const depthA = GRID[a].col + GRID[a].row;
  const depthB = GRID[b].col + GRID[b].row;
  return depthA - depthB || GRID[a].col - GRID[b].col;
});

export interface AnchorPoint {
  x: number;
  y: number;
}

export interface WorkspaceHandle {
  update(model: WorkspaceModel): void;
  destroy(): void;
}

export interface MountHandlers {
  onSelect(
    selection:
      | { type: "attacker"; id: string }
      | { type: "deployment"; id: string }
      | { type: "area"; id: AreaId },
  ): void;
  onAnchors(anchors: Record<string, AnchorPoint>): void;
}

interface Motion {
  x: number;
  y: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

export async function mountWorkspace(host: HTMLElement, handlers: MountHandlers): Promise<WorkspaceHandle> {
  if (document.fonts?.load) {
    await Promise.all([
      document.fonts.load('600 13px "IBM Plex Sans"'),
      document.fonts.load('500 12px "IBM Plex Sans"'),
    ]).catch(() => undefined);
  }

  const app = new Application();
  await app.init({
    background: "#f3efe6",
    resizeTo: host,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    preference: "webgl",
  });
  app.canvas.style.width = "100%";
  app.canvas.style.height = "100%";
  app.canvas.setAttribute("role", "img");
  app.canvas.setAttribute(
    "aria-label",
    "Isometric workspace with source, CI, deploy, runbooks, integrations, and service",
  );
  host.appendChild(app.canvas);
  app.stage.eventMode = "static";

  const world = new Container();
  const tokenLayer = new Container();
  app.stage.addChild(world);
  app.stage.addChild(tokenLayer);

  const motions = new Map<string, Motion>();
  const tokenViews = new Map<string, Container>();
  let model: WorkspaceModel | null = null;
  let origin = { x: 0, y: 0 };
  let viewScale = 1;
  let viewOffset = { x: 0, y: 0 };
  let animating = false;
  let animStart = 0;
  let reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const onMotion = () => {
    reduced = motionQuery?.matches ?? false;
  };
  motionQuery?.addEventListener?.("change", onMotion);

  function layout() {
    const width = Math.max(1, host.clientWidth || 800);
    const height = Math.max(1, host.clientHeight || 520);
    // Local bounds around the source-tile center. Includes decoy cards above the
    // top tile, the defender caption, bench labels, and token names.
    const left = -TILE_W * 1.55;
    const right = TILE_W * 1.62;
    const top = -96;
    const bottom = 386;
    const contentW = right - left;
    const contentH = bottom - top;
    const padX = 12;
    const padY = 10;
    viewScale = Math.min(1, (width - padX * 2) / contentW, (height - padY * 2) / contentH);
    if (!Number.isFinite(viewScale) || viewScale <= 0) viewScale = 1;
    viewOffset = {
      x: (width - contentW * viewScale) / 2 - left * viewScale,
      y: (height - contentH * viewScale) / 2 - top * viewScale,
    };
    world.scale.set(viewScale);
    tokenLayer.scale.set(viewScale);
    world.position.set(viewOffset.x, viewOffset.y);
    tokenLayer.position.set(viewOffset.x, viewOffset.y);
    origin = { x: 0, y: 0 };
  }

  function toHost(point: { x: number; y: number }): { x: number; y: number } {
    return {
      x: point.x * viewScale + viewOffset.x,
      y: point.y * viewScale + viewOffset.y,
    };
  }

  function centerOf(stand: StandId): { x: number; y: number } {
    if (stand === "bench") return { x: origin.x + 8, y: origin.y + 328 };
    if (stand === "withheld") return { x: origin.x + 8, y: origin.y + 248 };
    if (stand === "ops") {
      const rooms: AreaId[] = ["ci", "deploy", "runbooks", "integrations"];
      const pts = rooms.map((id) => centerOf(id));
      return {
        x: pts.reduce((sum, point) => sum + point.x, 0) / pts.length,
        y: pts.reduce((sum, point) => sum + point.y, 0) / pts.length + 18,
      };
    }
    const cell = GRID[stand];
    return {
      x: origin.x + (cell.col - cell.row) * HALF_W,
      y: origin.y + (cell.col + cell.row) * HALF_H,
    };
  }

  function tokenDest(token: TokenModel, index: number): { x: number; y: number } {
    const base = centerOf(token.stand);
    if (token.stand === "bench" || token.stand === "withheld") {
      return { x: base.x + (index - 1) * 78, y: base.y };
    }
    const spread = [
      { x: -26, y: 8 },
      { x: 4, y: -10 },
      { x: 28, y: 12 },
    ];
    const offset = spread[index] ?? spread[0];
    return { x: base.x + offset.x, y: base.y + offset.y };
  }

  function diamond(shiftY = 0): number[] {
    return [0, -HALF_H + shiftY, HALF_W, shiftY, 0, HALF_H + shiftY, -HALF_W, shiftY];
  }

  function rebuildWorld() {
    world.removeChildren();
    if (!model) return;
    const floor = new Graphics();
    floor.ellipse(origin.x + 20, origin.y + 120, 340, 150).fill({ color: 0xe7e0d4, alpha: 0.45 });
    world.addChild(floor);

    const latestSeq = model.highlights.reduce((max, hit) => Math.max(max, hit.sequence), 0);

    for (const area of ROOM_ORDER) {
      const at = centerOf(area);
      const tile = new Container();
      tile.position.set(at.x, at.y);
      const hits = model.highlights.filter((hit) => hit.area === area);
      const latestHits = hits.filter((hit) => hit.sequence === latestSeq);
      const showLatest = latestHits.length > 0;
      const body = new Graphics();
      body.poly(diamond(10)).fill({ color: 0xddd4c6 });
      body.poly(diamond(0)).fill({ color: AREA_FILL[area] });
      if (hits.length > 0) {
        body.poly(diamond(0)).fill({ color: 0xe2b15a, alpha: showLatest ? 0.55 : 0.22 });
      }
      if (area === "service" && model.compromise) {
        body.poly(diamond(0)).fill({ color: COMPROMISE_HEX, alpha: 0.22 });
      } else if (area === "service" && model.engagement) {
        body.poly(diamond(0)).fill({ color: ALERT_HEX, alpha: 0.16 });
      }
      body.poly(diamond(0)).stroke({ color: 0xc9c0b2, width: 1.5 });
      body.eventMode = "static";
      body.cursor = "pointer";
      body.on("pointertap", (event: FederatedPointerEvent) => {
        event.stopPropagation();
        handlers.onSelect({ type: "area", id: area });
      });
      tile.addChild(body);
      drawGlyph(tile, area);
      const label = new Text({
        text: AREA_LABEL[area],
        style: { fill: 0x1a1814, fontSize: 14, fontWeight: "600", fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" },
      });
      label.anchor.set(0.5);
      label.position.set(0, 8);
      tile.addChild(label);
      if (showLatest) {
        const query = latestHits[0]?.query ?? "";
        const clipped = latestHits.some((hit) => hit.clipped);
        const caption = new Text({
          text: `${latestHits.length} hit${latestHits.length === 1 ? "" : "s"}${clipped ? " · clipped" : ""}`,
          style: { fill: 0x1a1814, fontSize: 11, fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" },
        });
        caption.anchor.set(0.5, 0);
        caption.position.set(0, HALF_H + 8);
        tile.addChild(caption);
        if (query) {
          const q = new Text({
            text: query.length > 28 ? `${query.slice(0, 28)}…` : query,
            style: { fill: 0x4a453d, fontSize: 11, fontFamily: "IBM Plex Mono, ui-monospace, monospace" },
          });
          q.anchor.set(0.5, 0);
          q.position.set(0, HALF_H + 24);
          tile.addChild(q);
        }
      }
      const here = model.deployments.filter((item) => item.area === area);
      here.forEach((deployment, index) => tile.addChild(deploymentCard(deployment, index, here.length)));
      if (area === "service" && (model.engagement || model.compromise)) {
        tile.addChild(serviceMarks(model));
      }
      world.addChild(tile);
    }

    const labelStyle = {
      fill: 0x6b645b,
      fontSize: 12,
      fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif",
    };
    const benchAt = centerOf("bench");
    const bench = new Text({ text: "No tool target yet", style: labelStyle });
    bench.anchor.set(0.5);
    bench.position.set(benchAt.x, benchAt.y + 22);
    world.addChild(bench);
    const withheldAt = centerOf("withheld");
    const withheld = new Text({
      text: "File tools · path not on this projection",
      style: labelStyle,
    });
    withheld.anchor.set(0.5);
    withheld.position.set(withheldAt.x, withheldAt.y + 22);
    world.addChild(withheld);

    const defender = defenderMark(model.defenderWaiting);
    const defAt = { x: origin.x - TILE_W * 0.95, y: origin.y + TILE_H * 1.7 };
    defender.position.set(defAt.x, defAt.y);
    world.addChild(defender);
  }

  function deploymentCard(deployment: DeploymentModel, index: number, count: number): Container {
    const card = new Container();
    const shift = (index - (count - 1) / 2) * 28;
    card.position.set(shift, -52);
    const g = new Graphics();
    g.roundRect(-30, -20, 60, 42, 3).fill({ color: 0xfffdf8 });
    g.roundRect(-30, -20, 60, 42, 3).stroke({
      color: deployment.engaged ? ALERT_HEX : BRASS_HEX,
      width: deployment.selected ? 3 : 2,
    });
    g.poly([-30, -20, -16, -20, -30, -6]).fill({ color: BRASS_HEX });
    g.eventMode = "static";
    g.cursor = "pointer";
    g.on("pointertap", (event: FederatedPointerEvent) => {
      event.stopPropagation();
      handlers.onSelect({ type: "deployment", id: deployment.id });
    });
    card.addChild(g);
    const caption = new Text({
      text: deployment.engaged ? "Engaged" : "Decoy",
      style: {
        fill: deployment.engaged ? ALERT_HEX : BRASS_HEX,
        fontSize: 11,
        fontWeight: "600",
        fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif",
      },
    });
    caption.anchor.set(0.5);
    caption.position.set(0, 6);
    card.addChild(caption);
    return card;
  }

  function serviceMarks(current: WorkspaceModel): Container {
    const layer = new Container();
    if (current.engagement) {
      const ring = new Graphics();
      ring.circle(0, 0, HALF_H + 8).stroke({ color: ALERT_HEX, width: 3, alpha: 0.9 });
      layer.addChild(ring);
    }
    if (current.compromise) {
      const seal = new Graphics();
      seal.moveTo(-18, -HALF_H - 16).lineTo(18, -HALF_H + 8).stroke({ color: COMPROMISE_HEX, width: 3 });
      seal.moveTo(18, -HALF_H - 16).lineTo(-18, -HALF_H + 8).stroke({ color: COMPROMISE_HEX, width: 3 });
      layer.addChild(seal);
    }
    return layer;
  }

  function defenderMark(waiting: boolean): Container {
    const node = new Container();
    const g = new Graphics();
    g.circle(0, 0, 16).fill({ color: BRASS_HEX });
    g.circle(0, 0, 16).stroke({ color: 0x1a1814, width: 1.5 });
    if (waiting) g.circle(0, 0, 22).stroke({ color: BRASS_HEX, width: 2, alpha: 0.8 });
    node.addChild(g);
    const letter = new Text({
      text: "D",
      style: { fill: 0xfffdf8, fontSize: 14, fontWeight: "600", fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" },
    });
    letter.anchor.set(0.5);
    node.addChild(letter);
    const caption = new Text({
      text: waiting ? "Defender · waiting on model" : "Defender",
      style: { fill: 0x1a1814, fontSize: 12, fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif" },
    });
    caption.anchor.set(0.5, 0);
    caption.position.set(0, 22);
    node.addChild(caption);
    return node;
  }

  function drawGlyph(tile: Container, area: AreaId) {
    const g = new Graphics();
    g.position.set(0, -18);
    const ink = 0x3f3a33;
    if (area === "source") {
      g.roundRect(-16, -8, 18, 22, 2).stroke({ color: ink, width: 1.4 });
      g.roundRect(-8, -12, 18, 22, 2).fill({ color: 0xfffdf8 }).stroke({ color: ink, width: 1.4 });
    } else if (area === "ci") {
      g.circle(-14, 0, 4).stroke({ color: ink, width: 1.4 });
      g.circle(0, 0, 4).stroke({ color: ink, width: 1.4 });
      g.circle(14, 0, 4).stroke({ color: ink, width: 1.4 });
      g.moveTo(-10, 0).lineTo(-4, 0).moveTo(4, 0).lineTo(10, 0).stroke({ color: ink, width: 1.4 });
    } else if (area === "deploy") {
      g.poly([0, -12, 14, -4, 0, 4, -14, -4]).stroke({ color: ink, width: 1.4 });
      g.moveTo(-14, -4).lineTo(-14, 8).lineTo(0, 16).lineTo(14, 8).lineTo(14, -4).stroke({ color: ink, width: 1.4 });
    } else if (area === "runbooks") {
      g.moveTo(0, -10).lineTo(-16, -6).lineTo(-16, 10).lineTo(0, 6).lineTo(16, 10).lineTo(16, -6).lineTo(0, -10).stroke({ color: ink, width: 1.4 });
      g.moveTo(0, -10).lineTo(0, 6).stroke({ color: ink, width: 1.4 });
    } else if (area === "integrations") {
      g.circle(0, -8, 3.5).circle(-10, 6, 3.5).circle(10, 6, 3.5).stroke({ color: ink, width: 1.4 });
      g.moveTo(0, -4).lineTo(-8, 4).moveTo(0, -4).lineTo(8, 4).stroke({ color: ink, width: 1.4 });
    } else {
      g.circle(0, 0, 12).stroke({ color: ink, width: 1.5 });
      g.circle(0, 0, 4).fill({ color: ink });
      g.roundRect(-8, 8, 16, 6, 2).stroke({ color: ink, width: 1.4 });
    }
    tile.addChild(g);
  }

  function syncTokens() {
    if (!model) return;
    const live = new Set(model.tokens.map((token) => token.id));
    for (const [id, view] of tokenViews) {
      if (!live.has(id)) {
        tokenLayer.removeChild(view);
        view.destroy({ children: true });
        tokenViews.delete(id);
        motions.delete(id);
      }
    }
    model.tokens.forEach((token, index) => {
      let view = tokenViews.get(token.id);
      if (!view) {
        view = drawToken(token);
        tokenViews.set(token.id, view);
        tokenLayer.addChild(view);
      } else {
        paintToken(view, token);
      }
      const dest = tokenDest(token, index);
      let motion = motions.get(token.id);
      if (!motion) {
        motion = { x: dest.x, y: dest.y, fromX: dest.x, fromY: dest.y, toX: dest.x, toY: dest.y };
        motions.set(token.id, motion);
      } else if (motion.toX !== dest.x || motion.toY !== dest.y) {
        motion.fromX = motion.x;
        motion.fromY = motion.y;
        motion.toX = dest.x;
        motion.toY = dest.y;
        const snap = !model || model.motion === "snap" || reduced;
        if (snap) {
          motion.x = dest.x;
          motion.y = dest.y;
          motion.fromX = dest.x;
          motion.fromY = dest.y;
        } else {
          animating = true;
          animStart = performance.now();
        }
      }
      view.position.set(motion.x, motion.y);
    });
  }

  function drawToken(token: TokenModel): Container {
    const node = new Container();
    node.eventMode = "static";
    node.cursor = "pointer";
    node.on("pointertap", (event: FederatedPointerEvent) => {
      event.stopPropagation();
      handlers.onSelect({ type: "attacker", id: token.id });
    });
    paintToken(node, token);
    return node;
  }

  function paintToken(node: Container, token: TokenModel) {
    node.removeChildren();
    const g = new Graphics();
    g.ellipse(0, 22, 16, 5).fill({ color: 0x1a1814, alpha: 0.08 });
    g.roundRect(-10, -4, 20, 22, 7).fill({ color: token.color });
    g.circle(0, -16, 8).fill({ color: token.color });
    if (token.shape === "circle") g.circle(0, 6, 4).stroke({ color: 0xfffdf8, width: 1.6 });
    else if (token.shape === "square") g.rect(-4, 2, 8, 8).stroke({ color: 0xfffdf8, width: 1.6 });
    else g.poly([0, 1, 5, 7, 0, 13, -5, 7]).stroke({ color: 0xfffdf8, width: 1.6 });
    if (token.status === "waiting_model") g.circle(0, 2, 24).stroke({ color: token.color, width: 1.5, alpha: 0.85 });
    if (token.selected) g.circle(0, 2, 28).stroke({ color: 0x1a1814, width: 1.5 });
    if (token.status === "refused" || token.status === "finished") g.circle(0, 2, 28).stroke({ color: 0x6b645b, width: 1, alpha: 0.7 });
    node.addChild(g);
    const name = new Text({
      text: token.label,
      style: {
        fill: token.status === "refused" || token.status === "finished" ? 0x6b645b : 0x1a1814,
        fontSize: 12,
        fontWeight: "600",
        fontFamily: "IBM Plex Sans, Helvetica Neue, Arial, sans-serif",
      },
    });
    name.anchor.set(0.5, 0);
    name.position.set(0, 30);
    node.addChild(name);
  }

  function publishAnchors() {
    const canvasRect = app.canvas.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    const dx = canvasRect.left - hostRect.left;
    const dy = canvasRect.top - hostRect.top;
    const anchors: Record<string, AnchorPoint> = {};
    for (const area of AREA_IDS) {
      const at = toHost(centerOf(area));
      anchors[`area:${area}`] = { x: at.x + dx, y: at.y + dy };
    }
    const bench = toHost(centerOf("bench"));
    anchors.bench = { x: bench.x + dx, y: bench.y + dy };
    for (const [id, motion] of motions) {
      const at = toHost(motion);
      anchors[`attacker:${id}`] = { x: at.x + dx, y: at.y + dy };
    }
    if (model) {
      for (const deployment of model.deployments) {
        if (!deployment.area) continue;
        const local = centerOf(deployment.area);
        const at = toHost({ x: local.x, y: local.y - 52 });
        anchors[`deployment:${deployment.id}`] = { x: at.x + dx, y: at.y + dy };
      }
    }
    handlers.onAnchors(anchors);
  }

  const tick = () => {
    if (animating) {
      const u = Math.min(1, (performance.now() - animStart) / 720);
      const eased = u < 0.5 ? 2 * u * u : 1 - ((-2 * u + 2) ** 2) / 2;
      for (const [id, motion] of motions) {
        motion.x = motion.fromX + (motion.toX - motion.fromX) * eased;
        motion.y = motion.fromY + (motion.toY - motion.fromY) * eased;
        tokenViews.get(id)?.position.set(motion.x, motion.y);
      }
      if (u >= 1) animating = false;
      publishAnchors();
    }
  };
  app.ticker.add(tick);

  let lastW = -1;
  let lastH = -1;
  const onResize = () => {
    const width = host.clientWidth;
    const height = host.clientHeight;
    if (width === lastW && height === lastH) return;
    lastW = width;
    lastH = height;
    layout();
    for (const motion of motions.values()) {
      motion.fromX = motion.x;
      motion.fromY = motion.y;
    }
    rebuildWorld();
    if (model) {
      model.tokens.forEach((token, index) => {
        const dest = tokenDest(token, index);
        const motion = motions.get(token.id);
        if (!motion) return;
        motion.x = dest.x;
        motion.y = dest.y;
        motion.fromX = dest.x;
        motion.fromY = dest.y;
        motion.toX = dest.x;
        motion.toY = dest.y;
        tokenViews.get(token.id)?.position.set(dest.x, dest.y);
      });
    }
    animating = false;
    publishAnchors();
  };
  window.addEventListener("resize", onResize);
  const resizeObserver = new ResizeObserver(() => onResize());
  resizeObserver.observe(host);
  layout();

  return {
    update(next) {
      model = next;
      layout();
      rebuildWorld();
      syncTokens();
      publishAnchors();
    },
    destroy() {
      resizeObserver.disconnect();
      window.removeEventListener("resize", onResize);
      motionQuery?.removeEventListener?.("change", onMotion);
      app.ticker.remove(tick);
      app.destroy({ removeView: true }, { children: true });
    },
  };
}
