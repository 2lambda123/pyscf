#!/usr/bin/env python
import unittest
import numpy
from pyscf import gto, scf, lib, symm
from pyscf import cc
from pyscf.cc import ccsd_t

mol = gto.Mole()
mol.atom = [
    [8 , (0. , 0.     , 0.)],
    [1 , (0. , -.757 , .587)],
    [1 , (0. ,  .757 , .587)]]
mol.symmetry = True
mol.verbose = 7
mol.output = '/dev/null'
mol.basis = 'ccpvdz'
mol.build()
rhf = scf.RHF(mol)
rhf.conv_tol = 1e-14
rhf.scf()

mcc = cc.CCSD(rhf)
mcc.conv_tol = 1e-14
mcc.ccsd()

class KnownValues(unittest.TestCase):
    def test_ccsd_t(self):
        mol = gto.M()
        numpy.random.seed(12)
        nocc, nvir = 5, 12
        eris = cc.ccsd._ChemistsERIs()
        eris.ovvv = numpy.random.random((nocc,nvir,nvir*(nvir+1)//2)) * .1
        eris.ovoo = numpy.random.random((nocc,nvir,nocc,nocc)) * .1
        eris.ovvo = numpy.random.random((nocc,nvir,nvir,nocc)) * .1
        t1 = numpy.random.random((nocc,nvir)) * .1
        t2 = numpy.random.random((nocc,nocc,nvir,nvir)) * .1
        t2 = t2 + t2.transpose(1,0,3,2)
        mf = scf.RHF(mol)
        mycc = cc.CCSD(mf)
        mycc.mo_energy = mycc._scf.mo_energy = numpy.arange(0., nocc+nvir)
        eris.fock = numpy.diag(mycc.mo_energy)
        e = ccsd_t.kernel(mycc, eris, t1, t2)
        self.assertAlmostEqual(e, -8.501010390740708, 9)

    def test_ccsd_t_symm(self):
        e3a = ccsd_t.kernel(mcc, mcc.ao2mo())
        self.assertAlmostEqual(e3a, -0.003060022611584471, 9)

        mcc.mol.symmetry = False
        e3a = ccsd_t.kernel(mcc, mcc.ao2mo())
        self.assertAlmostEqual(e3a, -0.003060022611584471, 9)
        mcc.mol.symmetry = True

    def test_sort_eri(self):
        eris = mcc.ao2mo()
        nocc, nvir = mcc.t1.shape
        nmo = nocc + nvir
        vvop = numpy.empty((nvir,nvir,nocc,nmo))
        log = lib.logger.Logger(mcc.stdout, mcc.verbose)
        orbsym = ccsd_t._sort_eri(mcc, eris, nocc, nvir, vvop, log)

        o_sorted = numpy.hstack([numpy.where(orbsym[:nocc] == i)[0] for i in range(8)])
        v_sorted = numpy.hstack([numpy.where(orbsym[nocc:] == i)[0] for i in range(8)])
        eris_vvop = numpy.empty((nvir,nvir,nocc,nmo))
        eris_voov = numpy.asarray(eris.ovvo).transpose(1,0,3,2)
        eris_voov = eris_voov[v_sorted][:,o_sorted][:,:,o_sorted][:,:,:,v_sorted]
        eris_vvop[:,:,:,:nocc] = eris_voov.transpose(0,3,1,2)
        eris_vovv = lib.unpack_tril(numpy.asarray(eris.ovvv).transpose(1,0,2).reshape(nocc*nvir,-1))
        eris_vovv = eris_vovv.reshape(nvir,nocc,nvir,nvir)
        eris_vovv = eris_vovv[v_sorted][:,o_sorted][:,:,v_sorted][:,:,:,v_sorted]
        eris_vvop[:,:,:,nocc:] = eris_vovv.transpose(0,2,1,3)
        self.assertAlmostEqual(abs(eris_vvop-vvop).max(), 0, 9)

    def test_sort_t2_vooo(self):
        t1 = mcc.t1
        t2 = mcc.t2
        eris = mcc.ao2mo()
        nocc, nvir = t1.shape
        nmo = nocc + nvir
        mol = mcc.mol
        orbsym = symm.addons.label_orb_symm(mol, mol.irrep_id, mol.symm_orb,
                                            mcc.mo_coeff)
        orbsym = numpy.asarray(orbsym, dtype=numpy.int32)
        mo_energy, t1T, t2T, vooo, foVT = \
                ccsd_t._sort_t2_vooo_(mcc, orbsym, t1, t2.copy(), eris)

        o_sorted = numpy.hstack([numpy.where(orbsym[:nocc] == i)[0] for i in range(8)])
        v_sorted = numpy.hstack([numpy.where(orbsym[nocc:] == i)[0] for i in range(8)])
        o_sym = orbsym[o_sorted]
        oo_sym = (o_sym[:,None] ^ o_sym).ravel()
        oo_sorted = numpy.hstack([numpy.where(oo_sym == i)[0] for i in range(8)])

        ref_t2T = t2.transpose(2,3,1,0)
        ref_t2T = ref_t2T[v_sorted][:,v_sorted][:,:,o_sorted][:,:,:,o_sorted]
        ref_t2T = ref_t2T.reshape(nvir,nvir,-1)[:,:,oo_sorted].reshape(nvir,nvir,nocc,nocc)
        ref_vooo = numpy.asarray(eris.ovoo).transpose(1,0,2,3)
        ref_vooo = ref_vooo[v_sorted][:,o_sorted][:,:,o_sorted][:,:,:,o_sorted]
        ref_vooo = ref_vooo.reshape(nvir,-1,nocc)[:,oo_sorted].reshape(nvir,nocc,nocc,nocc)

        self.assertAlmostEqual(abs(ref_vooo-vooo).sum(), 0, 9)
        self.assertAlmostEqual(abs(ref_t2T-t2T).sum(), 0, 9)


if __name__ == "__main__":
    print("Full Tests for CCSD(T)")
    unittest.main()

