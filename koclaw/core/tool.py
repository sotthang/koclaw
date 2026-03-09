from abc import ABC, abstractmethod


class Tool(ABC):
    name: str
    description: str
    parameters: dict
    is_sandboxed: bool = False

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    async def execute(self, **kwargs) -> str: ...


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    async def execute(self, name: str, args: dict) -> str:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return await self._tools[name].execute(**args)

    def safe_tools(self) -> list[Tool]:
        return [t for t in self._tools.values() if not t.is_sandboxed]

    def sandboxed_tools(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.is_sandboxed]

    def clone(self) -> "ToolRegistry":
        new = ToolRegistry()
        for tool in self._tools.values():
            new.register(tool)
        return new

    def load_installed(self) -> None:
        """entry_points 기반으로 설치된 tool을 자동 등록"""
        from importlib.metadata import entry_points
        for ep in entry_points(group="koclaw.tools"):
            tool_cls = ep.load()
            self.register(tool_cls())
