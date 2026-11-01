"""Guards against the bug that broke /coach/ask: a module-level name in api.py that is imported
and then reassigned (coach = Coach() shadowed `from .agents import coach`). Runs without FastAPI."""
import ast
import os


def test_no_shadowed_imports():
    path = os.path.join(os.path.dirname(__file__), "..", "batchmate", "api.py")
    tree = ast.parse(open(path).read())
    imported, assigned = set(), set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.Assign):
            assigned |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(node.name)
    clash = imported & assigned
    assert not clash, f"api.py reassigns imported names: {clash}"


if __name__ == "__main__":
    test_no_shadowed_imports()
    print("api names OK")
