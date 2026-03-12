class Node:
    def __init__(self, content: str):
        self.content = content
        self.children = []

    def export(self):
        return {
            "content": self.content,
            "children": [c.export() for c in self.children]
        }
