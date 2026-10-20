"""Minimal S-expression reader for KiCad files.

(kicad_pcb (version 20240108) (footprint "Lib:Name" (at 10 20 90) ...))
becomes nested lists: ['kicad_pcb', ['version', '20240108'], ['footprint', 'Lib:Name', ...]].
Quoted strings and bare atoms are both returned as str.
"""


class SexprError(ValueError):
    pass


def parse(text):
    stack = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            if len(stack) < 2:
                raise SexprError(f"unbalanced ')' at offset {i}")
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    j += 1
                    buf.append({"n": "\n", "t": "\t"}.get(text[j], text[j]))
                else:
                    buf.append(text[j])
                j += 1
            if j >= n:
                raise SexprError(f"unterminated string at offset {i}")
            stack[-1].append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()\"":
                j += 1
            stack[-1].append(text[i:j])
            i = j
    if len(stack) != 1 or len(stack[0]) != 1:
        raise SexprError("unbalanced parentheses at end of file")
    return stack[0][0]


def children(node, name):
    """Direct sub-lists of `node` whose head is `name`."""
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def child(node, name, default=None):
    found = children(node, name)
    return found[0] if found else default


def value(node, name, default=None, index=1):
    c = child(node, name)
    return c[index] if c is not None and len(c) > index else default


def floats(node, start=1):
    return [float(v) for v in node[start:] if isinstance(v, str) and _is_num(v)]


def _is_num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
