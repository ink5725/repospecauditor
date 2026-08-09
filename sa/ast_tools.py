"""AST-based code retrieval built on tree-sitter.

This module implements the lightweight AST query layer of the pipeline
(the paper uses Weggli; here we provide an equivalent, dependency-light
implementation with parameterized query templates):
  - find function definitions / struct definitions
  - find all call sites of a function (callers)
  - extract usage examples of an entity
  - extract the enclosing function of any source line
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from tree_sitter import Language, Parser
import tree_sitter_c

C_LANGUAGE = Language(tree_sitter_c.language())


def new_parser() -> Parser:
    p = Parser(C_LANGUAGE)
    return p


# --------------------------------------------------------------------- #
# Single-file extraction (used by the indexer)                          #
# --------------------------------------------------------------------- #
def extract_file_info(source: bytes) -> Dict[str, list]:
    """Parse one C file, return:
    {
      'functions': [(name, start_line, end_line)],
      'calls':     [(caller_name, line, callee)],
      'structs':   [(name, start_line, end_line)],
    }
    Caller name is the enclosing function ('' if outside any function).
    """
    parser = new_parser()
    tree = parser.parse(source)
    root = tree.root_node
    info: Dict[str, list] = {"functions": [], "calls": [], "structs": []}
    seen_structs = set()

    def enclosing_function(node, cache: Dict) -> Optional[str]:
        """Walk ancestors to find the innermost function_definition name."""
        parent = node.parent
        while parent is not None:
            if parent.type == "function_definition":
                name = function_name(parent)
                if name:
                    return name
            parent = parent.parent
        return None

    def function_name(node) -> Optional[str]:
        decl = node.child_by_field_name("declarator")
        if decl is None:
            return None
        # function_declarator -> declarator (identifier or pointer)
        cur = decl
        while cur is not None and cur.type != "identifier":
            if cur.type in ("pointer_declarator", "function_declarator",
                            "parenthesized_declarator"):
                cur = cur.child_by_field_name("declarator") or cur.named_children[0]
            else:
                break
        if cur is not None and cur.type == "identifier":
            return cur.text.decode("utf-8", errors="replace")
        return None

    def visit(node) -> None:
        ntype = node.type
        if ntype == "function_definition":
            name = function_name(node)
            if name:
                start = node.start_point[0] + 1
                end = node.end_point[0] + 1
                info["functions"].append((name, start, end))
        elif ntype == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier":
                callee = fn.text.decode("utf-8", errors="replace")
                caller = enclosing_function(node, {})
                info["calls"].append((caller or "", node.start_point[0] + 1, callee))
        elif ntype == "struct_specifier":
            ident = node.child_by_field_name("name")
            if ident is not None and ident.type in ("type_identifier", "identifier"):
                name = ident.text.decode("utf-8", errors="replace")
                if name not in seen_structs:
                    seen_structs.add(name)
                    info["structs"].append(
                        (name, node.start_point[0] + 1, node.end_point[0] + 1)
                    )
        for child in node.named_children:
            visit(child)

    visit(root)
    return info


# --------------------------------------------------------------------- #
# Query templates (parameterized by entity name)                        #
# --------------------------------------------------------------------- #
FUNCTION_DEF_QUERY = "function definition of {entity}"
STRUCT_DEF_QUERY = "struct definition of {entity}"
CALL_SITES_QUERY = "all call sites of function {entity}"
