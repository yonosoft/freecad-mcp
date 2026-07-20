"""Focused external MCP acceptance for Milestone 21 rollback stabilization.

This client intentionally imports no freecad_mcp or FreeCAD modules.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_URL = "http://127.0.0.1:8765/mcp"
TRANSACTION = "Add sketch reference constraints"


class Campaign:
    def __init__(self) -> None:
        self.raw_calls: list[dict[str, object]] = []
        self.scenarios: dict[str, object] = {}

    async def call(
        self, session: ClientSession, tool: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        result = await session.call_tool(tool, arguments)
        payload = result.structuredContent
        if not isinstance(payload, dict):
            payload = None
            for block in result.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    try:
                        candidate = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(candidate, dict):
                        payload = candidate
                        break
        if not isinstance(payload, dict):
            payload = {
                "ok": False,
                "error": {
                    "code": "unstructured_tool_error",
                    "message": [getattr(block, "text", repr(block)) for block in result.content],
                },
            }
        self.raw_calls.append(
            {
                "tool": tool,
                "arguments": arguments,
                "is_error": bool(result.isError),
                "response": payload,
            }
        )
        return payload

    async def require_ok(
        self, session: ClientSession, tool: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        result = await self.call(session, tool, arguments)
        if result.get("ok") is not True:
            raise AssertionError((tool, arguments, result))
        return result

    async def snapshot(
        self, session: ClientSession, document_name: str, sketch_name: str
    ) -> dict[str, object]:
        names = {"document_name": document_name, "sketch_name": sketch_name}
        return {
            "document": await self.require_ok(session, "get_document", {"name": document_name}),
            "sketch": await self.require_ok(session, "get_sketch", names),
            "history": await self.require_ok(
                session, "get_document_history", {"document_name": document_name}
            ),
            "external": await self.require_ok(session, "list_external_geometry", names),
            "dependencies": await self.require_ok(session, "get_sketch_dependencies", names),
        }

    async def create_document(self, session: ClientSession, name: str) -> None:
        await self.require_ok(
            session, "create_document", {"name": name, "label": name.replace("_", " ")}
        )

    async def create_attached_sketch(
        self,
        session: ClientSession,
        document_name: str,
        body_name: str,
        sketch_name: str,
    ) -> None:
        await self.require_ok(
            session,
            "create_sketch",
            {
                "document_name": document_name,
                "body_name": body_name,
                "name": sketch_name,
                "support_plane": "xy_plane",
            },
        )

    async def setup_circle_story(
        self,
        session: ClientSession,
        document_name: str,
        target_name: str,
        radius: float,
    ) -> None:
        await self.create_document(session, document_name)
        await self.require_ok(
            session,
            "create_body",
            {"document_name": document_name, "name": "Body"},
        )
        await self.create_attached_sketch(session, document_name, "Body", "Source")
        await self.require_ok(
            session,
            "create_sketch_equilateral_triangle",
            {
                "document_name": document_name,
                "sketch_name": "Source",
                "circumradius": 30.0,
                "center": {"x": 0.0, "y": 0.0},
            },
        )
        await self.create_attached_sketch(session, document_name, "Body", target_name)
        await self.require_ok(
            session,
            "add_sketch_geometry",
            {
                "document_name": document_name,
                "sketch_name": target_name,
                "geometry": [
                    {
                        "type": "circle",
                        "center": {"x": 0.0, "y": 0.0},
                        "radius": radius,
                        "construction": False,
                    }
                ],
            },
        )
        for index in range(3):
            await self.require_ok(
                session,
                "add_external_geometry",
                {
                    "document_name": document_name,
                    "sketch_name": target_name,
                    "source": {
                        "type": "sketch_geometry",
                        "sketch_name": "Source",
                        "geometry_index": index,
                    },
                },
            )

    @staticmethod
    def point_on_object(index: int) -> dict[str, object]:
        return {
            "type": "point_on_object",
            "first": {
                "geometry": {
                    "kind": "external",
                    "external_reference_number": index,
                },
                "position": "start",
            },
            "second": {"kind": "internal", "geometry_index": 0},
        }

    @staticmethod
    def tangent(index: int) -> dict[str, object]:
        return {
            "type": "tangent",
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": index},
        }

    async def run_circle_story(
        self,
        session: ClientSession,
        *,
        document_name: str,
        target_name: str,
        radius: float,
        constraint_factory: Any,
        sequential: bool,
    ) -> None:
        await self.setup_circle_story(session, document_name, target_name, radius)
        calls = [[constraint_factory(index)] for index in range(3)]
        if not sequential:
            calls = [[constraint_factory(index) for index in range(3)]]
        for constraints in calls:
            before = await self.snapshot(session, document_name, target_name)
            result = await self.call(
                session,
                "add_sketch_reference_constraints",
                {
                    "document_name": document_name,
                    "sketch_name": target_name,
                    "constraints": constraints,
                },
            )
            if result.get("ok") is not True:
                after = await self.snapshot(session, document_name, target_name)
                if after != before:
                    raise AssertionError((document_name, "rollback mismatch", before, after))
                error = result.get("error", {})
                if isinstance(error, dict) and error.get("code") == (
                    "external_constraint_rollback_failed"
                ):
                    raise AssertionError((document_name, "rollback error", result))
                raise AssertionError((document_name, "mandatory workflow refused", result))
        final = await self.snapshot(session, document_name, target_name)
        sketch = final["sketch"]["sketch"]
        if sketch["geometry_count"] != 1 or sketch["constraint_count"] != 3:
            raise AssertionError((document_name, sketch))
        solver = sketch["solver"]
        if not solver["fresh"] or any(
            solver[name]
            for name in (
                "conflicting_constraint_indices",
                "redundant_constraint_indices",
                "partially_redundant_constraint_indices",
                "malformed_constraint_indices",
            )
        ):
            raise AssertionError((document_name, solver))

    async def setup_linear(self, session: ClientSession, document_name: str) -> None:
        await self.create_document(session, document_name)
        await self.require_ok(
            session,
            "create_body",
            {"document_name": document_name, "name": "Body"},
        )
        await self.create_attached_sketch(session, document_name, "Body", "Source")
        await self.require_ok(
            session,
            "create_sketch_equilateral_triangle",
            {
                "document_name": document_name,
                "sketch_name": "Source",
                "circumradius": 30.0,
                "center": {"x": 0.0, "y": 0.0},
            },
        )
        await self.create_attached_sketch(session, document_name, "Body", "Target")
        await self.require_ok(
            session,
            "add_sketch_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "geometry": [
                    {
                        "type": "line_segment",
                        "start": {"x": 0.0, "y": 2.0},
                        "end": {"x": 7.0, "y": 5.0},
                        "construction": False,
                    }
                ],
            },
        )
        await self.require_ok(
            session,
            "add_external_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "source": {
                    "type": "sketch_geometry",
                    "sketch_name": "Source",
                    "geometry_index": 0,
                },
            },
        )

    @staticmethod
    def mixed_relation(relation: str = "parallel") -> dict[str, object]:
        return {
            "type": relation,
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": 0},
        }

    async def natural_conflict(self, session: ClientSession, document_name: str) -> None:
        await self.setup_linear(session, document_name)
        before = await self.snapshot(session, document_name, "Target")
        result = await self.call(
            session,
            "add_sketch_reference_constraints",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "constraints": [
                    self.mixed_relation("parallel"),
                    self.mixed_relation("perpendicular"),
                ],
            },
        )
        if result.get("ok") is True:
            raise AssertionError((document_name, "conflict unexpectedly succeeded"))
        after = await self.snapshot(session, document_name, "Target")
        if after != before:
            raise AssertionError((document_name, "conflict rollback mismatch", before, after))
        history = after["history"]["history"]
        if history["next_undo_name"] == TRANSACTION:
            raise AssertionError((document_name, "failed transaction remains", history))

    async def linear_interactions(self, session: ClientSession, document_name: str) -> None:
        await self.setup_linear(session, document_name)
        await self.require_ok(
            session,
            "add_sketch_reference_constraints",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "constraints": [self.mixed_relation()],
            },
        )
        before_target = await self.snapshot(session, document_name, "Target")
        await self.require_ok(
            session,
            "update_sketch_constraint_value",
            {
                "document_name": document_name,
                "sketch_name": "Source",
                "constraint_index": 11,
                "value": 250.0,
            },
        )
        await self.require_ok(session, "recompute_document", {"document_name": document_name})
        after_target = await self.snapshot(session, document_name, "Target")
        before_line = before_target["sketch"]["sketch"]["geometry"][0]
        after_line = after_target["sketch"]["sketch"]["geometry"][0]
        if before_line == after_line:
            raise AssertionError((document_name, "source propagation absent"))

        before_refusal = await self.snapshot(session, document_name, "Target")
        remove_external = await self.call(
            session,
            "remove_external_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "external_reference_number": 0,
            },
        )
        if remove_external.get("ok") is True:
            raise AssertionError((document_name, "consumed external removed"))
        if await self.snapshot(session, document_name, "Target") != before_refusal:
            raise AssertionError((document_name, "external refusal mutated"))

        remove_internal = await self.call(
            session,
            "remove_sketch_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "geometry_indices": [0],
            },
        )
        if remove_internal.get("ok") is True:
            raise AssertionError((document_name, "consumed internal removed"))
        if await self.snapshot(session, document_name, "Target") != before_refusal:
            raise AssertionError((document_name, "internal refusal mutated"))

        await self.require_ok(
            session,
            "remove_sketch_constraints",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "constraint_indices": [0],
            },
        )
        after_removal = await self.snapshot(session, document_name, "Target")
        external = after_removal["external"]["external_geometry"]
        if external[0]["used_by_constraint_indices"]:
            raise AssertionError((document_name, "dependency use remained", external))
        await self.require_ok(
            session,
            "remove_external_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "external_reference_number": 0,
            },
        )

    async def history_flow(self, session: ClientSession, document_name: str) -> None:
        await self.setup_linear(session, document_name)
        await self.require_ok(
            session,
            "add_sketch_reference_constraints",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "constraints": [self.mixed_relation()],
            },
        )
        before_wrong = await self.snapshot(session, document_name, "Target")
        wrong = await self.call(
            session,
            "undo_document",
            {"document_name": document_name, "expected_transaction_name": "Wrong name"},
        )
        if wrong.get("ok") is True:
            raise AssertionError((document_name, "wrong-name undo succeeded"))
        if await self.snapshot(session, document_name, "Target") != before_wrong:
            raise AssertionError((document_name, "wrong-name undo mutated"))
        await self.require_ok(
            session,
            "undo_document",
            {"document_name": document_name, "expected_transaction_name": TRANSACTION},
        )
        await self.require_ok(
            session,
            "redo_document",
            {"document_name": document_name, "expected_transaction_name": TRANSACTION},
        )
        redone = await self.snapshot(session, document_name, "Target")
        if redone["sketch"]["sketch"]["constraint_count"] != 1:
            raise AssertionError((document_name, "redo did not restore"))
        await self.require_ok(
            session,
            "undo_document",
            {"document_name": document_name, "expected_transaction_name": TRANSACTION},
        )
        await self.require_ok(
            session,
            "add_sketch_geometry",
            {
                "document_name": document_name,
                "sketch_name": "Target",
                "geometry": [
                    {
                        "type": "line_segment",
                        "start": {"x": 20.0, "y": 0.0},
                        "end": {"x": 25.0, "y": 2.0},
                        "construction": True,
                    }
                ],
            },
        )
        history = await self.require_ok(
            session, "get_document_history", {"document_name": document_name}
        )
        if history["history"]["redo_count"] != 0:
            raise AssertionError((document_name, "redo not invalidated", history))

    async def isolation(self, session: ClientSession, first: str, second: str) -> None:
        await self.setup_linear(session, first)
        await self.setup_linear(session, second)
        second_before = await self.snapshot(session, second, "Target")
        await self.require_ok(
            session,
            "add_sketch_reference_constraints",
            {
                "document_name": first,
                "sketch_name": "Target",
                "constraints": [self.mixed_relation()],
            },
        )
        if await self.snapshot(session, second, "Target") != second_before:
            raise AssertionError("forward cross-document isolation failed")
        first_before = await self.snapshot(session, first, "Target")
        await self.require_ok(
            session,
            "add_sketch_reference_constraints",
            {
                "document_name": second,
                "sketch_name": "Target",
                "constraints": [self.mixed_relation("perpendicular")],
            },
        )
        if await self.snapshot(session, first, "Target") != first_before:
            raise AssertionError("reverse cross-document isolation failed")


async def run(output: Path, url: str) -> None:
    campaign = Campaign()
    suffix = secrets.token_hex(3).upper()
    async with (
        streamable_http_client(url) as (read_stream, write_stream, _),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        names = [tool.name for tool in tools.tools]
        if len(names) != 35 or names[-1] != "add_sketch_reference_constraints":
            raise AssertionError(("tool inventory", names))

        scenarios = [
            (
                "circumcircle_batch",
                lambda: campaign.run_circle_story(
                    session,
                    document_name=f"M21S_{suffix}_CircBatch",
                    target_name="Target",
                    radius=20.0,
                    constraint_factory=campaign.point_on_object,
                    sequential=False,
                ),
            ),
            (
                "circumcircle_sequential",
                lambda: campaign.run_circle_story(
                    session,
                    document_name=f"M21S_{suffix}_CircSeq",
                    target_name="Target",
                    radius=20.0,
                    constraint_factory=campaign.point_on_object,
                    sequential=True,
                ),
            ),
            (
                "incircle_batch",
                lambda: campaign.run_circle_story(
                    session,
                    document_name=f"M21S_{suffix}_InBatch",
                    target_name="Target",
                    radius=10.0,
                    constraint_factory=campaign.tangent,
                    sequential=False,
                ),
            ),
            (
                "incircle_sequential",
                lambda: campaign.run_circle_story(
                    session,
                    document_name=f"M21S_{suffix}_InSeq",
                    target_name="Target",
                    radius=10.0,
                    constraint_factory=campaign.tangent,
                    sequential=True,
                ),
            ),
            (
                "natural_zero_history_rollback",
                lambda: campaign.natural_conflict(session, f"M21S_{suffix}_Conflict"),
            ),
            (
                "linear_dependency_removal",
                lambda: campaign.linear_interactions(session, f"M21S_{suffix}_Linear"),
            ),
            (
                "history_undo_redo_invalidation",
                lambda: campaign.history_flow(session, f"M21S_{suffix}_History"),
            ),
            (
                "forward_reverse_isolation",
                lambda: campaign.isolation(session, f"M21S_{suffix}_IsoA", f"M21S_{suffix}_IsoB"),
            ),
        ]
        try:
            for name, scenario in scenarios:
                await scenario()
                campaign.scenarios[name] = "PASS"
            classification = "PASS"
        except Exception as exc:
            campaign.scenarios[name] = {"status": "FAIL", "reason": repr(exc)}
            classification = "FAIL"
            raise
        finally:
            output.write_text(
                json.dumps(
                    {
                        "classification": locals().get("classification", "FAIL"),
                        "suffix": suffix,
                        "tool_names": names,
                        "scenarios": campaign.scenarios,
                        "raw_calls": campaign.raw_calls,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
    print(f"Milestone 21 stabilization external acceptance: PASS ({len(scenarios)} groups)")
    print(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    asyncio.run(run(args.output.resolve(), args.url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
