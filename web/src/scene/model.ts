import type { StandId } from "../events/areas";
import type { AttackerStatus, DeploymentView, Highlight, TokenShape } from "../events/reduce";

export interface TokenModel {
  id: string;
  label: string;
  stand: StandId;
  status: AttackerStatus;
  shape: TokenShape;
  color: number;
  selected: boolean;
}

export interface DeploymentModel extends DeploymentView {
  selected: boolean;
  engaged: boolean;
}

export interface WorkspaceModel {
  tokens: TokenModel[];
  highlights: Highlight[];
  deployments: DeploymentModel[];
  engagement: boolean;
  compromise: boolean;
  defenderWaiting: boolean;
  defenderSelected: boolean;
  motion: "play" | "snap";
  /** Changes when a round commit moves every attacker together. */
  moveEpoch: number;
}
