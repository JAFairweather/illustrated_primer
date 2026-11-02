from copy import deepcopy
from itertools import combinations, product
import random
import unittest

from notebook_label_solver import select_labels, LabelSearchBudgetExceeded
from notebook_procedural import _place_labels


class LabelSolverTests(unittest.TestCase):
    def test_empty_unsatisfiable_and_complete_results(self):
        self.assertEqual(select_labels({},lambda a,b:False),{})
        self.assertIsNone(select_labels({'a':[]},lambda a,b:False))
        self.assertIsNone(select_labels({'a':[1],'b':[2]},lambda a,b:True))
        self.assertEqual(select_labels({'a':[1],'b':[2]},lambda a,b:False),{'a':1,'b':2})

    def test_reselects_most_constrained_label_after_each_choice(self):
        # A has two options initially. Once A=0 is selected, C has only one
        # legal location; choosing C next avoids B stealing that location.
        options={'a':[('a',0),('a',1)],
                 'b':[('b',0),('b',1),('b',2)],
                 'c':[('c',0),('c',1),('c',2),('c',3)]}
        def conflict(a,b):
            pair={a,b}
            return any(pair=={('a',0),('c',n)} for n in (1,2,3)) or pair=={('b',0),('c',0)}
        original=deepcopy(options)
        chosen=select_labels(options,conflict)
        self.assertEqual(list(chosen),['a','c','b'])
        self.assertEqual(chosen,{'a':('a',0),'c':('c',0),'b':('b',1)})
        self.assertEqual(options,original)
        self.assertEqual(chosen,select_labels(options,conflict))

    def test_checks_against_exhaustive_small_assignments(self):
        rng=random.Random(1701)
        for case in range(160):
            options={str(i):[(i,j) for j in range(rng.randint(1,4))]
                     for i in range(rng.randint(2,5))}
            conflicts=set()
            for a,b in combinations(options,2):
                for left,right in product(options[a],options[b]):
                    if rng.random()<.4:conflicts.add(frozenset((left,right)))
            incompatible=lambda a,b:frozenset((a,b)) in conflicts
            solutions=[candidate for candidate in product(*options.values())
                       if all(not incompatible(a,b) for a,b in combinations(candidate,2))]
            chosen=select_labels(options,incompatible)
            with self.subTest(case=case):
                self.assertEqual(chosen is not None,bool(solutions))
                if chosen is not None:
                    self.assertEqual(set(chosen),set(options))
                    self.assertIn(tuple(chosen[key] for key in options),solutions)

    def test_pruning_work_is_charged_and_no_partial_result_escapes(self):
        calls=[]
        options={'a':[object()],'b':[object() for _ in range(100)]}
        before=list(options['b'])
        with self.assertRaises(LabelSearchBudgetExceeded):
            select_labels(options,lambda a,b:calls.append((a,b)) or False,work_limit=8)
        self.assertEqual(len(calls),7)  # One choice plus seven pair checks.
        self.assertEqual(options['b'],before)

    def test_pair_cache_is_symmetric_and_accepts_unhashable_candidates(self):
        options={'a':[[0],[1]],'b':[[0],[1]],'c':[[0],[1]]}
        calls=[]
        def conflicts(a,b):
            pair=tuple(sorted((id(a),id(b))))
            self.assertNotIn(pair,calls)
            calls.append(pair)
            return a==b
        self.assertIsNone(select_labels(options,conflicts))

    def test_budget_validation_and_choice_charge(self):
        for bad in (0,-1,True,2.5):
            with self.assertRaises(ValueError):select_labels({},lambda a,b:False,work_limit=bad)
        option=object()
        self.assertIs(select_labels({'a':[option]},lambda a,b:False,work_limit=1)['a'],option)

    def test_duplicate_geometric_candidates_do_not_consume_search_budget(self):
        choices=[(100,60)]*5000+[(300,60)]*5000
        expected=_place_labels([('a','A',[(100,60),(300,60)]),('b','B',[(100,60)])],[])
        self.assertEqual(_place_labels([('a','A',choices),('b','B',[(100,60)])],[]),expected)

    def test_same_text_box_with_different_pointers_is_not_deduplicated(self):
        blocked=[dict(op='line',**{'from':[140,140],'to':[350,140]})]
        clear=[dict(op='line',**{'from':[140,200],'to':[350,200]})]
        alternatives=iter((blocked,clear))
        placed,_=_place_labels([('a','A',[(100,60),(100,60)]),('b','B',[(300,150)])],[],
                               attachments={'a':lambda box:next(alternatives)})
        self.assertEqual(placed['a'][0],clear[0])

    def test_fallback_is_not_searched_when_primary_placement_exists(self):
        a,b,c=object(),object(),object();calls=[]
        selected=select_labels({'a':[a],'b':[b]},
            lambda x,y:calls.append((x,y)) or False,fallback_options={'a':[c]})
        self.assertEqual(selected,{'a':a,'b':b})
        self.assertEqual(calls,[(a,b)])

    def test_fallback_shares_the_original_work_budget_and_pair_cache(self):
        a0,a1,b0=('a',0),('a',1),('b',0)
        options={'a':[a0],'b':[b0]};extra={'a':[a1]}
        conflict=lambda a,b:a[1]==b[1]
        # Primary unsatisfiable: 2 work units. Expanded pass: one choice,
        # one NEW comparison (the old one is cached), one final choice.
        with self.assertRaises(LabelSearchBudgetExceeded):
            select_labels(options,conflict,work_limit=4,fallback_options=extra)
        self.assertEqual(select_labels(options,conflict,work_limit=5,fallback_options=extra),
                         {'b':b0,'a':a1})

    def test_fallback_can_supply_an_empty_domain_but_never_a_partial_assignment(self):
        self.assertEqual(select_labels({'a':[],'b':[2]},lambda a,b:False,
                                       fallback_options={'a':[1]}),{'a':1,'b':2})
        self.assertIsNone(select_labels({'a':[],'b':[]},lambda a,b:False,
                                        fallback_options={'a':[1]}))

    def test_fallback_positions_still_obey_geometry_clearance(self):
        def candidates(box):return [(100,60)]
        candidates.fallback=lambda box:[(300,60)]
        wall=[dict(op='line',**{'from':[100,30],'to':[100,80]})]
        placed,_=_place_labels([('a','A',candidates)],wall)
        self.assertGreater(placed['a'][0]['at'][0],200)

    def test_impossible_cluster_does_not_enumerate_unrelated_labels(self):
        # Three mutually touching labels cannot share two positions. Six
        # unrelated labels precede them in the deterministic search order.
        # Their choices cannot repair the impossible cluster.
        options={f'free-{i}':[(f'free-{i}',j) for j in range(2)] for i in range(6)}
        options.update({key:[(key,j) for j in (0,1,1)] for key in ('a','b','c')})
        calls=[]
        def conflict(a,b):
            calls.append((a,b))
            return a[0] in 'abc' and b[0] in 'abc' and a[1]==b[1]
        self.assertIsNone(select_labels(options,conflict,work_limit=256))
        self.assertLess(len(calls),200)

    def test_backtracking_revisits_the_choice_that_removed_needed_positions(self):
        options={'gate':[('gate',0),('gate',1)],
                 'free':[('free',0),('free',1)]}
        options.update({key:[(key,j) for j in range(3)] for key in ('a','b','c')})
        def conflict(a,b):
            if a[0]=='gate':return a[1]==0 and b[0] in 'abc' and b[1]==2
            if b[0]=='gate':return conflict(b,a)
            return a[0] in 'abc' and b[0] in 'abc' and a[1]==b[1]
        selected=select_labels(options,conflict,work_limit=256)
        self.assertEqual(selected['gate'],('gate',1))
        self.assertEqual({selected[k][1] for k in ('a','b','c')},{0,1,2})
        self.assertTrue(all(not conflict(a,b) for a,b in combinations(selected.values(),2)))

    def test_failed_primary_causes_do_not_poison_expanded_domains(self):
        options={key:[(key,j) for j in range(2)] for key in ('a','b','c')}
        conflict=lambda a,b:a[1]==b[1]
        selected=select_labels(options,conflict,fallback_options={'c':[('c',2)]})
        self.assertEqual(selected['c'],('c',2))
        self.assertEqual({v[1] for v in selected.values()},{0,1,2})

    def test_fallback_search_matches_exhaustive_small_problems(self):
        rng=random.Random(6168)
        for case in range(200):
            keys=[str(i) for i in range(rng.randint(2,5))]
            options={k:[(k,j) for j in range(rng.randint(0,3))] for k in keys}
            extra={k:[(k,j+3) for j in range(rng.randint(0,2))] for k in keys}
            expanded={k:options[k]+extra[k] for k in keys}
            conflicts=set()
            for a,b in combinations(keys,2):
                for left,right in product(expanded[a],expanded[b]):
                    if rng.random()<.5:conflicts.add(frozenset((left,right)))
            incompatible=lambda a,b:frozenset((a,b)) in conflicts
            solutions=[candidate for candidate in product(*expanded.values())
                       if all(not incompatible(a,b) for a,b in combinations(candidate,2))]
            chosen=select_labels(options,incompatible,fallback_options=extra)
            with self.subTest(case=case):
                self.assertEqual(chosen is not None,bool(solutions))
                if chosen is not None:
                    self.assertIn(tuple(chosen[k] for k in keys),solutions)


if __name__=='__main__':unittest.main()
