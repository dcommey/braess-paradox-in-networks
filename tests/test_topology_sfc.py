import unittest

from security_braess.topology import nsfnet
from security_braess.topology_sfc import (
    build_topology_sfc_model, evaluate_topology_suite, summarize_evaluations,
    load_hhi, normalized_load_entropy, single_resource_removal_loss,
)
from security_braess.multicommodity import solve_multicommodity_equilibrium, solve_nonlinear_equilibrium


class TopologySfcTest(unittest.TestCase):
    def test_topology_model_has_multiple_requests_and_gateway_paths(self):
        model = build_topology_sfc_model(nsfnet(), include_gateway=True, request_count=4)

        self.assertEqual(len(model.requests), 4)
        self.assertEqual(len([path for path in model.paths if path.tag == "defensive_expansion"]), 4)
        result = solve_multicommodity_equilibrium(model)
        self.assertTrue(result.converged)
        self.assertGreater(result.average_cost, 0.0)

    def test_paradox_aware_improves_over_naive_on_suite(self):
        rows = summarize_evaluations(evaluate_topology_suite())
        by_topology = {}
        for row in rows:
            by_topology.setdefault(row["topology"], {})[row["policy"]] = row

        for topology, group in by_topology.items():
            self.assertGreater(group["naive_expansion"]["paradox_penalty"], 0.05, topology)
            self.assertLessEqual(
                group["paradox_aware"]["paradox_penalty"],
                0.021,
                topology,
            )
            self.assertLess(
                group["paradox_aware"]["expected_attack_loss"],
                group["naive_expansion"]["expected_attack_loss"],
                topology,
            )

    def test_nonlinear_solver_recomputes_feasible_equilibrium(self):
        model = build_topology_sfc_model(
            nsfnet(), include_gateway=True, request_count=6, gateway_slope=0.25
        )
        result = solve_nonlinear_equilibrium(model)
        self.assertTrue(result.converged)
        for request in model.requests:
            allocated = sum(result.flows[path.name] for path in model.paths_for_request(request.name))
            self.assertAlmostEqual(allocated, request.demand, places=6)

    def test_standard_resilience_metrics_are_bounded(self):
        model = build_topology_sfc_model(nsfnet(), include_gateway=True, request_count=5)
        result = solve_multicommodity_equilibrium(model)
        self.assertGreaterEqual(load_hhi(model, result), 0.0)
        self.assertLessEqual(load_hhi(model, result), 1.0)
        self.assertGreaterEqual(normalized_load_entropy(model, result), 0.0)
        self.assertLessEqual(normalized_load_entropy(model, result), 1.0)
        self.assertGreaterEqual(single_resource_removal_loss(model, result), 0.0)


if __name__ == "__main__":
    unittest.main()
