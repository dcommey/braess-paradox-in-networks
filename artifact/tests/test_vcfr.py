import itertools
import unittest
from security_braess.lbcd_vcfr import Column, solve_vcfr, solve_partitioned

class VCFRTests(unittest.TestCase):
    def columns(self):
        return [Column(r+n,r,{n:1},{},frozenset([(n,'fw')])) for r in ['r1','r2'] for n in ['a','b']]

    def test_milp_matches_exhaustive_placement_objective(self):
        columns=self.columns()
        alpha=.6
        result=solve_vcfr(columns,['r1','r2'],{'a':2,'b':2},{},
             storage_capacity={'a':1,'b':1},storage_price={'a':1,'b':1},alpha=alpha,opex_scale=2)
        costs=[]
        for choice in itertools.product(['a','b'],repeat=2):
            eta=max(choice.count('a'),choice.count('b'))/2
            costs.append(alpha*eta+(1-alpha)*len(set(choice))/2)
        self.assertAlmostEqual(result['objective'],min(costs))
        self.assertEqual(result['mip_gap'],0)

    def test_shared_storage_and_partition_integration(self):
        result=solve_partitioned(self.columns(),{'r1':1,'r2':1},[{'r1'},{'r2'}],
             {'a':4,'b':4},{},storage_capacity={'a':4,'b':4},
             storage_price={'a':1,'b':2},alpha=0)
        self.assertEqual(result['active_storage'],{('a','fw')})
        self.assertEqual(result['maximum_utilization'],.5)
        self.assertEqual(result['community_count'],2)

    def test_bandwidth_and_qos_feasibility(self):
        cols=[Column('slow','r',{'a':1},{'link':1},frozenset(),10),
              Column('fast','r',{'b':1},{'link':1},frozenset(),1)]
        result=solve_vcfr(cols,['r'],{'a':2,'b':2},{'link':1},delay_limits={'r':2})
        self.assertEqual(result['selected'][0].name,'fast')
        with self.assertRaises(RuntimeError):
            solve_vcfr(cols,['r'],{'a':2,'b':2},{'link':.5})

    def test_optimal_ties_are_invariant_to_column_order(self):
        columns=self.columns()
        def selected(cols):
            return {c.name for c in solve_vcfr(cols,['r1','r2'],{'a':2,'b':2},{})['selected']}
        expected=selected(columns)
        self.assertEqual(expected,selected(list(reversed(columns))))
        extra=Column('zz-unused','r1',{'a':2},{},frozenset())
        self.assertEqual(expected,selected(columns+[extra]))

    def test_feasible_objective_is_recomputed_after_integer_rounding(self):
        cols=[Column(f'{r}-{n}',str(r),{n:1},{},frozenset()) for r in range(5) for n in ['a','b']]
        cols+=[Column(f'{r}-gateway',str(r),{'a':1,'b':1},{},frozenset()) for r in range(5)]
        result=solve_vcfr(cols,[str(r) for r in range(5)],{'a':5,'b':5},{})
        self.assertAlmostEqual(result['objective'],.6,places=12)
        self.assertAlmostEqual(result['maximum_utilization'],.6,places=12)

if __name__=='__main__': unittest.main()
