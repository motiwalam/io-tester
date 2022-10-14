import argparse
from functools import reduce
from dataclasses import dataclass
import subprocess
import sys
from more_itertools import with_iter
from multiprocessing import Pool

class Either:
    def __init__(self, lr, val):
        self.kind = lr
        self.value = val

    def bind(self, f):
        if self.kind == 'left':
            return self

        else:
            return f(self.value)

    def __repr__(self):
        return f'{self.kind.capitalize()}<{self.value}>'

    def __str__(self):
        return repr(self)

@dataclass
class Test:
    command: str
    input: str
    output: str

    append_input = lambda s: lambda t: Test(t.command, t.input + s, t.output)
    append_output = lambda s: lambda t: Test(t.command, t.input, t.output + s)
    
    @property
    def pretty(self):
        return (
            f'$ {self.command}\n'
            f'<<<\n'
            f'{self.input}'
            f'<<<\n'
            f'>>>\n'
            f'{self.output}'
            f'>>>\n'
        )

def Right(val): return Either('right', val)
def Left(val): return Either('left', val)

def update(d, k, v):
    c = d.copy()
    c[k] = v
    return c

def updatemany(d, *kfs): return reduce(lambda d, kf: update(d, *kf), kfs, d)

def modify(d, k, f): return update(d, k, f(d.get(k)))
def modifymany(d, *kfs): return reduce(lambda d, kf: modify(d, *kf), kfs, d)

def const(v): return lambda *args, **kwargs: v

def append(v): return lambda i: (*i, v)


def tests(lines):
    def reducer(prev, line):
        e = prev['expecting']
        l = line.strip()
        skip = not l or l.startswith('NB.')
        if e == 'command':
            if skip:
                return Right(prev)
            
            if l.startswith('$ '):
                return Right(modifymany(
                    prev,
                    ['current', const(Test(l.removeprefix('$ '), '', ''))],
                    ['expecting', const('start-input')]
                ))

            return Left(f'expected a line starting with $, or a comment. got {l}')

        elif e == 'start-input':
            if skip:
                return Right(prev)
            
            if l.startswith('<<<') and set(l) == {'<'}:
                return Right(modifymany(
                    prev,
                    ['expecting', const('end-input')],
                    ['length', const(len(l))]
                ))

            return Left(f'expected a line starting with at least <<<. got {l}')

        elif e == 'end-input':
            if l == '<' * prev['length']:
                return Right(modifymany(
                    prev,
                    ['expecting', const('start-output')]
                ))

            return Right(modifymany(
                prev,
                ['current', Test.append_input(line)]
            ))

        elif e == 'start-output':
            if skip:
                return Right(prev)

            if l.startswith('>>>') and set(l) == {'>'}:
                return Right(modifymany(
                    prev,
                    ['expecting', const('end-output')],
                    ['length', const(len(l))]
                ))
            
            return Left(f'expected a line starting with at least >>>. got {l}')
            

        elif e == 'end-output':
            if l == '>' * prev['length']:
                return Right(modifymany(
                    prev,
                    ['expecting', const('command')],
                    ['tests', append(prev['current'])]
                ))

            return Right(modifymany(
                prev,
                ['current', Test.append_output(line)]
            ))

        return Left(f'unknown expecting {e}')

    return reduce(
        lambda a, b: a.bind(lambda s: reducer(s, b)),
        lines,
        Either('right', {
            'expecting': 'command',
            'tests': [],
            'current': ()
        })
    )

def test(t):
    p = subprocess.run(t.command, shell=True, input=t.input.encode(), capture_output=True)
    if p.stdout == t.output.encode():
        return Right(t)
    
    else:
        return Left([t, p])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=str)
    parser.add_argument('-j', '--num-procs', type=int, default=50, help="number of processes to run the tests")
    args = parser.parse_args()

    file = args.file
    ts = tests(with_iter(open(file)))
    if ts.kind == 'left':
        raise Exception('blah', ts.value)

    numtotal = len(ts.value['tests'])
    numfailed = 0

    with Pool(args.num_procs) as p:
        results = p.imap_unordered(test, ts.value['tests'])
        for r in results:
            if r.kind == 'left':
                print('TEST FAILED')
                print(r.value[0].pretty)
                print('SCRIPT OUTPUTTED:')
                print(r.value[1].stdout.decode())

                numfailed += 1
            
            else:
                # print('TEST SUCCEEDED')
                # print(r.value.pretty)
                pass

    if numfailed == 0:
        print(f'ALL {numtotal} TESTS SUCCEEDED')

    else:
        print(f'FAILED {numfailed} TESTS OUT OF {numtotal}')    

if __name__ == '__main__':
    raise SystemExit(main())

