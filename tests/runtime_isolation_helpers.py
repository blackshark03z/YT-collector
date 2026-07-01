import hashlib
from pathlib import Path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_runtime_state(root: Path) -> dict:
    state = {
        "channels_exists": (root / "channels").exists(),
        "secrets_exists": (root / "secrets").exists(),
        "canonical_channel_json_hash": None,
        "canonical_channel_profile_hash": None,
        "canonical_channel_learnings_hash": None,
        "canonical_token_hash": None,
        "legacy_identity_hash": None,
        "legacy_learnings_hash": None,
        "legacy_token_hash": None,
    }

    channel_json = root / "channels" / "mist_of_ages" / "channel.json"
    if channel_json.exists():
        state["canonical_channel_json_hash"] = file_hash(channel_json)

    channel_profile = root / "channels" / "mist_of_ages" / "channel_profile.md"
    if channel_profile.exists():
        state["canonical_channel_profile_hash"] = file_hash(channel_profile)

    channel_learnings = root / "channels" / "mist_of_ages" / "channel_learnings_master.md"
    if channel_learnings.exists():
        state["canonical_channel_learnings_hash"] = file_hash(channel_learnings)

    token_path = root / "secrets" / "youtube" / "mist_of_ages_oauth_token.json"
    if token_path.exists():
        state["canonical_token_hash"] = file_hash(token_path)

    legacy_identity = root / ".local" / "mist_of_ages_channel.json"
    if legacy_identity.exists():
        state["legacy_identity_hash"] = file_hash(legacy_identity)

    legacy_learnings = root / "channel" / "mist_of_ages" / "channel_learnings_master.md"
    if legacy_learnings.exists():
        state["legacy_learnings_hash"] = file_hash(legacy_learnings)

    legacy_token = root / "youtube_oauth_token.json"
    if legacy_token.exists():
        state["legacy_token_hash"] = file_hash(legacy_token)

    return state
