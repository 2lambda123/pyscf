#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

import os
from pyscf.data.nist import LIGHT_SPEED, BOHR

L_MAX      = 8
MAX_MEMORY = int(os.environ.get('PYSCF_MAX_MEMORY', 4000)) # MB
TMPDIR = os.environ.get('TMPDIR', '.')
TMPDIR = os.environ.get('PYSCF_TMPDIR', TMPDIR)

BOHR = float(os.environ.get('PYSCF_BOHR', BOHR))
LIGHT_SPEED = float(os.environ.get('PYSCF_LIGHT_SPEED', LIGHT_SPEED))
OUTPUT_DIGITS = int(os.environ.get('PYSCF_OUTPUT_DIGITS', 5))
OUTPUT_COLS   = int(os.environ.get('PYSCF_OUTPUT_COLS', 5))

ANGULAR = 'spdfghik'
ANGULARMAP = {'s': 0,
              'p': 1,
              'd': 2,
              'f': 3,
              'g': 4,
              'h': 5,
              'i': 6,
              'k': 7}

REAL_SPHERIC = (
    ('',), \
    ('x', 'y', 'z'), \
    ('xy', 'yz', 'z^2', 'xz', 'x2-y2',), \
    ('y^3', 'xyz', 'yz^2', 'z^3', 'xz^2', 'zx^2', 'x^3'), \
    ('-4', '-3', '-2', '-1', ' 0', ' 1', ' 2', ' 3', ' 4'),
    ('-5', '-4', '-3', '-2', '-1', ' 0', ' 1', ' 2', ' 3', ' 4', ' 5'),
    ('-6', '-5', '-4', '-3', '-2', '-1', ' 0', ' 1', ' 2', ' 3', ' 4', ' 5',' 6'),
)

ELEMENTS = ('GHOST',
    'H' , 'He', 'Li', 'Be', 'B' , 'C' , 'N' , 'O' , 'F' , 'Ne',
    'Na', 'Mg', 'Al', 'Si', 'P' , 'S' , 'Cl', 'Ar', 'K' , 'Ca',
    'Sc', 'Ti', 'V' , 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
    'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr', 'Rb', 'Sr', 'Y' , 'Zr',
    'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn',
    'Sb', 'Te', 'I' , 'Xe', 'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd',
    'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb',
    'Lu', 'Hf', 'Ta', 'W' , 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
    'Tl', 'Pb', 'Bi', 'Po', 'At', 'Rn', 'Fr', 'Ra', 'Ac', 'Th',
    'Pa', 'U' , 'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm',
    'Md', 'No', 'Lr', 'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds',
    'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og',
)
ELEMENTS_PROTON = NUC = dict([(x,i) for i,x in enumerate(ELEMENTS)])

VERBOSE_DEBUG  = 5
VERBOSE_INFO   = 4
VERBOSE_NOTICE = 3
VERBOSE_WARN   = 2
VERBOSE_ERR    = 1
VERBOSE_QUIET  = 0
VERBOSE_CRIT   = -1
VERBOSE_ALERT  = -2
VERBOSE_PANIC  = -3
TIMER_LEVEL    = VERBOSE_DEBUG

