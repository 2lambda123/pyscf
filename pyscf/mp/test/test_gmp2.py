#!/usr/bin/env python
import unittest
from functools import reduce
import numpy
from pyscf import lib
from pyscf import gto
from pyscf import scf
from pyscf import ao2mo
from pyscf import mp

mol = gto.Mole()
mol.verbose = 7
mol.output = '/dev/null'
mol.atom = [
    [8 , (0. , 0.     , 0.)],
    [1 , (0. , -0.757 , 0.587)],
    [1 , (0. , 0.757  , 0.587)]]
mol.basis = '631g'
mol.spin = 2
mol.build()
mf = scf.UHF(mol)
mf.conv_tol = 1e-14
mf.scf()
gmf = scf.GHF(mol)
gmf.conv_tol = 1e-14
gmf.scf()


class KnownValues(unittest.TestCase):
    def test_gmp2(self):
        pt = mp.GMP2(gmf)
        emp2, t2 = pt.kernel()
        self.assertAlmostEqual(emp2, -0.12886859466191491, 9)

        pt.max_memory = 1
        pt.frozen = None
        emp2, t2 = pt.kernel()
        self.assertAlmostEqual(emp2, -0.12886859466191491, 9)

        mf1 = scf.addons.convert_to_ghf(mf)
        mf1.mo_coeff = numpy.asarray(mf1.mo_coeff)  # remove tag orbspin
        pt = mp.GMP2(mf1)
        emp2, t2 = pt.kernel()
        self.assertAlmostEqual(emp2, -0.09625784206542846, 9)

        pt.max_memory = 1
        pt.frozen = None
        emp2, t2 = pt.kernel()
        self.assertAlmostEqual(emp2, -0.09625784206542846, 9)

    def test_gmp2_contract_eri_dm(self):
        pt = mp.GMP2(mf)
        pt.frozen = 2
        emp2, t2 = pt.kernel()
        dm1 = pt.make_rdm1()
        dm2 = pt.make_rdm2()

        nao = mol.nao_nr()
        mo_a = pt._scf.mo_coeff[:nao]
        mo_b = pt._scf.mo_coeff[nao:]
        nmo = mo_a.shape[1]
        eri = ao2mo.kernel(mf._eri, mo_a+mo_b, compact=False).reshape([nmo]*4)
        orbspin = pt._scf.mo_coeff.orbspin
        sym_forbid = (orbspin[:,None] != orbspin)
        eri[sym_forbid,:,:] = 0
        eri[:,:,sym_forbid] = 0
        hcore = mf.get_hcore()
        h1 = reduce(numpy.dot, (mo_a.T.conj(), hcore, mo_a))
        h1+= reduce(numpy.dot, (mo_b.T.conj(), hcore, mo_b))

        e1 = numpy.einsum('ij,ji', h1, dm1)
        e1+= numpy.einsum('ijkl,jilk', eri, dm2) * .5
        e1+= mol.energy_nuc()
        self.assertAlmostEqual(e1, pt.e_tot, 9)

        pt = mp.GMP2(mf)
        emp2, t2 = pt.kernel()
        dm1 = pt.make_rdm1()
        dm2 = pt.make_rdm2()
        e1 = numpy.einsum('ij,ji', h1, dm1)
        e1+= numpy.einsum('ijkl,jilk', eri, dm2) * .5
        e1+= mol.energy_nuc()
        self.assertAlmostEqual(e1, pt.e_tot, 9)

        hcore = pt._scf.get_hcore()
        mo = pt._scf.mo_coeff
        vhf = pt._scf.get_veff(mol, pt._scf.make_rdm1())
        h1 = reduce(numpy.dot, (mo.T, hcore+vhf, mo))
        dm1[numpy.diag_indices(mol.nelectron)] -= 1
        e = numpy.einsum('pq,pq', h1, dm1)
        self.assertAlmostEqual(e, -emp2, 9)

    def test_gmp2_frozen(self):
        pt = mp.GMP2(gmf)
        pt.frozen = [2,3]
        pt.kernel(with_t2=False)
        self.assertAlmostEqual(pt.emp2, -0.087828433042835427, 9)

    def test_gmp2_outcore_frozen(self):
        pt = mp.GMP2(gmf)
        pt.max_memory = 0
        pt.nmo = 24
        pt.frozen = [8,9]
        e = pt.kernel(with_t2=False)[0]
        self.assertAlmostEqual(e, -0.098239933985213371, 9)

        pt = mp.GMP2(gmf)
        pt.nmo = 24
        pt.nocc = 8
        e = pt.kernel(with_t2=False)[0]
        self.assertAlmostEqual(e, -0.098239933985213371, 9)

    def test_gmp2_with_ao2mofn(self):
        pt = mp.GMP2(gmf)
        mf_df = mf.density_fit('weigend')
        ao2mofn = mf_df.with_df.ao2mo
        pt.ao2mo = lambda *args: mp.gmp2._make_eris_incore(pt, *args, ao2mofn=ao2mofn)
        e1 = pt.kernel()[0]
#        pt = mp.GMP2(gmf.density_fit('weigend'))
#        e2 = pt.kernel()[0]
#        self.assertAlmostEqual(e1, e2, 9)



if __name__ == "__main__":
    print("Full Tests for mp2")
    unittest.main()

