from .node import Node

class TreeEngine:
    def __init__(self):
        self.root = Node("ROOT")
        self.current = self.root
        self.history = []

    def add(self, content: str):
        new = Node(content)
        self.current.children.append(new)
        self.history.append(self.current)
        self.current = new
        return self.export_state()

    def backtrack(self):
        if not self.history:
            return {"error": "no history"}
        self.current = self.history.pop()
        return self.export_state()

    def breakpoint(self):
        # 占位实现
        return {"meta": "breakpoint set", "state": self.export_state()}

    def export_state(self):
        return {"tree": self.root.export(), "current": self.current.content}
