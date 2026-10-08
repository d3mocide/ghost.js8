"""Generate contract/schema.json from the Pydantic models.

``python -m ghostjs8.contract.generate <out.json>``. TypeScript is produced from
that file by json-schema-to-typescript (see Makefile ``contract``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import models_json_schema

from ghostjs8 import PROTOCOL_VERSION
from ghostjs8.contract import messages as m

SERVER: list[type[BaseModel]] = [
    m.Hello,
    m.Health,
    m.Session,
    m.Decode,
    m.Station,
    m.History,
    m.ReceiverStatus,
    m.GhostNet,
    m.Error,
    m.Pong,
]
CLIENT: list[type[BaseModel]] = [
    m.ClientHello,
    m.Tune,
    m.SelectReceiver,
    m.DisconnectReceiver,
    m.Subscribe,
    m.Ping,
]
HTTP: list[type[BaseModel]] = [m.ReceiverDirectory, m.NetSummary, m.NetLog]


def _strip_titles(node: object) -> None:
    """Property-level titles make json2ts emit one alias per field; drop them."""
    if isinstance(node, dict):
        node.pop("title", None)
        for value in node.values():
            _strip_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_titles(item)


def build_schema() -> dict[str, Any]:
    _, defs = models_json_schema(
        [(model, "serialization") for model in SERVER + CLIENT + HTTP],
        ref_template="#/$defs/{model}",
    )
    all_defs: dict[str, Any] = defs.get("$defs", {})
    # Pydantic marks fields with defaults optional, but serialization always
    # emits them, and the web client always sends complete messages. Requiring
    # every property keeps the generated TypeScript strict on both sides.
    for node in all_defs.values():
        if node.get("type") == "object" and "properties" in node:
            node["required"] = sorted(node["properties"].keys())
            for prop in node["properties"].values():
                _strip_titles(prop)
    for name in ("ServerMessage", "ClientMessage"):
        adapter: TypeAdapter[Any] = (
            m.server_message_adapter if name == "ServerMessage" else m.client_message_adapter
        )
        union = adapter.json_schema(ref_template="#/$defs/{model}", mode="serialization")
        union.pop("$defs", None)
        union["title"] = name
        all_defs[name] = union
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/d3mocide/ghost.js8/contract/schema.json",
        "title": "GhostJs8Protocol",
        "description": f"ghost.js8 bridge <-> browser protocol v{PROTOCOL_VERSION}. Generated; do not edit.",
        "type": "object",
        "properties": {
            "server": {"$ref": "#/$defs/ServerMessage"},
            "client": {"$ref": "#/$defs/ClientMessage"},
        },
        "$defs": dict(sorted(all_defs.items())),
    }


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0]) if args else Path("contract/schema.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_schema(), indent=2, sort_keys=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
