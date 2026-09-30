import unittest
from security_braess.lbcd import partition_score, detect_communities

class LBCDCommunityTests(unittest.TestCase):
    def test_score_and_total_variance_identity(self):
        edges = [(0,1),(1,2),(2,0),(3,4),(4,5),(5,3),(2,3)]
        loads = dict(enumerate([1,2,3,4,5,6]))
        _, q, h = partition_score(edges, loads, [{0,1,2},{3,4,5}])
        self.assertAlmostEqual(q, 5/14)
        self.assertAlmostEqual(h, 4/17.5)
        self.assertAlmostEqual(partition_score(edges, loads, [set(loads)])[2], 1)
        self.assertAlmostEqual(partition_score(edges, loads, [{v} for v in loads])[2], 0)

    def test_modularity_only_separates_dense_groups(self):
        edges = [(0,1),(1,2),(2,0),(3,4),(4,5),(5,3),(2,3)]
        groups, history = detect_communities(edges, {i:1 for i in range(6)}, beta=1)
        self.assertEqual({frozenset(c) for c in groups}, {frozenset([0,1,2]),frozenset([3,4,5])})
        self.assertTrue(all(b>a for a,b in zip(history,history[1:])))

    def test_compression_preserves_all_vertices(self):
        edges = [(i,(i+1)%12) for i in range(12)]
        loads = {i: (i%4)+1 for i in range(12)}
        groups, history = detect_communities(edges,loads)
        self.assertEqual(sum(len(c) for c in groups),len(loads))
        self.assertEqual(set().union(*groups),set(loads))
        score,q,h=partition_score(edges,loads,groups)
        self.assertGreaterEqual(h,0)
        self.assertLessEqual(h,1)
        self.assertTrue(all(b>a for a,b in zip(history,history[1:])))

if __name__ == '__main__': unittest.main()
