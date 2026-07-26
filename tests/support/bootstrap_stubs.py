"""Shared FreeCAD bootstrap stubs."""


class WorkbenchStub:
    def __init__(self) -> None:
        self.toolbars: list[tuple[str, list[str]]] = []
        self.menus: list[tuple[str, list[str]]] = []

    def appendToolbar(self, name: str, commands: list[str]) -> None:
        self.toolbars.append((name, commands))

    def appendMenu(self, name: str, commands: list[str]) -> None:
        self.menus.append((name, commands))


class ConsoleStub:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.errors: list[str] = []
        self.logs: list[str] = []

    def PrintMessage(self, message: str) -> None:
        self.messages.append(message)

    def PrintError(self, message: str) -> None:
        self.errors.append(message)

    def PrintLog(self, message: str) -> None:
        self.logs.append(message)
