import type { Scene } from "./reduce";

export function detectionLabel(scene: Scene): { value: string; detail: string } {
  if (scene.tie) {
    return {
      value: "No",
      detail: "Same-round tie, lead time 0. This does not count as detection before compromise.",
    };
  }
  if (scene.detectionBeforeCompromise && scene.compromise) {
    return {
      value: "Yes",
      detail: "Verified engagement was in an earlier round than the protected value.",
    };
  }
  if (scene.detectionBeforeCompromise) {
    return {
      value: "Yes",
      detail: "Verified engagement occurred. Compromise has not been observed.",
    };
  }
  if (scene.compromise && scene.engagements.length === 0) {
    return { value: "No", detail: "The protected value was delivered with no verified engagement." };
  }
  if (scene.engagements.length === 0) {
    return {
      value: "Not observed",
      detail: scene.finished ? "No verified engagement in this episode." : "No verified engagement yet.",
    };
  }
  return { value: "No", detail: "Verified engagement did not precede compromise." };
}

export function compromiseLabel(scene: Scene): { value: string; detail: string } {
  if (scene.compromise) {
    return {
      value: "Observed",
      detail: `Protected value delivered (seq ${scene.compromise.sequence}). Separate from verified engagement.`,
    };
  }
  return {
    value: "Not observed",
    detail: scene.finished ? "The episode ended without protected-value delivery." : "No protected value has been delivered.",
  };
}

export function leadLabel(scene: Scene): string {
  if (scene.tie) return "0 rounds · same-round tie";
  if (scene.leadRounds !== null && scene.compromise && scene.engagements.length > 0) {
    const attempts =
      scene.leadAttempts === null ? "" : ` · ${scene.leadAttempts} attempt${scene.leadAttempts === 1 ? "" : "s"}`;
    return `${scene.leadRounds} round${scene.leadRounds === 1 ? "" : "s"}${attempts}`;
  }
  if (scene.engagements.length > 0 && !scene.compromise) return "Censored — compromise not observed";
  return "—";
}

export function outcomeSentence(scene: Scene): string {
  if (!scene.episodeId && scene.events.length === 0) return "No episode events yet.";
  if (scene.tie) {
    return "Verified engagement and genuine compromise landed in the same round. Lead time is 0, so this is not detection before compromise.";
  }
  if (scene.detectionBeforeCompromise && scene.compromise) {
    return "Verified engagement came first. The protected value was still delivered later. A catch is not containment.";
  }
  if (scene.detectionBeforeCompromise) {
    return "Verified engagement occurred. Genuine compromise has not been observed. A catch does not stop the other sessions.";
  }
  if (scene.compromise) {
    return "The protected value was delivered. Verified engagement did not precede it.";
  }
  if (scene.finished) {
    return "The episode ended. Verified engagement was not observed, and genuine compromise was not observed.";
  }
  return "No verified engagement or genuine compromise in the events shown so far.";
}

export function costLabel(scene: Scene): { decoys: string; inference: string } {
  const noun = scene.decoysCommitted === 1 ? "decoy" : "decoys";
  const priced = `$${(scene.decoyCostCents / 100).toFixed(2)}`;
  const decoys =
    scene.rewardTransitions === 0 && scene.deploymentCommits > 0
      ? "Commit seen. Decoy cost arrives on transition_completed."
      : `${scene.decoysCommitted} ${noun} committed · surrogate ${priced}`;
  return {
    decoys,
    inference: "Inference price is outside this projection.",
  };
}

export function surrogateDisagreement(scene: Scene): string | null {
  if (scene.surrogateDetection && !scene.detectionBeforeCompromise) {
    return "A transition records detection_bonus 1. The counter follows verified_engagement and protected_value_exposed.";
  }
  if (scene.surrogateCompromise && !scene.compromise) {
    return "A transition records compromise_penalty 1. The counter follows protected_value_exposed.";
  }
  return null;
}
