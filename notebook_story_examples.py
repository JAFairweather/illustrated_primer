"""Authored contract fixtures, never evidence of model-generated explanations."""


def story_examples():
    odd = dict(v=1, mode='story', audience='A curious twelve-year-old', template='explain_result',
               question='Why does adding consecutive odd numbers make a square?',
               acts=[
                   dict(id='notice', beat='Small square pictures suggest a pattern.'),
                   dict(id='mechanism', beat='An L-shaped border grows any square by one side unit.'),
                   dict(id='generalize', beat='Every border is odd, so the pattern continues.'),
                   dict(id='distinguish', beat='The border argument explains all sizes, unlike examples alone.')],
               panels=[],
               takeaway='Each new border adds 2k minus 1 tiles to the previous square. '
                        'Starting with one tile, the first n odd borders therefore make n squared tiles.')
    rows = [
        ('one', 'notice', 'Start with one', 'What is the smallest square?',
         'A single tile is a one-by-one square.', 'One tile makes the first square.', None),
        ('two', 'notice', 'Add an L', 'How can we grow the square?',
         'Three additional tiles complete a two-by-two square.', 'Three new tiles complete a square with two-tile sides.', 'one'),
        ('three', 'notice', 'Try the next border', 'How many more tiles make three-tile sides?',
         'Five additional tiles extend the square on two sides.', 'Five more tiles make the next square.', 'two'),
        ('general', 'mechanism', 'Look at any size', 'Can one picture explain every size?',
         'A schematic k-by-k square contains a previous square and one L-shaped border.',
         'Imagine a square whose sides each contain k tiles.', None),
        ('across', 'mechanism', 'Count one arm', 'How many tiles lie across the new top?',
         'The top arm of the new border has k tiles, including the corner.',
         'The top arm has k tiles, including the corner.', 'general'),
        ('down', 'mechanism', 'Count the other arm', 'Should the corner be counted again?',
         'The remaining side of the border has k minus 1 tiles.',
         'The side adds k minus one; count the corner once.', 'across'),
        ('odd', 'generalize', 'The border is odd', 'What is the total border size?',
         'The two arms total k plus k minus 1, which is 2k minus 1.',
         'Together, the arms contain twice k minus one tiles.', 'down'),
        ('grow', 'generalize', 'Repeat the growth', 'Why does the reasoning continue at larger sizes?',
         'The same border construction works whenever the side grows by one tile.',
         'The same construction works for every larger square.', 'odd'),
        ('examples', 'distinguish', 'Return to our small square', 'What did the first examples show?',
         'The earlier three-by-three square illustrates the rule without proving all cases.',
         'Our small squares illustrate the pattern, but do not prove it.', 'three'),
        ('argument', 'distinguish', 'Return to the general border', 'What makes this an explanation for every size?',
         'The general L-shaped border argument covers arbitrary positive integer side lengths.',
         'The general border argument explains every positive integer size.', 'grow'),
    ]
    for identity, act, title, question, idea, caption, base in rows:
        odd['panels'].append(dict(id=identity, act=act, title=title, question=question,
                                 new_idea=idea, visual_kind='geometric', caption=caption, base=base))
    return {'odd-borders': odd}
