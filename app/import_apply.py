from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from fieldflow.domain.scheduling.types import Activity, Relationship


@dataclass(frozen=True)
class ImportChangeSummary:
    mode: str  # "overwrite" or "merge"
    activities_added: int
    activities_updated: int
    activities_removed: int
    relationships_added: int
    relationships_updated: int
    relationships_removed: int
    relationships_dropped_invalid: int
    relationships_dropped_self: int
    warnings: List[str]


def _rel_key(r: Relationship) -> Tuple[str, str, str]:
    return (str(r.pred_id), str(r.succ_id), r.rel_type.value)


def validate_relationships(
    activities: List[Activity],
    relationships: List[Relationship],
) -> Tuple[List[Relationship], int, int]:
    """
    Drops:
      - self links
      - links where pred or succ is missing from activities
    Returns: (filtered_relationships, dropped_invalid, dropped_self)
    """
    ids = {str(a.id) for a in activities}
    out: List[Relationship] = []
    dropped_invalid = 0
    dropped_self = 0

    for r in relationships:
        pred = str(r.pred_id)
        succ = str(r.succ_id)
        if pred == succ:
            dropped_self += 1
            continue
        if pred not in ids or succ not in ids:
            dropped_invalid += 1
            continue
        out.append(r)

    return out, dropped_invalid, dropped_self


def apply_import_overwrite(
    existing_activities: List[Activity],
    existing_relationships: List[Relationship],
    imported_activities: List[Activity],
    imported_relationships: List[Relationship],
    warnings: Optional[List[str]] = None,
) -> Tuple[List[Activity], List[Relationship], ImportChangeSummary]:
    """
    Overwrite mode: replace activities/relationships with imported (after validation).
    """
    warnings = list(warnings or [])

    filtered_rels, dropped_invalid, dropped_self = validate_relationships(
        imported_activities, imported_relationships
    )

    summary = ImportChangeSummary(
        mode="overwrite",
        activities_added=len(imported_activities),
        activities_updated=0,
        activities_removed=len(existing_activities),
        relationships_added=len(filtered_rels),
        relationships_updated=0,
        relationships_removed=len(existing_relationships),
        relationships_dropped_invalid=dropped_invalid,
        relationships_dropped_self=dropped_self,
        warnings=warnings,
    )
    return list(imported_activities), list(filtered_rels), summary


def apply_import_merge(
    existing_activities: List[Activity],
    existing_relationships: List[Relationship],
    imported_activities: List[Activity],
    imported_relationships: List[Relationship],
    warnings: Optional[List[str]] = None,
) -> Tuple[List[Activity], List[Relationship], ImportChangeSummary]:
    """
    Merge by ID:
      - Activities:
          - If imported has the ID, update name/duration always.
          - Constraints: imported snet/fnet override only if non-None; otherwise keep existing.
          - New activities are added.
          - No removals in merge mode.
      - Relationships:
          - Keyed by (pred, succ, type). If same key exists, lag updates to imported value.
          - Otherwise added. No removals in merge mode.
      - Validation runs at end to drop invalid/self links.
    """
    warnings = list(warnings or [])

    ex_by_id: Dict[str, Activity] = {str(a.id): a for a in existing_activities}
    im_by_id: Dict[str, Activity] = {str(a.id): a for a in imported_activities}

    added = 0
    updated = 0

    # preserve existing order; append new IDs at end
    out_ids: List[str] = [str(a.id) for a in existing_activities]
    out_by_id: Dict[str, Activity] = dict(ex_by_id)

    for aid, imp in im_by_id.items():
        if aid in out_by_id:
            ex = out_by_id[aid]
            new_snet = imp.snet if imp.snet is not None else ex.snet
            new_fnet = imp.fnet if imp.fnet is not None else ex.fnet
            out_by_id[aid] = Activity(
                id=aid,
                name=imp.name or ex.name,
                duration_days=int(imp.duration_days),
                snet=new_snet,
                fnet=new_fnet,
            )
            updated += 1
        else:
            out_by_id[aid] = imp
            out_ids.append(aid)
            added += 1

    out_activities = [out_by_id[aid] for aid in out_ids]

    # Relationships merge
    ex_rel: Dict[Tuple[str, str, str], Relationship] = {
        _rel_key(r): r for r in existing_relationships
    }
    rel_added = 0
    rel_updated = 0

    for r in imported_relationships:
        k = _rel_key(r)
        if k in ex_rel:
            ex = ex_rel[k]
            if int(ex.lag_days) != int(r.lag_days):
                ex_rel[k] = Relationship(ex.pred_id, ex.succ_id, ex.rel_type, int(r.lag_days))
                rel_updated += 1
        else:
            ex_rel[k] = r
            rel_added += 1

    out_relationships = list(ex_rel.values())
    out_relationships, dropped_invalid, dropped_self = validate_relationships(
        out_activities, out_relationships
    )

    summary = ImportChangeSummary(
        mode="merge",
        activities_added=added,
        activities_updated=updated,
        activities_removed=0,
        relationships_added=rel_added,
        relationships_updated=rel_updated,
        relationships_removed=0,
        relationships_dropped_invalid=dropped_invalid,
        relationships_dropped_self=dropped_self,
        warnings=warnings,
    )
    return out_activities, out_relationships, summary