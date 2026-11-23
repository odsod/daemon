"""Models and D-Bus names for the shortcuts component."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BUS_NAME = "io.github.odsod.daemon.session"
OBJECT_PATH = "/io/github/odsod/daemon/shortcuts"
INTERFACE = "io.github.odsod.daemon.Shortcuts"

Kind = Literal["builtin", "app", "command", "debug"]


class Shortcut(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    action_id: str = Field(alias="actionId")
    key: str
    kind: Kind
    command: list[str] = []
    resource_class: str | None = Field(default=None, alias="resourceClass")
    resource_class_includes: list[str] | None = Field(
        default=None, alias="resourceClassIncludes"
    )
    resource_name: str | None = Field(default=None, alias="resourceName")
    no_border: bool = Field(default=False, alias="noBorder")


class ShortcutList(BaseModel):
    model_config = ConfigDict(extra="allow")

    shortcuts: list[Shortcut] = []
