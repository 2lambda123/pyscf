'''
Interface to geometry optimizer pyberny https://github.com/azag0/pyberny
(In testing)
'''
from __future__ import absolute_import
try:
    from berny import Berny, geomlib, Logger, optimize as optimize_berny
except ImportError:
    raise ImportError('Geometry optimizer pyberny not found.\npyberny library '
                      'can be found on github https://github.com/azag0/pyberny')

import copy
import numpy
from pyscf import lib
from pyscf.geomopt.grad import gen_grad_scanner

def to_berny_geom(mol, include_ghost=True):
    atom_charges = mol.atom_charges()
    if include_ghost:
        species = [mol.atom_symbol(i) if z != 0 else 'Ghost'
                   for i,z in enumerate(atom_charges)]
        coords = mol.atom_coords() * lib.param.BOHR
    else:
        atmlst = numpy.where(atom_charges != 0)[0]  # Exclude ghost atoms
        species = [mol.atom_symbol(i) for i in atmlst]
        coords = mol.atom_coords()[atmlst] * lib.param.BOHR
    return geomlib.Molecule(species, coords)

def _geom_to_atom(mol, geom, include_ghost):
    atoms = list(geom)
    atmlst = numpy.where(mol.atom_charges() != 0)[0]
    atom_charges = mol.atom_charges() * lib.param.BOHR
    atom_coords = mol.atom_coords()

    mol_atom = []
    for k, i in enumerate(atmlst):
        if atom_charges[i] == 0:
            mol_atom.append((mol.atom_symbol(i), atom_coords[i]))
        else:
            if include_ghost:
                mol_atom.append(atoms[i])
            else:
                mol_atom.append(atoms[k])
    return mol_atom

def to_berny_log(pyscf_log):
    class BernyLogger(Logger):
        def __call__(self, msg, level=0):
            if level >= -self.verbosity:
                pyscf_log.info('%d %s', self.n, msg)
    return BernyLogger()

def as_berny_solver(method, assert_convergence=True, include_ghost=True):
    '''Generate a solver for berny optimize function.
    '''
    mol = copy.copy(method.mol)
    g_scanner = gen_grad_scanner(method)
    if not include_ghost:
        g_scanner.atmlst = numpy.where(mol.atom_charges() != 0)[0]

    geom = yield
    while True:
        mol.set_geom_(_geom_to_atom(mol, geom, include_ghost))
        energy, gradients = g_scanner(mol)
        if assert_convergence and not g_scanner.converged:
            raise RuntimeError('Nuclear gradients of %s not converged' % method)

        geom = yield energy, gradients


def optimize(method, assert_convergence=True, include_ghost=True, **kwargs):
    '''Optimize the geometry with the given method.
    '''
    mol = copy.copy(method.mol)
    if 'log' in kwargs:
        log = lib.logger.new_logger(method, kwargs['log'])
    elif 'verbose' in kwargs:
        log = lib.logger.new_logger(method, kwargs['verbose'])
    else:
        log = lib.logger.new_logger(method)
#    geom = optimize_berny(as_berny_solver(method), to_berny_geom(mol),
#                          log=to_berny_log(log), **kwargs)
# temporary interface, taken from berny.py optimize function
    log = to_berny_log(log)
    solver = as_berny_solver(method, assert_convergence, include_ghost)
    geom = to_berny_geom(mol, include_ghost)
    next(solver)
    optimizer = Berny(geom, log=log, **kwargs)
    for geom in optimizer:
        energy, gradients = solver.send(geom)
        optimizer.send((energy, gradients))
    mol.set_geom_(_geom_to_atom(mol, geom, include_ghost))
    return mol
kernel = optimize


if __name__ == '__main__':
    from pyscf import gto
    from pyscf import scf, dft, cc, mp
    mol = gto.M(atom='''
C       1.1879  -0.3829 0.0000
C       0.0000  0.5526  0.0000
O       -1.1867 -0.2472 0.0000
H       -1.9237 0.3850  0.0000
H       2.0985  0.2306  0.0000
H       1.1184  -1.0093 0.8869
H       1.1184  -1.0093 -0.8869
H       -0.0227 1.1812  0.8852
H       -0.0227 1.1812  -0.8852
                ''',
                basis='3-21g')

    mf = scf.RHF(mol)
    mol1 = optimize(mf)
    print(mf.kernel() - -153.219208484874)
    print(scf.RHF(mol1).kernel() - -153.222680852335)

    mf = dft.RKS(mol)
    mf.xc = 'pbe'
    mf.conv_tol = 1e-7
    mol1 = optimize(mf)

    mymp2 = mp.MP2(scf.RHF(mol))
    mol1 = optimize(mymp2)

    mycc = cc.CCSD(scf.RHF(mol))
    mol1 = optimize(mycc)

