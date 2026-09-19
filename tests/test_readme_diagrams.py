"""The README diagrams are documentation people trust, so they are checked
against the code they describe.

Found 2026-09-19: the layer diagram drew `indicators -> store` and
`store -> config` although neither import exists (wrong from the day it was
written), omitted `ingest` and `dashboard` entirely, and the ER diagram missed a
table added later. Nothing noticed, because nothing compared them.

Two of the four diagrams can be checked mechanically and are. The tick-flow and
architecture diagrams describe behaviour and are kept honest by review.

If one of these fails you changed the code's shape (a new import, module or
table): update the diagram, not the test.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENT = ROOT / "agent"

NUMBER_WORDS = {3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}


def mermaid_blocks() -> list[list[str]]:
    blocks, cur = [], None
    for line in README.splitlines():
        if line.startswith("```mermaid"):
            cur = []
        elif cur is not None and line.startswith("```"):
            blocks.append(cur)
            cur = None
        elif cur is not None:
            cur.append(line)
    return blocks


def block_starting_with(prefix: str, containing: str = "") -> list[str]:
    for b in mermaid_blocks():
        if b and b[0].strip().startswith(prefix) and containing in "\n".join(b):
            return b
    raise AssertionError(f"no mermaid block starting with {prefix!r} containing {containing!r}")


# --- layer-dependency diagram vs the real imports -----------------------------

def module_names() -> set[str]:
    return {p.stem for p in AGENT.glob("*.py") if p.stem != "__init__"}


def actual_imports() -> dict[str, dict[str, str]]:
    """module -> {dependency: 'top' or 'lazy'}. 'lazy' means every import of it
    is inside a function; a module-level import anywhere makes it 'top'."""
    mods = module_names()
    result = {}
    for path in AGENT.glob("*.py"):
        if path.stem == "__init__":
            continue
        deps: dict[str, str] = {}

        def note(name, lazy):
            if name in mods and name != path.stem:
                deps[name] = "top" if (not lazy or deps.get(name) == "top") else "lazy"

        def visit(node, lazy):
            for child in ast.iter_child_nodes(node):
                inside = lazy or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                if isinstance(child, ast.ImportFrom) and child.module:
                    if child.module == "agent":
                        for alias in child.names:
                            note(alias.name, inside)
                    elif child.module.startswith("agent."):
                        note(child.module.split(".")[1], inside)
                elif isinstance(child, ast.Import):
                    for alias in child.names:
                        if alias.name.startswith("agent."):
                            note(alias.name.split(".")[1], inside)
                visit(child, inside)

        visit(ast.parse(path.read_text(encoding="utf-8")), False)
        result[path.stem] = deps
    return result


def diagram_imports() -> dict[str, dict[str, str]]:
    """The same shape, read from the README. Nodes are declared as ID[name.py...];
    `-->` is a module-level import, `-.->` one made inside a function."""
    block = block_starting_with("flowchart", containing="run.py<br/>orchestration")
    ids = {}
    for line in block:
        m = re.match(r"\s*(\w+)\[(\w+)\.py", line)
        if m:
            ids[m.group(1)] = m.group(2)
    edges: dict[str, dict[str, str]] = {name: {} for name in ids.values()}
    for line in block:
        m = re.match(r"\s*(\w+)\s*(-->|-\.->)\s*(.+)", line)
        if not m:
            continue
        src, arrow, targets = ids[m.group(1)], m.group(2), m.group(3)
        for target in re.split(r"\s*&\s*", targets.strip()):
            edges[src][ids[target.strip()]] = "top" if arrow == "-->" else "lazy"
    return edges


def test_layer_diagram_shows_every_module():
    assert set(diagram_imports()) == module_names()


def test_layer_diagram_matches_the_real_imports():
    real, drawn = actual_imports(), diagram_imports()
    problems = []
    for module in sorted(real):
        for dep in sorted(set(real[module]) | set(drawn.get(module, {}))):
            want, got = real[module].get(dep), drawn.get(module, {}).get(dep)
            if want != got:
                problems.append(f"{module} -> {dep}: code has {want or 'nothing'}, "
                                f"diagram has {got or 'nothing'}")
    assert not problems, "\n".join(problems)


def test_the_layers_have_no_cycles():
    """The README claims modules only depend downward. That is only true if the
    graph has no cycle, lazy imports included."""
    graph = {m: set(d) for m, d in actual_imports().items()}
    state = {}

    def dfs(node, path):
        state[node] = "visiting"
        for dep in graph.get(node, ()):
            if state.get(dep) == "visiting":
                raise AssertionError("import cycle: " + " -> ".join(path + [node, dep]))
            if dep not in state:
                dfs(dep, path + [node])
        state[node] = "done"

    for module in graph:
        if module not in state:
            dfs(module, [])


# --- ER diagram vs store.SCHEMA ------------------------------------------------

def schema_tables() -> dict[str, tuple[set[str], set[str]]]:
    from agent import store

    tables = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", store.SCHEMA, re.S):
        columns, pk = set(), set()
        for line in m.group(2).splitlines():
            line = re.sub(r"--.*", "", line).strip().rstrip(",")
            if not line:
                continue
            pm = re.match(r"PRIMARY KEY \((.*)\)", line)
            if pm:
                pk |= {c.strip() for c in pm.group(1).split(",")}
                continue
            name = line.split()[0]
            columns.add(name)
            if "PRIMARY KEY" in line:
                pk.add(name)
        tables[m.group(1)] = (columns, pk)
    return tables


def diagram_tables() -> dict[str, tuple[set[str], set[str]]]:
    tables, current = {}, None
    for line in block_starting_with("erDiagram"):
        entity = re.match(r"\s*(\w+) \{", line)
        if entity:
            current = entity.group(1)
            tables[current] = (set(), set())
        elif line.strip() == "}":
            current = None
        elif current:
            attr = re.match(r"\s*\w+ (\w+)( PK)?", line)
            if attr:
                tables[current][0].add(attr.group(1))
                if attr.group(2):
                    tables[current][1].add(attr.group(1))
    return tables


def test_er_diagram_has_every_table_with_its_columns_and_keys():
    assert diagram_tables() == schema_tables()


def test_data_model_prose_counts_the_tables():
    n = len(schema_tables())
    assert f"{NUMBER_WORDS[n]} tables, all defined in `store.SCHEMA`" in README
