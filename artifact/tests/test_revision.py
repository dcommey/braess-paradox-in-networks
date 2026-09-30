"""Independent numerical checks for the new asymmetric sufficient condition."""
import unittest
from security_braess.model import Resource
from security_braess.multicommodity import (
    Request, MCPath, MultiServiceModel, solve_multicommodity_equilibrium,
)


class AsymmetricConditionTests(unittest.TestCase):
    def test_unequal_costs_slopes_and_capacities(self):
        # Different u values exercise alpha = a D / u, not an implicit u=D.
        for c1, c2, alpha1, alpha2 in [(2., 2.1, 1., 1.), (2., 1.9, .8, 1.2), (2.2, 2., 1.1, .9)]:
            demand = 3.
            c0 = (alpha2*c1 + alpha1*c2 + alpha1*alpha2)/(alpha1+alpha2)
            upper = min(c1+alpha1, c2+alpha2)
            epsilon = (c0+upper)/2-alpha1-alpha2
            self.assertGreaterEqual(epsilon, 0)
            resources = {
                'a': Resource('a', base_delay=0, slope=alpha1*7/demand, capacity=7),
                'b': Resource('b', base_delay=0, slope=alpha2*11/demand, capacity=11),
                'c1': Resource('c1', base_delay=c1, slope=0, capacity=1),
                'c2': Resource('c2', base_delay=c2, slope=0, capacity=1),
                'g': Resource('g', base_delay=epsilon, slope=0, capacity=1),
            }
            requests=(Request('r', demand, 's', 't'),)
            paths=(MCPath('left','r',('a','c1')), MCPath('right','r',('c2','b')))
            before=MultiServiceModel('before',resources,requests,paths)
            after=MultiServiceModel('after',resources,requests,paths+(MCPath('shortcut','r',('a','g','b')),))
            baseline=solve_multicommodity_equilibrium(before,tolerance=1e-10)
            expanded=solve_multicommodity_equilibrium(after,tolerance=1e-10)
            self.assertAlmostEqual(baseline.average_cost,c0,places=7)
            self.assertAlmostEqual(expanded.average_cost,epsilon+alpha1+alpha2,places=7)
            self.assertAlmostEqual(expanded.flows['shortcut'],demand,places=7)
            self.assertGreater(expanded.average_cost,baseline.average_cost)


if __name__=='__main__':
    unittest.main()
