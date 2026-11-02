"""Validate emitted arrow ink, not invisible tangent construction points."""
import math
import unittest

from notebook_procedural import _route_commands, _poly
from notebook_lesson import _primitive


class RouteGeometryTest(unittest.TestCase):
    def test_virtual_tangent_may_leave_page_when_actual_head_fits(self):
        for points in (
                [(50,12),(50,14)],[(12,50),(14,50)],
                [(588,50),(586,50)],[(50,348),(50,346)]):
            with self.subTest(points=points):
                a,b=points;length=math.dist(a,b)
                back=[b[k]+(a[k]-b[k])*30/length for k in (0,1)]
                with self.assertRaises(ValueError):
                    _primitive(dict(op='arrow',**{'from':back,'to':b}))
                commands=_route_commands(points)
                self.assertEqual(commands[0],_poly(points))
                self.assertEqual(len(commands),2)
                for command in commands:
                    for path in _primitive(command):
                        self.assertTrue(all(0<=x<=600 and 0<=y<=360 for x,y in path))

    def test_existing_interior_heads_are_exactly_unchanged(self):
        for index in range(72):
            angle=index*math.tau/72
            endpoint=(300,180)
            previous=(300-3*math.cos(angle),180-3*math.sin(angle))
            points=[(250,160),previous,endpoint]
            length=math.dist(previous,endpoint)
            back=[endpoint[k]+(previous[k]-endpoint[k])*30/length for k in (0,1)]
            expected=[_poly(points)]+[_poly(p) for p in _primitive(
                dict(op='arrow',**{'from':back,'to':list(endpoint)}))[1:]]
            self.assertEqual(_route_commands(points),expected)

    def test_real_out_of_bounds_ink_is_still_rejected(self):
        for points in (
                [(5,5),(6,5)],[(595,355),(594,355)],
                [(-1,100),(50,100)],[(50,100),(601,100)]):
            with self.subTest(points=points):
                with self.assertRaises(ValueError):_route_commands(points)


if __name__=='__main__':unittest.main()
