"""Deterministic player-candidate generation and review."""

from app.services.candidates.service import (
    CANDIDATE_SCHEMA_VERSION,
    CandidateError,
    CandidateImpossibleMergeError,
    CandidateNotFoundError,
    build_player_candidates,
    load_player_candidates,
    merge_player_candidates,
    reject_player_candidate,
    restore_player_candidate,
    select_player_candidate,
    unmerge_player_candidates,
)

__all__ = [
    "CANDIDATE_SCHEMA_VERSION",
    "CandidateError",
    "CandidateImpossibleMergeError",
    "CandidateNotFoundError",
    "build_player_candidates",
    "load_player_candidates",
    "merge_player_candidates",
    "reject_player_candidate",
    "restore_player_candidate",
    "select_player_candidate",
    "unmerge_player_candidates",
]
