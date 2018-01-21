#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
General spin-orbital CISD
'''

import time
from functools import reduce
import numpy
from pyscf import lib
from pyscf.lib import logger
from pyscf.cc import ccsd
from pyscf.cc import gccsd
from pyscf.cc import gccsd_rdm
from pyscf.cc.addons import spatial2spin, spin2spatial
from pyscf.ci import cisd
from pyscf import fci
from pyscf.fci import cistring


def make_diagonal(myci, eris):
    nocc = myci.nocc
    nmo = myci.nmo
    nvir = nmo - nocc
    jkdiag = numpy.zeros((nmo,nmo))
    jkdiag[:nocc,:nocc] = numpy.einsum('ijij->ij', eris.oooo)
    jkdiag[nocc:,nocc:] = numpy.einsum('ijij->ij', eris.vvvv)
    jkdiag[:nocc,nocc:] = numpy.einsum('ijij->ij', eris.ovov)
    jksum = jkdiag[:nocc,:nocc].sum()
    mo_energy = eris.fock.diagonal()
    ehf = mo_energy[:nocc].sum() - jksum * .5
    e1diag = numpy.empty((nocc,nvir))
    e2diag = numpy.empty((nocc,nocc,nvir,nvir))
    for i in range(nocc):
        for a in range(nocc, nmo):
            e1diag[i,a-nocc] = ehf - mo_energy[i] + mo_energy[a] - jkdiag[i,a]
            for j in range(nocc):
                for b in range(nocc, nmo):
                    e2diag[i,j,a-nocc,b-nocc] = ehf \
                            - mo_energy[i] - mo_energy[j] \
                            + mo_energy[a] + mo_energy[b] \
                            + jkdiag[i,j] + jkdiag[a,b] \
                            - jkdiag[i,a] - jkdiag[j,a] \
                            - jkdiag[i,b] - jkdiag[j,b]
    return amplitudes_to_cisdvec(ehf, e1diag, e2diag)

def contract(myci, civec, eris):
    nocc = myci.nocc
    nmo = myci.nmo

    c0, c1, c2 = cisdvec_to_amplitudes(civec, nmo, nocc)
    c2 = c2

    fock = eris.fock
    fov = fock[:nocc,nocc:]
    foo = fock[:nocc,:nocc]
    fvv = fock[nocc:,nocc:]

    t1  = lib.einsum('ie,ae->ia', c1, fvv)
    t1 -= lib.einsum('ma,mi->ia', c1, foo)
    t1 += lib.einsum('imae,me->ia', c2, fov)
    #:t1 -= lib.einsum('nf,naif->ia', c1, eris.ovov)
    t1 += lib.einsum('nf,nafi->ia', c1, eris.ovvo)
    t1 -= 0.5*lib.einsum('imef,maef->ia', c2, eris.ovvv)
    t1 -= 0.5*lib.einsum('mnae,mnie->ia', c2, eris.ooov)

    tmp = lib.einsum('ijae,be->ijab', c2, fvv)
    t2  = tmp - tmp.transpose(0,1,3,2)
    tmp = lib.einsum('imab,mj->ijab', c2, foo)
    t2 -= tmp - tmp.transpose(1,0,2,3)
    t2 += 0.5*lib.einsum('mnab,mnij->ijab', c2, eris.oooo)
    t2 += 0.5*lib.einsum('ijef,abef->ijab', c2, eris.vvvv)
    tmp = lib.einsum('imae,mbej->ijab', c2, eris.ovvo)
    tmp+= numpy.einsum('ia,jb->ijab', c1, fov)
    tmp = tmp - tmp.transpose(0,1,3,2)
    t2 += tmp - tmp.transpose(1,0,2,3)
    tmp = lib.einsum('ie,jeba->ijab', c1, numpy.asarray(eris.ovvv).conj())
    t2 += tmp - tmp.transpose(1,0,2,3)
    tmp = lib.einsum('ma,ijmb->ijab', c1, numpy.asarray(eris.ooov).conj())
    t2 -= tmp - tmp.transpose(0,1,3,2)

    eris_oovv = numpy.asarray(eris.oovv)
    t1 += fov * c0
    t2 += eris_oovv * c0
    t0  = numpy.einsum('ia,ia', fov, c1)
    t0 += numpy.einsum('ijab,ijab', eris_oovv, c2) * .25

    return amplitudes_to_cisdvec(t0, t1, t2)

def amplitudes_to_cisdvec(c0, c1, c2):
    nocc, nvir = c1.shape
    ooidx = numpy.tril_indices(nocc, -1)
    vvidx = numpy.tril_indices(nvir, -1)
    c2tril = lib.take_2d(c2.reshape(nocc**2,nvir**2),
                         ooidx[0]*nocc+ooidx[1], vvidx[0]*nvir+vvidx[1])
    return numpy.hstack((c0, c1.ravel(), c2tril.ravel()))

def cisdvec_to_amplitudes(civec, nmo, nocc):
    nvir = nmo - nocc
    c0 = civec[0]
    c1 = civec[1:nocc*nvir+1].reshape(nocc,nvir)
    c2 = ccsd._unpack_4fold(civec[nocc*nvir+1:], nocc, nvir)
    return c0, c1, c2

def from_cisdvec(civec, nocc, orbspin):
    '''Convert the CISD vectors'''
    from pyscf.cc import addons
    from pyscf.ci import ucisd
    nmoa = numpy.count_nonzero(orbspin == 0)
    nmob = numpy.count_nonzero(orbspin == 1)
    if isinstance(nocc, int):
        nocca = noccb = nocc
    else:
        nocca, noccb = nocc
    nvira, nvirb = nmoa-nocca, nmob-noccb

    if civec.size == nocca*nvira + (nocca*nvira)**2 + 1:  # RCISD
        c0, c1, c2 = cisd.cisdvec_to_amplitudes(civec, nmoa, nocca)
    else:  # UCISD
        c0, c1, c2 = ucisd.cisdvec_to_amplitudes(civec, (nmoa,nmob), (nocca,noccb))
    c1 = addons.spatial2spin(c1, orbspin)
    c2 = addons.spatial2spin(c2, orbspin)
    return amplitudes_to_cisdvec(c0, c1, c2)

t1strs = cisd.t1strs

def t2strs(norb, nelec):
    nocc = nelec
    hf_str = int('1'*nocc, 2)
    addrs = []
    signs = []
    for a in range(nocc+1, norb):
        for b in range(nocc, a):
            for i in reversed(range(1,nocc)):
                for j in reversed(range(i)):
                    str1 = hf_str ^ (1 << j) | (1 << b)
                    sign = cistring.cre_des_sign(b, j, hf_str)
                    sign*= cistring.cre_des_sign(a, i, str1)
                    str1^= (1 << i) | (1 << a)
                    addrs.append(cistring.str2addr(norb, nelec, str1))
                    signs.append(sign)
    return numpy.asarray(addrs), numpy.asarray(signs)

def to_fcivec(cisdvec, nelec, orbspin):
    from pyscf import fci
    nocc = nelec
    norb = len(orbspin)
    c0, c1, c2 = cisdvec_to_amplitudes(cisdvec, norb, nocc)
    oidxa = orbspin[:nocc] == 0
    oidxb = orbspin[:nocc] == 1
    vidxa = orbspin[nocc:] == 0
    vidxb = orbspin[nocc:] == 1
    c1a = c1[oidxa][:,vidxa]
    c1b = c1[oidxb][:,vidxb]
    c2aa = c2[oidxa][:,oidxa][:,:,vidxa][:,:,:,vidxa]
    c2bb = c2[oidxb][:,oidxb][:,:,vidxb][:,:,:,vidxb]
    c2ab = c2[oidxa][:,oidxb][:,:,vidxa][:,:,:,vidxb]
    nocca = numpy.count_nonzero(oidxa)
    noccb = numpy.count_nonzero(oidxb)
    nvira = numpy.count_nonzero(vidxa)
    nvirb = numpy.count_nonzero(vidxb)
    norba = nocca + nvira
    norbb = noccb + nvirb
    t1addra, t1signa = t1strs(norba, nocca)
    t1addrb, t1signb = t1strs(norbb, noccb)

    na = fci.cistring.num_strings(norba, nocca)
    nb = fci.cistring.num_strings(norbb, noccb)
    fcivec = numpy.zeros((na,nb))
    fcivec[0,0] = c0
    fcivec[t1addra,0] = c1a[::-1].T.ravel() * t1signa
    fcivec[0,t1addrb] = c1b[::-1].T.ravel() * t1signb
    c2ab = c2ab[::-1,::-1].transpose(2,0,3,1).reshape(nocca*nvira,-1)
    c2ab = numpy.einsum('i,j,ij->ij', t1signa, t1signb, c2ab)
    lib.takebak_2d(fcivec, c2ab, t1addra, t1addrb)

    if nocca > 1 and nvira > 1:
        ooidx = numpy.tril_indices(nocca, -1)
        vvidx = numpy.tril_indices(nvira, -1)
        c2aa = c2aa[ooidx][:,vvidx[0],vvidx[1]]
        t2addra, t2signa = t2strs(norba, nocca)
        fcivec[t2addra,0] = c2aa[::-1].T.ravel() * t2signa
    if noccb > 1 and nvirb > 1:
        ooidx = numpy.tril_indices(noccb, -1)
        vvidx = numpy.tril_indices(nvirb, -1)
        c2bb = c2bb[ooidx][:,vvidx[0],vvidx[1]]
        t2addrb, t2signb = t2strs(norbb, noccb)
        fcivec[0,t2addrb] = c2bb[::-1].T.ravel() * t2signb
    return fcivec

def from_fcivec(ci0, nelec, orbspin):
    nocc = nelec
    oidxa = orbspin[:nocc] == 0
    oidxb = orbspin[:nocc] == 1
    vidxa = orbspin[nocc:] == 0
    vidxb = orbspin[nocc:] == 1
    nocca = numpy.count_nonzero(oidxa)
    noccb = numpy.count_nonzero(oidxb)
    nvira = numpy.count_nonzero(vidxa)
    nvirb = numpy.count_nonzero(vidxb)
    norba = nocca+nvira
    norbb = noccb+nvirb
    t1addra, t1signa = t1strs(norba, nocca)
    t1addrb, t1signb = t1strs(norbb, noccb)

    na = fci.cistring.num_strings(norba, nocca)
    nb = fci.cistring.num_strings(norbb, noccb)
    ci0 = ci0.reshape(na,nb)
    c0 = ci0[0,0]
    c1a = ((ci0[t1addra,0] * t1signa).reshape(nvira,nocca).T)[::-1]
    c1b = ((ci0[0,t1addrb] * t1signb).reshape(nvirb,noccb).T)[::-1]
    c1 = spatial2spin((c1a, c1b), orbspin)

    c2ab = numpy.einsum('i,j,ij->ij', t1signa, t1signb, ci0[t1addra][:,t1addrb])
    c2ab = c2ab.reshape(nvira,nocca,nvirb,noccb).transpose(1,3,0,2)
    c2ab = c2ab[::-1,::-1]
    t2addra, t2signa = t2strs(norba, nocca)
    c2aa = (ci0[t2addra,0] * t2signa).reshape(nvira*(nvira-1)//2,-1).T
    c2aa = ccsd._unpack_4fold(c2aa[::-1], nocca, nvira)
    t2addrb, t2signb = t2strs(norbb, noccb)
    c2bb = (ci0[0,t2addrb] * t2signb).reshape(nvirb*(nvirb-1)//2,-1).T
    c2bb = ccsd._unpack_4fold(c2bb[::-1], noccb, nvirb)
    c2 = spatial2spin((c2aa, c2ab, c2bb), orbspin)

    cisdvec = amplitudes_to_cisdvec(c0, c1, c2)
    return cisdvec


def make_rdm1(myci, civec=None, nmo=None, nocc=None):
    '''spin-orbital 1-particle density matrix
    '''
    if civec is None: civec = myci.ci
    if nmo is None: nmo = myci.nmo
    if nocc is None: nocc = myci.nocc
    d1 = _gamma1_intermediates(myci, civec, nmo, nocc)
    return gccsd_rdm._make_rdm1(myci, d1, with_frozen=True)

def make_rdm2(myci, civec=None, nmo=None, nocc=None):
    '''spin-orbital 2-particle density matrix in chemist's notation
    '''
    if civec is None: civec = myci.ci
    if nmo is None: nmo = myci.nmo
    if nocc is None: nocc = myci.nocc
    d1 = _gamma1_intermediates(myci, civec, nmo, nocc)
    d2 = _gamma2_intermediates(myci, civec, nmo, nocc)
    return gccsd_rdm._make_rdm2(myci, d1, d2, with_dm1=True, with_frozen=True)

def _gamma1_intermediates(myci, civec, nmo, nocc):
    c0, c1, c2 = cisdvec_to_amplitudes(civec, nmo, nocc)
    dov = c0 * c1
    dov += numpy.einsum('jb,ijab->ia', c1.conj(), c2)
    doo  =-numpy.einsum('ia,ka->ik', c1.conj(), c1)
    doo -= numpy.einsum('jiab,kiab->jk', c2.conj(), c2) * .5
    dvv  = numpy.einsum('ia,ic->ac', c1, c1.conj())
    dvv += numpy.einsum('ijab,ijac->bc', c2, c2.conj()) * .5
    return doo, dov, dov.conj().T, dvv

def _gamma2_intermediates(myci, civec, nmo, nocc):
    c0, c1, c2 = cisdvec_to_amplitudes(civec, nmo, nocc)
    goovv = c0 * c2 * .5
    govvv = numpy.einsum('ia,ikcd->kadc', c1.conj(), c2) * .5
    gooov = numpy.einsum('ia,klac->klic', c1.conj(), c2) *-.5
    goooo = numpy.einsum('ijab,klab->ijkl', c2.conj(), c2) * .25
    gvvvv = numpy.einsum('ijab,ijcd->abcd', c2, c2.conj()) * .25
    govvo = numpy.einsum('ijab,ikac->jcbk', c2.conj(), c2)
    govvo+= numpy.einsum('ia,jb->ibaj', c1.conj(), c1)

    dovov = goovv.transpose(0,2,1,3) - goovv.transpose(0,3,1,2)
    doooo = goooo.transpose(0,2,1,3) - goooo.transpose(0,3,1,2)
    dvvvv = gvvvv.transpose(0,2,1,3) - gvvvv.transpose(0,3,1,2)
    dovvo = govvo.transpose(0,2,1,3)
    dooov = gooov.transpose(0,2,1,3) - gooov.transpose(1,2,0,3)
    dovvv = govvv.transpose(0,2,1,3) - govvv.transpose(0,3,1,2)
    doovv = None
    dvvov = None
    return dovov, dvvvv, doooo, doovv, dovvo, dvvov, dovvv, dooov


class GCISD(cisd.CISD):
    def get_init_guess(self, eris=None):
        # MP2 initial guess
        if eris is None: eris = self.ao2mo(self.mo_coeff)
        time0 = time.clock(), time.time()
        mo_e = eris.fock.diagonal()
        nocc = self.nocc
        eia = mo_e[:nocc,None] - mo_e[None,nocc:]
        eijab = lib.direct_sum('ia,jb->ijab',eia,eia)
        t1 = eris.fock[:nocc,nocc:] / eia
        eris_oovv = numpy.array(eris.oovv)
        t2 = eris_oovv / eijab
        self.emp2 = 0.25*numpy.einsum('ijab,ijab', t2.conj(), eris_oovv).real
        logger.info(self, 'Init t2, MP2 energy = %.15g', self.emp2)
        logger.timer(self, 'init mp2', *time0)

        if abs(self.emp2) < 1e-3 and abs(t1).sum() < 1e-3:
            t1 = 1. / eia
        return self.emp2, amplitudes_to_cisdvec(1, t1, t2)

    def ao2mo(self, mo_coeff=None):
        nmo = self.nmo
        mem_incore = nmo**4*2 * 8/1e6
        mem_now = lib.current_memory()[0]
        if (self._scf._eri is not None and
            (mem_incore+mem_now < self.max_memory) or self.mol.incore_anyway):
            return gccsd._make_eris_incore(self, mo_coeff)
        elif hasattr(self._scf, 'with_df'):
            raise NotImplementedError
        else:
            return gccsd._make_eris_outcore(self, mo_coeff)

    contract = contract
    make_diagonal = make_diagonal
    _dot = None

    def to_fcivec(self, cisdvec, nelec, orbspin):
        return to_fcivec(cisdvec, nelec, orbspin)

    def from_fcivec(self, fcivec, nelec, orbspin):
        return from_fcivec(fcivec, nelec, orbspin)

    make_rdm1 = make_rdm1
    make_rdm2 = make_rdm2

    def amplitudes_to_cisdvec(self, c0, c1, c2):
        return amplitudes_to_cisdvec(c0, c1, c2)

    def cisdvec_to_amplitudes(self, civec, nmo=None, nocc=None):
        if nmo is None: nmo = self.nmo
        if nocc is None: nocc = self.nocc
        return cisdvec_to_amplitudes(civec, nmo, nocc)

    def spatial2spin(self, tx, orbspin=None):
        if orbspin is None:
            orbspin = getattr(self.mo_coeff, 'orbspin', None)
            if orbspin is not None:
                orbspin = orbspin[self.get_frozen_mask()]
        return spatial2spin(tx, orbspin)

    def spin2spatial(self, tx, orbspin=None):
        if orbspin is None:
            orbspin = getattr(self.mo_coeff, 'orbspin', None)
            if orbspin is not None:
                orbspin = orbspin[self.get_frozen_mask()]
        return spin2spatial(tx, orbspin)


if __name__ == '__main__':
    from pyscf import gto
    from pyscf import scf
    from pyscf import fci
    from pyscf import ao2mo
    from pyscf.cc.addons import spatial2spin

    mol = gto.Mole()
    mol.verbose = 0
    mol.atom = [
        ['O', ( 0., 0.    , 0.   )],
        ['H', ( 0., -0.757, 0.587)],
        ['H', ( 0., 0.757 , 0.587)],]
    mol.basis = {'H': 'sto-3g',
                 'O': 'sto-3g',}
    mol.build()
    mf = scf.UHF(mol).run(conv_tol=1e-14)
    gmf = scf.addons.convert_to_ghf(mf)
    myci = GCISD(gmf)
    eris = myci.ao2mo()
    ecisd, civec = myci.kernel(eris=eris)
    print(ecisd - -0.048878084082066106)

    nmo = eris.mo_coeff.shape[1]
    rdm1 = myci.make_rdm1(civec, nmo, mol.nelectron)
    rdm2 = myci.make_rdm2(civec, nmo, mol.nelectron)

    mo = eris.mo_coeff[:7] + eris.mo_coeff[7:]
    eri = ao2mo.kernel(mf._eri, mo, compact=False).reshape([nmo]*4)
    eri[eris.orbspin[:,None]!=eris.orbspin,:,:] = 0
    eri[:,:,eris.orbspin[:,None]!=eris.orbspin] = 0
    h1a = reduce(numpy.dot, (mf.mo_coeff[0].T, mf.get_hcore(), mf.mo_coeff[0]))
    h1b = reduce(numpy.dot, (mf.mo_coeff[1].T, mf.get_hcore(), mf.mo_coeff[1]))
    h1e = numpy.zeros((nmo,nmo))
    idxa = eris.orbspin == 0
    idxb = eris.orbspin == 1
    h1e[idxa[:,None]&idxa] = h1a.ravel()
    h1e[idxb[:,None]&idxb] = h1b.ravel()
    e2 = (numpy.einsum('ij,ji', h1e, rdm1) +
          numpy.einsum('ijkl,jilk', eri, rdm2) * .5)
    e2 += mol.energy_nuc()
    print(myci.e_tot - e2)   # = 0

    print(abs(rdm1 - numpy.einsum('ijkk->ij', rdm2)/(mol.nelectron-1)).sum())

