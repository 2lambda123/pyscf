#!/usr/bin/env python
import unittest
from pyscf import gto, lib
from pyscf import scf, dft
from pyscf import ci
from pyscf.ci import cisd_grad
from pyscf import grad

mol = gto.Mole()
mol.verbose = 7
mol.output = '/dev/null'
mol.atom = [
    [8 , (0. , 0.     , 0.)],
    [1 , (0. , -0.757 , 0.587)],
    [1 , (0. , 0.757  , 0.587)]]

mol.basis = '631g'
mol.build()
mf = scf.RHF(mol)
mf.conv_tol_grad = 1e-8
mf.kernel()


class KnownValues(unittest.TestCase):
    def test_cisd_grad(self):
        myci = ci.cisd.CISD(mf)
        myci.conv_tol = 1e-10
        myci.kernel()
        g1 = myci.nuc_grad_method().kernel(myci.ci, mf_grad=grad.RHF(mf), atmlst=[0,1,2])
        self.assertAlmostEqual(lib.finger(g1), -0.032562347119070523, 7)

    def test_cisd_grad_finite_diff(self):
        mol = gto.M(
            verbose = 0,
            atom = 'H 0 0 0; H 0 0 1.706',
            basis = '631g',
            unit='Bohr')
        ci_scanner = scf.RHF(mol).set(conv_tol=1e-14).apply(ci.CISD).as_scanner()
        e0 = ci_scanner(mol)
        mol = gto.M(
            verbose = 0,
            atom = 'H 0 0 0; H 0 0 1.704',
            basis = '631g',
            unit='Bohr')
        e1 = ci_scanner(mol)
        mol = gto.M(
            verbose = 0,
            atom = 'H 0 0 0; H 0 0 1.705',
            basis = '631g',
            unit='Bohr')
        ci_scanner(mol)
        g1 = ci_scanner.nuc_grad_method().kernel()
        self.assertAlmostEqual(g1[0,2], (e1-e0)*500, 6)

    def test_frozen(self):
        myci = ci.cisd.CISD(mf)
        myci.frozen = [0,1,10,11,12]
        myci.max_memory = 1
        myci.kernel()
        g1 = cisd_grad.kernel(myci, myci.ci, mf_grad=grad.RHF(mf))
        self.assertAlmostEqual(lib.finger(g1), 0.10224149952700579, 6)

    def test_as_scanner(self):
        myci = ci.cisd.CISD(mf)
        myci.frozen = [0,1,10,11,12]
        gscan = myci.nuc_grad_method().as_scanner()
        e, g1 = gscan(mol)
        self.assertTrue(gscan.converged)
        self.assertAlmostEqual(e, -76.032220245016717, 9)
        self.assertAlmostEqual(lib.finger(g1), 0.10224149952700579, 6)


if __name__ == "__main__":
    print("Tests for CISD gradients")
    unittest.main()

