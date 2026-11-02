import math
import unittest

from notebook_pen_motion import motion_chunks,sample_motion_path


class MotionTests(unittest.TestCase):
    def test_subpixel_plotter_dot_is_not_a_zero_length_stroke(self):
        path=[(10,20),(10.3,20)]
        self.assertEqual(sample_motion_path(path),path)
        self.assertEqual(motion_chunks(path,.1),[{'points':path,'duration':.1}])

    def test_sample_preserves_corners_endpoints_and_arc_length(self):
        path=[(10,20),(10,20),(10,117),(210,117),(210,20),(10,20)]
        dense=sample_motion_path(path)
        self.assertEqual(dense[0],path[0]);self.assertEqual(dense[-1],path[-1])
        for point in path:self.assertIn(point,dense)
        self.assertLessEqual(max(math.dist(a,b) for a,b in zip(dense,dense[1:])),1.25+1e-10)
        self.assertAlmostEqual(sum(math.dist(a,b) for a,b in zip(dense,dense[1:])),
                               sum(math.dist(a,b) for a,b in zip(path,path[1:])))
        self.check_partition(dense)

    def test_sample_budget_rejects_before_motion(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            sample_motion_path([(0,0),(5000,0)])
        dense=sample_motion_path([(0,0),(2999,0)],1)
        self.assertEqual(len(dense),3000)
        with self.assertRaisesRegex(ValueError,'budget'):
            sample_motion_path([(0,0),(3000,0)],1)

    def test_sample_validation(self):
        for spacing in (True,0,.1,3,float('nan'),float('inf'),'1'):
            with self.assertRaises(ValueError):sample_motion_path([(0,0),(10,0)],spacing)
        for path in ([],[(0,0)],[(0,0),(0,0)],[(0,0),(float('nan'),1)]):
            with self.assertRaises(ValueError):sample_motion_path(path)

    def check_partition(self,path,duration=2.5):
        chunks=motion_chunks(path,duration)
        self.assertEqual(chunks[0]['points'][0],tuple(path[0]))
        self.assertEqual(chunks[-1]['points'][-1],tuple(path[-1]))
        self.assertAlmostEqual(sum(c['duration'] for c in chunks),duration)
        total=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
        for i,c in enumerate(chunks):
            self.assertGreater(c['duration'],0)
            self.assertLessEqual(c['duration'],.65+1e-12)
            self.assertGreaterEqual(len(c['points']),2)
            self.assertTrue(all(a!=b for a,b in zip(c['points'],c['points'][1:])))
            length=sum(math.dist(a,b) for a,b in zip(c['points'],c['points'][1:]))
            self.assertAlmostEqual(length,total/len(chunks),places=7)
            if i:self.assertEqual(chunks[i-1]['points'][-1],c['points'][0])
        for point in path:
            self.assertTrue(any(tuple(point) in c['points'] for c in chunks))
        return chunks

    def test_line_exact_boundaries(self):
        self.check_partition([(i,0) for i in range(201)])

    def test_sparse_line(self):
        self.check_partition([(0,0),(1000,0)])

    def test_corners_and_duplicates(self):
        self.check_partition([(0,0),(0,0),(100,0),(100,200),(100,200),(500,200)])

    def test_closed_circle(self):
        path=[(200+100*math.cos(i*math.tau/200),200+100*math.sin(i*math.tau/200)) for i in range(200)]
        self.check_partition(path+[path[0]])

    def test_one_chunk(self):
        self.assertEqual(len(self.check_partition([(0,0),(10,10)],.1)),1)

    def test_duration_compatible_with_native_helper(self):
        for duration in (.1,.2,.2001,.3,.65,.65001,2.5,10):
            for contact in (.2,.65,1):
                for chunk in motion_chunks([(0,0),(100,0)],duration,contact):
                    self.assertGreaterEqual(chunk['duration'],.1-1e-12)
                    self.assertLessEqual(chunk['duration'],contact+1e-12)

    def test_invalid(self):
        for duration in (True,0,31,float('nan'),float('inf'),'2'):
            with self.assertRaises(ValueError):motion_chunks([(0,0),(10,10)],duration)
        for path in ([],[(0,0)],[(0,0),(0,0)],[(True,0),(1,1)],[(0,0),(float('nan'),1)],[(0,0)]*3001):
            with self.assertRaises(ValueError):motion_chunks(path,2.5)
        with self.assertRaises(ValueError):motion_chunks([(0,0),(10,10)],30,.2)
        with self.assertRaises(ValueError):motion_chunks([(0,0),(10,10)],2.5,.1)


if __name__=='__main__':unittest.main()
