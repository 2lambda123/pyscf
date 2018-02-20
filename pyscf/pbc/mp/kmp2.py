#!/usr/bin/env python
# $Id$
# -*- coding: utf-8
#
# Author: Timothy Berkelbach <tim.berkelbach@gmail.com>
#


'''
kpoint-adapted and spin-adapted MP2
t2[i,j,a,b] = <ij|ab> / D_ij^ab

t2 and eris are never stored in full, only a partial 
eri of size (nkpts,nocc,nocc,nvir,nvir)
'''

import time
import numpy as np

from pyscf import lib
from pyscf.lib import logger
from pyscf.mp import mp2
from pyscf.pbc.lib import kpts_helper


def kernel(mp, mo_energy, mo_coeff, verbose=logger.NOTE):
    nocc = mp.nocc
    nvir = mp.nmo - nocc
    nkpts = mp.nkpts

    eia = np.zeros((nocc,nvir))
    eijab = np.zeros((nocc,nocc,nvir,nvir))

    fao2mo = mp._scf.with_df.ao2mo
    kconserv = mp.khelper.kconserv
    emp2 = 0.
    oovv_ij = np.zeros((nkpts,nocc,nocc,nvir,nvir), dtype=mo_coeff[0].dtype)
    for ki in range(nkpts):
      for kj in range(nkpts):
        for ka in range(nkpts):
            kb = kconserv[ki,ka,kj]
            orbo_i = mo_coeff[ki][:,:nocc]
            orbo_j = mo_coeff[kj][:,:nocc]
            orbv_a = mo_coeff[ka][:,nocc:]
            orbv_b = mo_coeff[kb][:,nocc:]
            oovv_ij[ka] = fao2mo((orbo_i,orbv_a,orbo_j,orbv_b),
                            (mp.kpts[ki],mp.kpts[ka],mp.kpts[kj],mp.kpts[kb]),
                            compact=False).reshape(nocc,nvir,nocc,nvir).transpose(0,2,1,3) / nkpts
        for ka in range(nkpts):
            kb = kconserv[ki,ka,kj]
            eia = mo_energy[ki][:nocc].reshape(-1,1) - mo_energy[ka][nocc:]
            ejb = mo_energy[kj][:nocc].reshape(-1,1) - mo_energy[kb][nocc:]
            eijab = lib.direct_sum('ia,jb->ijab',eia,ejb)
            t2_ijab = np.conj(oovv_ij[ka]/eijab)
            woovv = 2*oovv_ij[ka] - oovv_ij[kb].transpose(0,1,3,2)
            emp2 += np.einsum('ijab,ijab', t2_ijab, woovv).real

    emp2 /= nkpts

    return emp2, None


def get_frozen_mask(mp):
    moidx = [np.ones(x.size, dtype=np.bool) for x in mp.mo_occ]
    if isinstance(mp.frozen, (int, np.integer)):
        for idx in moidx:
            idx[:mp.frozen] = False
    elif isinstance(mp.frozen[0], (int, np.integer)):
        frozen = list(mp.frozen)
        for idx in moidx:
            idx[frozen] = False
    else:
        raise NotImplementedError
    return moidx


def get_nocc(mp):
    '''The number of occupied orbitals per k-point.'''
    if mp._nocc is not None:
        return mp._nocc
    elif isinstance(mp.frozen, (int, np.integer)):
        nocc = int(mp.mo_occ[0].sum()) // 2 - mp.frozen
    elif isinstance(mp.frozen[0], (int, np.integer)):
        occ_idx = mp.mo_occ[0] > 0
        occ_idx[list(mp.frozen)] = False
        nocc = np.count_nonzero(occ_idx)
    else:
        raise NotImplementedError
    return nocc

def get_nmo(mp):
    '''The number of molecular orbitals per k-point.'''
    if mp._nmo is not None:
        return mp._nmo
    if isinstance(mp.frozen, (int, np.integer)):
        nmo = len(mp.mo_occ[0]) - mp.frozen
    elif isinstance(mp.frozen[0], (int, np.integer)):
        nmo = len(mp.mo_occ[0]) - len(mp.frozen)
    else:
        raise NotImplementedError
    return nmo


class KMP2(mp2.MP2):
    def __init__(self, mf, frozen=0, mo_coeff=None, mo_occ=None):

        if mo_coeff  is None: mo_coeff  = mf.mo_coeff
        if mo_occ    is None: mo_occ    = mf.mo_occ

        self.mol = mf.mol
        self._scf = mf
        self.verbose = self.mol.verbose
        self.stdout = self.mol.stdout
        self.max_memory = mf.max_memory

        self.frozen = frozen

##################################################
# don't modify the following attributes, they are not input options
        self.kpts = mf.kpts
        self.mo_energy = mf.mo_energy
        self.nkpts = len(self.kpts)
        self.khelper = kpts_helper.KptsHelper(mf.cell, mf.kpts)
        self.mo_energy = mf.mo_energy
        self.mo_coeff = mo_coeff
        self.mo_occ = mo_occ
        self._nocc = None
        self._nmo = None
        self.e_corr = None
        self.t2 = None
        self._keys = set(self.__dict__.keys())

    get_nocc = get_nocc
    get_nmo = get_nmo
    get_frozen_mask = get_frozen_mask

    def kernel(self, mo_energy=None, mo_coeff=None):
        if mo_energy is None:
            mo_energy = self.mo_energy
        if mo_coeff is None:
            mo_coeff = self.mo_coeff
        if mo_energy is None or mo_coeff is None:
            log = logger.Logger(self.stdout, self.verbose)
            log.warn('mo_coeff, mo_energy are not given.\n'
                     'You may need to call mf.kernel() to generate them.')
            raise RuntimeError

        self.e_corr, self.t2 = \
                kernel(self, mo_energy, mo_coeff, verbose=self.verbose)
        logger.log(self, 'KMP2 energy = %.15g', self.e_corr)
        return self.e_corr, self.t2
KRMP2 = KMP2


if __name__ == '__main__':
    from pyscf.pbc import gto, scf, mp 

    cell = gto.Cell()
    cell.atom='''
    C 0.000000000000   0.000000000000   0.000000000000
    C 1.685068664391   1.685068664391   1.685068664391
    '''
    cell.basis = 'gth-szv'
    cell.pseudo = 'gth-pade'
    cell.a = '''
    0.000000000, 3.370137329, 3.370137329
    3.370137329, 0.000000000, 3.370137329
    3.370137329, 3.370137329, 0.000000000'''
    cell.unit = 'B'
    cell.verbose = 5
    cell.build()

    # Running HF and MP2 with 1x1x2 Monkhorst-Pack k-point mesh
    kmf = scf.KRHF(cell, kpts=cell.make_kpts([1,1,2]), exxdiv=None)
    ehf = kmf.kernel()

    mymp = mp.KMP2(kmf)
    emp2, t2 = mymp.kernel()
    print(emp2 - -0.204721432828996)

