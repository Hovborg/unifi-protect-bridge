from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .automation_payloads import (
    automation_needs_replace,
    build_managed_automation_payload,
    group_managed_automations,
)

PLAN_ACTION_CREATE = "create"
PLAN_ACTION_KEEP = "keep"
PLAN_ACTION_REPLACE = "replace"
PLAN_ACTION_DELETE_DUPLICATE = "delete_duplicate"
PLAN_ACTION_DELETE_STALE = "delete_stale"

PLAN_ACTIONS = (
    PLAN_ACTION_CREATE,
    PLAN_ACTION_KEEP,
    PLAN_ACTION_REPLACE,
    PLAN_ACTION_DELETE_DUPLICATE,
    PLAN_ACTION_DELETE_STALE,
)


def build_desired_automations(
    catalog: Mapping[str, Any],
    webhook_url: str,
) -> dict[str, dict[str, Any]]:
    desired: dict[str, dict[str, Any]] = {}
    for source in catalog.get("managed_sources") or []:
        device_macs = [
            camera["device_mac"]
            for camera in catalog.get("cameras") or []
            if camera.get("device_mac") and source in (camera.get("supported_sources") or [])
        ]
        if not device_macs:
            continue
        desired[source] = build_managed_automation_payload(source, device_macs, webhook_url)
    return desired


def build_managed_automation_plan(
    catalog: Mapping[str, Any],
    automations: list[dict[str, Any]],
    webhook_url: str,
) -> dict[str, Any]:
    desired_by_source = build_desired_automations(catalog, webhook_url)
    existing_by_source = group_managed_automations(automations)
    managed_count = sum(len(items) for items in existing_by_source.values())
    actions: list[dict[str, Any]] = []

    for source, desired in desired_by_source.items():
        existing_candidates = list(existing_by_source.pop(source, []))
        existing = existing_candidates[0] if existing_candidates else None
        duplicates = existing_candidates[1:]

        if existing and not automation_needs_replace(existing, desired):
            actions.append(
                {
                    "action": PLAN_ACTION_KEEP,
                    "source": source,
                    "id": _automation_id(existing),
                    "name": existing.get("name"),
                    "reason": "existing automation matches desired payload",
                }
            )
            actions.extend(
                _delete_actions(PLAN_ACTION_DELETE_DUPLICATE, source, duplicates)
            )
            continue

        if existing_candidates:
            actions.append(
                {
                    "action": PLAN_ACTION_REPLACE,
                    "source": source,
                    "delete_ids": _automation_ids(existing_candidates),
                    "delete_names": _automation_names(existing_candidates),
                    "payload": desired,
                    "reason": "managed automation payload differs from desired state",
                }
            )
        else:
            actions.append(
                {
                    "action": PLAN_ACTION_CREATE,
                    "source": source,
                    "payload": desired,
                    "reason": "managed automation is missing",
                }
            )

    for source, stale_items in existing_by_source.items():
        actions.extend(_delete_actions(PLAN_ACTION_DELETE_STALE, source, stale_items))

    return {
        "dry_run": True,
        "nvr_id": catalog.get("nvr_id"),
        "nvr_name": catalog.get("nvr_name"),
        "camera_count": len(catalog.get("cameras") or []),
        "managed_source_count": len(desired_by_source),
        "ignored_user_owned": len(automations) - managed_count,
        "actions": actions,
        "summary": summarize_plan_actions(actions, len(automations) - managed_count),
    }


def summarize_plan_actions(
    actions: list[Mapping[str, Any]],
    ignored_user_owned: int = 0,
) -> dict[str, int]:
    summary = {action: 0 for action in PLAN_ACTIONS}
    for item in actions:
        action = item.get("action")
        if action in summary:
            summary[action] += 1
    summary["ignored_user_owned"] = ignored_user_owned
    return summary


def plan_delete_count(plan: Mapping[str, Any]) -> int:
    count = 0
    for action in plan.get("actions") or []:
        if not isinstance(action, Mapping):
            continue
        if action.get("action") in {PLAN_ACTION_REPLACE}:
            count += len(action.get("delete_ids") or [])
        elif action.get("action") in {PLAN_ACTION_DELETE_DUPLICATE, PLAN_ACTION_DELETE_STALE}:
            count += 1 if action.get("id") else 0
    return count


def plan_has_missing_delete_ids(plan: Mapping[str, Any]) -> bool:
    for action in plan.get("actions") or []:
        if not isinstance(action, Mapping):
            continue
        if action.get("action") == PLAN_ACTION_REPLACE:
            delete_ids = action.get("delete_ids") or []
            delete_names = action.get("delete_names") or []
            if len(delete_ids) != len(delete_names):
                return True
        elif action.get("action") in {PLAN_ACTION_DELETE_DUPLICATE, PLAN_ACTION_DELETE_STALE}:
            if not action.get("id"):
                return True
    return False


def _delete_actions(
    action: str,
    source: str,
    automations: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "action": action,
            "source": source,
            "id": _automation_id(automation),
            "name": automation.get("name"),
            "reason": "extra bridge-owned automation"
            if action == PLAN_ACTION_DELETE_DUPLICATE
            else "bridge-owned source is no longer desired",
        }
        for automation in automations
    ]


def _automation_id(automation: Mapping[str, Any]) -> str | None:
    value = automation.get("id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _automation_ids(automations: list[Mapping[str, Any]]) -> list[str]:
    return [
        automation_id
        for automation in automations
        if (automation_id := _automation_id(automation))
    ]


def _automation_names(automations: list[Mapping[str, Any]]) -> list[str | None]:
    return [automation.get("name") for automation in automations]
