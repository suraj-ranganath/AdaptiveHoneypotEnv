"""Private fixture generation and workspace materialization.

``build_fixture_bundle`` reads the public-layout stream and the private
fixture stream only. Policy and decoy streams are not arguments.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from adaptivehoneypotenv.scenarios.secret_store_ops_v1.rng import (
    RngStreams,
    derive_signing_key,
    protected_secret,
    random_stored_value,
    resolve_flag_identity,
    sample_account,
    select_workflow,
)
from adaptivehoneypotenv.scenarios.secret_store_ops_v1.spec import (
    ACCOUNT_ROLES,
    CREDENTIAL_ARTIFACTS,
    PACKAGE_DIR,
    RETIRED_LIST_ROLES,
    REVIEW_SENTENCES,
    SCENARIO_ID,
    VENDOR_SOURCE_DIR,
    WORKFLOW_OF_ROLE,
    WORKSPACE_TEMPLATE,
)

_PLACEHOLDER_KEYS = tuple(
    f"{role}.{field}" for role in ACCOUNT_ROLES for field in ("username", "email", "password")
)


@dataclass(frozen=True)
class Account:
    role: str
    workflow: str | None
    username: str
    email: str
    password: str
    stored_value: str


@dataclass(frozen=True)
class FixtureBundle:
    scenario_id: str
    public_layout_seed: int
    private_fixture_seed: int
    identity_kind: str
    identity: str
    episode_id: str
    comparison_id: str | None
    workflow: str
    signing_key: bytes
    accounts: dict[str, Account]
    retired_order: tuple[str, ...]
    review_sentence: str
    layout_fingerprint: str

    def account_for_workflow(self, workflow: str) -> Account:
        role = {value: key for key, value in WORKFLOW_OF_ROLE.items()}[workflow]
        return self.accounts[role]

    def stored_value_for_workflow(self, workflow: str) -> str:
        return self.account_for_workflow(workflow).stored_value


def build_fixture_bundle(
    streams: RngStreams,
    *,
    comparison_id: str | None,
    episode_id: str,
    workflow: str | None = None,
) -> FixtureBundle:
    """Materialize one genuine world.

    Protected workflow values are HMAC-SHA256 of a versioned identity message
    under a key derived only from ``private_fixture_seed``. Noise stored values
    use the private fixture stream and the same formatter. The public layout
    stream only orders the migration list and picks a review sentence.
    """

    if streams.public_layout_seed is None or streams.private_fixture_seed is None:
        raise ValueError("both layout and private seeds are required")
    signing_key = derive_signing_key(streams.private_fixture_seed)
    identity_kind, identity = resolve_flag_identity(
        comparison_id=comparison_id,
        episode_id=episode_id,
    )
    accounts: dict[str, Account] = {}
    used: set[str] = set()
    used_passwords: set[str] = set()
    private = streams.private_fixture
    for role in ACCOUNT_ROLES:
        while True:
            username, email, password = sample_account(private, used)
            if password not in used_passwords:
                used_passwords.add(password)
                break
        role_workflow = WORKFLOW_OF_ROLE.get(role)
        if role_workflow is None:
            stored_value = random_stored_value(private)
        else:
            stored_value = protected_secret(
                signing_key,
                identity_kind=identity_kind,
                identity=identity,
                workflow=role_workflow,
            )
        accounts[role] = Account(
            role=role,
            workflow=role_workflow,
            username=username,
            email=email,
            password=password,
            stored_value=stored_value,
        )
    order = list(RETIRED_LIST_ROLES)
    streams.public_layout.shuffle(order)
    sentence = streams.public_layout.choice(REVIEW_SENTENCES)
    retired_lines = "\n".join(
        f"- {accounts[role].username} — {CREDENTIAL_ARTIFACTS[role]}" for role in order
    )
    fingerprint = hashlib.sha256(f"{sentence}\n{retired_lines}".encode("utf-8")).hexdigest()
    chosen = workflow if workflow is not None else select_workflow(streams.private_fixture_seed)
    if chosen not in WORKFLOW_OF_ROLE.values():
        raise ValueError("workflow must be release or backup")
    return FixtureBundle(
        scenario_id=SCENARIO_ID,
        public_layout_seed=streams.public_layout_seed,
        private_fixture_seed=streams.private_fixture_seed,
        identity_kind=identity_kind,
        identity=identity,
        episode_id=episode_id,
        comparison_id=comparison_id,
        workflow=chosen,
        signing_key=signing_key,
        accounts=accounts,
        retired_order=tuple(order),
        review_sentence=sentence,
        layout_fingerprint=fingerprint,
    )


def materialize_workspace(
    bundle: FixtureBundle,
    dest: Path,
    *,
    repo_root: Path | None = None,
    copy_source: bool = True,
) -> Path:
    """Write the actor-readable workspace. Private keys and stored values stay out."""

    if dest.exists():
        raise FileExistsError(dest)
    mapping = _substitution_map(bundle)
    for source in sorted(path for path in WORKSPACE_TEMPLATE.rglob("*") if path.is_file()):
        if source.is_symlink():
            raise RuntimeError(f"refusing template symlink {source}")
        relative = source.relative_to(WORKSPACE_TEMPLATE).as_posix()
        text = substitute(source.read_text(encoding="utf-8"), mapping)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    if copy_source:
        root = repo_root if repo_root is not None else PACKAGE_DIR.parents[2]
        mount_pinned_source(dest, root)
    return dest


def substitute(text: str, mapping: dict[str, str]) -> str:
    rendered = text
    for key in _PLACEHOLDER_KEYS:
        rendered = rendered.replace(f"[[{key}]]", mapping[key])
    rendered = rendered.replace("[[layout.retired_list]]", mapping["layout.retired_list"])
    rendered = rendered.replace("[[layout.review_sentence]]", mapping["layout.review_sentence"])
    if "[[" in rendered or "]]" in rendered:
        raise RuntimeError("unresolved workspace placeholder")
    return rendered


def _substitution_map(bundle: FixtureBundle) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for role, account in bundle.accounts.items():
        mapping[f"{role}.username"] = account.username
        mapping[f"{role}.email"] = account.email
        mapping[f"{role}.password"] = account.password
    lines = [
        f"- {bundle.accounts[role].username} — {CREDENTIAL_ARTIFACTS[role]}"
        for role in bundle.retired_order
    ]
    mapping["layout.retired_list"] = "\n".join(lines)
    mapping["layout.review_sentence"] = bundle.review_sentence
    return mapping


def authored_relative_paths() -> frozenset[str]:
    return frozenset(
        path.relative_to(WORKSPACE_TEMPLATE).as_posix()
        for path in WORKSPACE_TEMPLATE.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def mount_pinned_source(workspace: Path, repo_root: Path) -> bool:
    """Copy WS1's vendored SecretStorage tree into ``source/`` when it exists.

    This package does not vendor the app. Returns False when the pin is absent
    so gate A tests can run before WS1 merges.
    """

    source_root = repo_root / VENDOR_SOURCE_DIR
    app = source_root / "app.py"
    if not app.is_file():
        return False
    destination_root = workspace / "source"
    destination_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise RuntimeError(f"refusing vendored symlink {path}")
        relative = path.relative_to(source_root)
        if relative.as_posix() == "README.md":
            relative = Path("upstream-readme.md")
        target = destination_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    return True
