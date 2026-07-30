"""The facade over the routing layers.

Nothing here exercises routing behaviour -- the layer suites own that. These two
guard the decomposition itself: the layers may only depend on earlier layers, and
the facade may not silently stop re-exporting one of them.
"""

from __future__ import annotations

import ast
import unittest

from routing_fixtures import (
    ROOT,
    RoutingTestCase,
)


class RoutingFacadeTests(RoutingTestCase):
    def test_routing_layers_only_depend_on_earlier_layers(self) -> None:
        """The decomposition is a stack, and the stack is the point.

        Splitting one 2,000-line module into six is worth nothing if the six import
        each other freely -- that is the same tangle with more files, and it costs
        the one property the split buys: you can read `routing_closure` knowing it
        cannot be reached into by validation, or read `routing_policy` knowing it
        answers to nobody. Declared order is dependency order, checked from the
        imports rather than from a comment claiming it.
        """
        order = [
            "routing_policy",
            "routing_markdown",
            "routing_closure",
            "routing_manifest",
            "routing_resolver",
            "routing_transport",
        ]
        rank = {name: index for index, name in enumerate(order)}
        for name, index in sorted(rank.items()):
            module = ROOT / f"aitk/{name}.py"
            with self.subTest(module=name):
                self.assertTrue(module.is_file(), f"{name} is missing")
                tree = ast.parse(module.read_text())
                imported = {
                    node.module.split(".", 1)[1]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and node.module is not None
                    and node.module.startswith("aitk.")
                }
                # `model_routing` is the facade, so importing it from a layer is a
                # cycle through the front door and is worth naming separately.
                self.assertNotIn(
                    "model_routing", imported, f"{name} imports its own facade"
                )
                for dependency in sorted(imported):
                    self.assertIn(dependency, rank, f"{name} imports {dependency}")
                    self.assertLess(
                        rank[dependency],
                        index,
                        f"{name} imports {dependency}, which is not below it",
                    )

    def test_the_routing_facade_exposes_every_layer_symbol(self) -> None:
        """Nothing may become unreachable by moving where it is defined.

        Callers import from `aitk.model_routing`, so a symbol that lands in a layer
        without a facade re-export is deleted from every caller's perspective while
        still passing every test that imports it from its new home. The facade's
        `__all__` is also checked to be honest in both directions -- a name it lists
        but cannot supply fails at import time, which is the wrong place to find out.
        """
        import aitk.model_routing as facade

        for name in facade.__all__:
            with self.subTest(symbol=name):
                self.assertTrue(
                    hasattr(facade, name), f"__all__ lists {name} but it is not bound"
                )
        exported = set(facade.__all__)
        # The facade defines nothing of its own, so anything bound on it beyond a
        # dunder or an imported layer module must be in `__all__`.
        bound = {
            name
            for name in vars(facade)
            if not name.startswith("__") and name not in {"annotations"}
        }
        self.assertEqual(set(), bound - exported - {"aitk"})
        # Every public name a layer defines has to reach the facade. Private helpers
        # are re-exported only where a test needs them, which is why this direction
        # is asserted for public names only.
        for module in (
            "routing_policy",
            "routing_markdown",
            "routing_closure",
            "routing_manifest",
            "routing_resolver",
            "routing_transport",
        ):
            tree = ast.parse((ROOT / f"aitk/{module}.py").read_text())
            defined = {
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and not node.name.startswith("_")
            }
            with self.subTest(module=module):
                self.assertEqual(
                    set(),
                    defined - exported,
                    f"{module} defines public names the facade does not re-export",
                )


if __name__ == "__main__":
    unittest.main()
