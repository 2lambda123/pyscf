#!/usr/bin/env python
# $Id$
# -*- coding: utf-8


'''
RMP2
'''

import time
from functools import reduce
import copy
import numpy
from pyscf import gto
from pyscf import lib
from pyscf.lib import logger
from pyscf import ao2mo
from pyscf.ao2mo import _ao2mo

def kernel(mp, mo_energy=None, mo_coeff=None, eris=None, with_t2=True,
           verbose=logger.NOTE):
    if mo_energy is None or mo_coeff is None:
        mo_coeff = None
        mo_energy = _mo_energy_without_core(mp, mp.mo_energy)
    else:
        # For backward compatibility.  In pyscf-1.4 or earlier, mp.frozen is
        # not supported when mo_energy or mo_coeff is given.
        assert(mp.frozen is 0 or mp.frozen is None)

    if eris is None: eris = mp.ao2mo(mo_coeff)

    nocc = mp.nocc
    nvir = mp.nmo - nocc
    eia = mo_energy[:nocc,None] - mo_energy[None,nocc:]

    if with_t2:
        t2 = numpy.empty((nocc,nocc,nvir,nvir), dtype=eris.ovov.dtype)
    else:
        t2 = None

    emp2 = 0
    for i in range(nocc):
        gi = numpy.asarray(eris.ovov[i*nvir:(i+1)*nvir])
        gi = gi.reshape(nvir,nocc,nvir).transpose(1,0,2)
        t2i = gi.conj()/lib.direct_sum('jb+a->jba', eia, eia[i])
        emp2 += numpy.einsum('jab,jab', t2i, gi) * 2
        emp2 -= numpy.einsum('jab,jba', t2i, gi)
        if with_t2:
            t2[i] = t2i

    return emp2.real, t2

def make_rdm1_ao(mp, mo_energy=None, mo_coeff=None, eris=None, verbose=logger.NOTE):
    '''1-particle density matrix in AO basis.  The occupied-virtual orbital
    response is not included.  This function uses small amount of memory.  The
    MP2 t2 amplitudes are generated on the fly using the given eris object.
    '''
    if mo_energy is None or mo_coeff is None:
        mo_coeff = None
    else:
        assert(mp.frozen is 0 or mp.frozen is None)
        mp = copy.copy(mp)
        mp.mo_energy = mo_energy
        mp.mo_coeff = mo_coeff

    if eris is None: eris = mp.ao2mo(mo_coeff)

    rdm1_mo = make_rdm1(mp, None, eris, verbose)
    rdm1 = reduce(numpy.dot, (mo_coeff, rdm1_mo, mo_coeff.T))
    return rdm1

def make_rdm1(mp, t2=None, eris=None, verbose=logger.NOTE):
    '''1-particle density matrix in MO basis.  The off-diagonal blocks due to
    the orbital response contribution are not included.
    '''
    from pyscf.cc import ccsd_rdm
    doo, dvv = _gamma1_intermediates(mp, t2, eris)
    nocc = doo.shape[0]
    nvir = doo.shape[0]
    dov = numpy.zeros((nocc,nvir), dtype=doo.dtype)
    dvo = dov.T
    return ccsd_rdm._make_rdm1(mp, (doo, dov, dvo, dvv), with_frozen=True)

def _gamma1_intermediates(mp, t2=None, eris=None):
    if t2 is None: t2 = mp.t2
    nmo = mp.nmo
    nocc = mp.nocc
    nvir = nmo - nocc
    if t2 is None:
        if eris is None: eris = mp.ao2mo()
        mo_energy = _mo_energy_without_core(mp, mp.mo_energy)
        eia = mo_energy[:nocc,None] - mo_energy[None,nocc:]
        dtype = eris.ovov.dtype
    else:
        dtype = t2.dtype

    dm1occ = numpy.zeros((nocc,nocc), dtype=dtype)
    dm1vir = numpy.zeros((nvir,nvir), dtype=dtype)
    for i in range(nocc):
        if t2 is None:
            gi = numpy.asarray(eris.ovov[i*nvir:(i+1)*nvir])
            gi = gi.reshape(nvir,nocc,nvir).transpose(1,0,2)
            t2i = gi.conj()/lib.direct_sum('jb+a->jba', eia, eia[i])
        else:
            t2i = t2[i]
        l2i = t2i.conj()
        dm1vir += numpy.einsum('jca,jcb->ba', l2i, t2i) * 2 \
                - numpy.einsum('jca,jbc->ba', l2i, t2i)
        dm1occ += numpy.einsum('iab,jab->ij', l2i, t2i) * 2 \
                - numpy.einsum('iab,jba->ij', l2i, t2i)
    return -dm1occ, dm1vir


def make_rdm2(mp, t2=None, eris=None, verbose=logger.NOTE):
    '''2-RDM in MO basis'''
    if t2 is None: t2 = mp.t2
    nmo = nmo0 = mp.nmo
    nocc = nocc0 = mp.nocc
    nvir = nmo - nocc
    if t2 is None:
        if eris is None: eris = mp.ao2mo()
        mo_energy = _mo_energy_without_core(mp, mp.mo_energy)
        eia = mo_energy[:nocc,None] - mo_energy[None,nocc:]

    dm1 = make_rdm1(mp, t2, eris, verbose)
    dm1[numpy.diag_indices(nocc0)] -= 2

    if not (mp.frozen is 0 or mp.frozen is None):
        nmo0 = mp.mo_occ.size
        nocc0 = numpy.count_nonzero(mp.mo_occ > 0)
        moidx = get_frozen_mask(mp)
        oidx = numpy.where(moidx & (mp.mo_occ > 0))[0]
        vidx = numpy.where(moidx & (mp.mo_occ ==0))[0]
    else:
        moidx = oidx = vidx = None

    dm2 = numpy.zeros((nmo0,nmo0,nmo0,nmo0), dtype=dm1.dtype) # Chemist notation
    #dm2[:nocc,nocc:,:nocc,nocc:] = t2.transpose(0,3,1,2)*2 - t2.transpose(0,2,1,3)
    #dm2[nocc:,:nocc,nocc:,:nocc] = t2.transpose(3,0,2,1)*2 - t2.transpose(2,0,3,1)
    for i in range(nocc):
        if t2 is None:
            gi = numpy.asarray(eris.ovov[i*nvir:(i+1)*nvir])
            gi = gi.reshape(nvir,nocc,nvir).transpose(1,0,2)
            t2i = gi.conj()/lib.direct_sum('jb+a->jba', eia, eia[i])
        else:
            t2i = t2[i]
        t2i = t2i.conj()
        dovov = t2i.transpose(1,0,2)*2 - t2i.transpose(2,0,1)
        dovov *= 2
        if moidx is None:
            dm2[i,nocc:,:nocc,nocc:] = dovov
            dm2[nocc:,i,nocc:,:nocc] = dovov.conj().transpose(0,2,1)
        else:
            dm2[oidx[i],vidx[:,None,None],oidx[:,None],vidx] = dovov
            dm2[vidx[:,None,None],oidx[i],vidx[:,None],oidx] = dovov.conj().transpose(0,2,1)

    for i in range(nocc0):
        dm2[i,i,:,:] += dm1 * 2
        dm2[:,:,i,i] += dm1 * 2
        dm2[:,i,i,:] -= dm1
        dm2[i,:,:,i] -= dm1.conj()

    for i in range(nocc0):
        for j in range(nocc0):
            dm2[i,i,j,j] += 4
            dm2[i,j,j,i] -= 2
    return dm2


def get_nocc(mp):
    if mp._nocc is not None:
        return mp._nocc
    elif mp.frozen is None:
        nocc = numpy.count_nonzero(mp.mo_occ > 0)
        assert(nocc > 0)
        return nocc
    elif isinstance(mp.frozen, (int, numpy.integer)):
        nocc = numpy.count_nonzero(mp.mo_occ > 0) - mp.frozen
        assert(nocc > 0)
        return nocc
    else:
        occ_idx = mp.mo_occ > 0
        occ_idx[list(mp.frozen)] = False
        return numpy.count_nonzero(occ_idx)

def get_nmo(mp):
    if mp._nmo is not None:
        return mp._nmo
    elif mp.frozen is None:
        return len(mp.mo_occ)
    elif isinstance(mp.frozen, (int, numpy.integer)):
        return len(mp.mo_occ) - mp.frozen
    else:
        return len(mp.mo_occ) - len(mp.frozen)

def get_frozen_mask(mp):
    '''Get boolean mask for the restricted reference orbitals.
    
    In the returned boolean (mask) array of frozen orbital indices, the
    element is False if it corresonds to the frozen orbital.
    '''
    moidx = numpy.ones(mp.mo_occ.size, dtype=numpy.bool)
    if mp._nmo is not None:
        moidx[mp._nmo:] = False
    elif mp.frozen is None:
        pass
    elif isinstance(mp.frozen, (int, numpy.integer)):
        moidx[:mp.frozen] = False
    elif len(mp.frozen) > 0:
        moidx[list(mp.frozen)] = False
    return moidx


def as_scanner(mp):
    '''Generating a scanner/solver for MP2 PES.

    The returned solver is a function. This function requires one argument
    "mol" as input and returns total MP2 energy.

    The solver will automatically use the results of last calculation as the
    initial guess of the new calculation.  All parameters assigned in the
    MP2 and the underlying SCF objects (conv_tol, max_memory etc) are
    automatically applied in the solver.

    Note scanner has side effects.  It may change many underlying objects
    (_scf, with_df, with_x2c, ...) during calculation.

    Examples::

        >>> from pyscf import gto, scf, mp
        >>> mol = gto.M(atom='H 0 0 0; F 0 0 1')
        >>> mp2_scanner = mp.MP2(scf.RHF(mol)).as_scanner()
        >>> e_tot = mp2_scanner(gto.M(atom='H 0 0 0; F 0 0 1.1'))
        >>> e_tot = mp2_scanner(gto.M(atom='H 0 0 0; F 0 0 1.5'))
    '''
    logger.info(mp, 'Set %s as a scanner', mp.__class__)
    class MP2_Scanner(mp.__class__, lib.SinglePointScanner):
        def __init__(self, mp):
            self.__dict__.update(mp.__dict__)
            self._scf = mp._scf.as_scanner()
        def __call__(self, mol, **kwargs):
            mf_scanner = self._scf
            mf_scanner(mol)
            self.mol = mol
            self.mo_energy = mf_scanner.mo_energy
            self.mo_coeff = mf_scanner.mo_coeff
            self.mo_occ = mf_scanner.mo_occ
            self.kernel(**kwargs)[0]
            return self.e_tot
    return MP2_Scanner(mp)


class MP2(lib.StreamObject):
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
        self.mo_energy = mf.mo_energy
        self.mo_coeff = mo_coeff
        self.mo_occ = mo_occ
        self._nocc = None
        self._nmo = None
        self.e_corr = None
        self.t2 = None
        self._keys = set(self.__dict__.keys())

    @property
    def nocc(self):
        return self.get_nocc()
    @nocc.setter
    def nocc(self, n):
        self._nocc = n

    @property
    def nmo(self):
        return self.get_nmo()
    @nmo.setter
    def nmo(self, n):
        self._nmo = n

    get_nocc = get_nocc
    get_nmo = get_nmo
    get_frozen_mask = get_frozen_mask

    def dump_flags(self):
        log = logger.Logger(self.stdout, self.verbose)
        log.info('')
        log.info('******** %s flags ********', self.__class__)
        log.info('nocc = %s, nmo = %s', self.nocc, self.nmo)
        if self.frozen is not 0:
            log.info('frozen orbitals %s', self.frozen)
        log.info('max_memory %d MB (current use %d MB)',
                 self.max_memory, lib.current_memory()[0])

    @property
    def emp2(self):
        return self.e_corr

    @property
    def e_tot(self):
        return self.e_corr + self._scf.e_tot

    def kernel(self, mo_energy=None, mo_coeff=None, eris=None, with_t2=True,
               _kern=kernel):
        '''
        Args:
            with_t2 : bool
                Whether to generate and hold t2 amplitudes in memory.
        '''
        if mo_energy is not None: self.mo_energy = mo_energy
        if mo_coeff is not None: self.mo_coeff = mo_coeff
        if self.mo_energy is None or self.mo_coeff is None:
            raise RuntimeError('mo_coeff, mo_energy are not initialized.\n'
                               'You may need to call mf.kernel() to generate them.')
        if self.verbose >= logger.WARN:
            self.check_sanity()
        self.dump_flags()

        self.e_corr, self.t2 = _kern(self, mo_energy, mo_coeff,
                                     eris, with_t2, self.verbose)
        logger.log(self, 'E(%s) = %.15g  E_corr = %.15g',
                   self.__class__.__name__, self.e_tot, self.e_corr)
        return self.e_corr, self.t2

    def ao2mo(self, mo_coeff=None):
        return _make_eris(self, mo_coeff, verbose=self.verbose)

    make_rdm1 = make_rdm1
    make_rdm2 = make_rdm2

    as_scanner = as_scanner

    def nuc_grad_method(self):
        from pyscf.mp import mp2_grad
        return mp2_grad.Gradients(self)

RMP2 = MP2


def _mo_energy_without_core(mp, mo_energy):
    return mo_energy[get_frozen_mask(mp)]

def _mo_without_core(mp, mo):
    return mo[:,get_frozen_mask(mp)]

def _mem_usage(nocc, nvir):
    nmo = nocc + nvir
    basic = ((nocc*nvir)**2 + nocc*nvir**2*2)*8 / 1e6
    incore = nocc*nvir*nmo**2/2*8 / 1e6 + basic
    outcore = basic
    return incore, outcore, basic

class _ChemistsERIs:
    def __init__(self, mp, mo_coeff=None):
        if mo_coeff is None:
            self.mo_coeff = _mo_without_core(mp, mp.mo_coeff)
        else:
            self.mo_coeff = _mo_without_core(mp, mo_coeff)

def _make_eris(mp, mo_coeff=None, ao2mofn=None, verbose=None):
    log = logger.new_logger(mp, verbose)
    time0 = (time.clock(), time.time())
    eris = _ChemistsERIs(mp, mo_coeff)
    mo_coeff = eris.mo_coeff

    nocc = mp.nocc
    nmo = mp.nmo
    nvir = nmo - nocc
    mem_incore, mem_outcore, mem_basic = _mem_usage(nocc, nvir)
    mem_now = lib.current_memory()[0]
    max_memory = max(0, mp.max_memory - mem_now)
    if max_memory < mem_basic:
        log.warn('Not enough memory for integral transformation. '
                 'Available mem %s MB, required mem %s MB',
                 max_memory, mem_basic)

    co = numpy.asarray(mo_coeff[:,:nocc], order='F')
    cv = numpy.asarray(mo_coeff[:,nocc:], order='F')
    if (mp.mol.incore_anyway or
        (mp._scf._eri is not None and mem_incore < max_memory)):
        log.debug('transform (ia|jb) incore')
        if callable(ao2mofn):
            eris.ovov = ao2mofn((co,cv,co,cv)).reshape(nocc*nvir,nocc*nvir)
        else:
            eris.ovov = ao2mo.general(mp._scf._eri, (co,cv,co,cv))

    elif hasattr(mp._scf, 'with_df') and mp._scf.with_df:
        # To handle the PBC or custom 2-electron with 3-index tensor.
        # Call dfmp2.MP2 for efficient DF-MP2 implementation.
        log.warn('DF-HF is found. (ia|jb) is computed based on the DF '
                 '3-tensor integrals.\n'
                 'You can switch to dfmp2.MP2 for better performance')
        log.debug('transform (ia|jb) with_df')
        eris.ovov = mp._scf.with_df.ao2mo((co,cv,co,cv))

    else:
        log.debug('transform (ia|jb) outcore')
        eris.feri = lib.H5TmpFile()
        #ao2mo.outcore.general(mp.mol, (co,cv,co,cv), eris.feri,
        #                      max_memory=max_memory, verbose=log)
        #eris.ovov = eris.feri['eri_mo']
        eris.ovov = _ao2mo_ovov(mp, co, cv, eris.feri, max(2000, max_memory), log)

    time1 = log.timer('Integral transformation', *time0)
    return eris

#
# the MO integral for MP2 is (ov|ov). This is the efficient integral
# (ij|kl) => (ij|ol) => (ol|ij) => (ol|oj) => (ol|ov) => (ov|ov)
#   or    => (ij|ol) => (oj|ol) => (oj|ov) => (ov|ov)
#
def _ao2mo_ovov(mp, orbo, orbv, feri, max_memory=2000, verbose=None):
    time0 = (time.clock(), time.time())
    log = logger.new_logger(mp, verbose)

    mol = mp.mol
    int2e = mol._add_suffix('int2e')
    ao2mopt = _ao2mo.AO2MOpt(mol, int2e, 'CVHFnr_schwarz_cond',
                             'CVHFsetnr_direct_scf')
    nao, nocc = orbo.shape
    nvir = orbv.shape[1]
    nbas = mol.nbas
    assert(nvir <= nao)

    ao_loc = mol.ao_loc_nr()
    dmax = max(4, min(nao/3, numpy.sqrt(max_memory*.95e6/8/(nao+nocc)**2)))
    sh_ranges = ao2mo.outcore.balance_partition(ao_loc, dmax)
    dmax = max(x[2] for x in sh_ranges)
    eribuf = numpy.empty((nao,dmax,dmax,nao))
    ftmp = lib.H5TmpFile()
    log.debug('max_memory %s MB (dmax = %s) required disk space %g MB',
              max_memory, dmax, nocc**2*(nao*(nao+dmax)/2+nvir**2)*8/1e6)

    buf_i = numpy.empty((nocc*dmax**2*nao))
    buf_li = numpy.empty((nocc**2*dmax**2))
    buf1 = numpy.empty_like(buf_li)

    fint = gto.moleintor.getints4c
    jk_blk_slices = []
    count = 0
    time1 = time0
    with lib.call_in_background(ftmp.__setitem__) as save:
        for ip, (ish0, ish1, ni) in enumerate(sh_ranges):
            for jsh0, jsh1, nj in sh_ranges[:ip+1]:
                i0, i1 = ao_loc[ish0], ao_loc[ish1]
                j0, j1 = ao_loc[jsh0], ao_loc[jsh1]
                jk_blk_slices.append((i0,i1,j0,j1))

                eri = fint(int2e, mol._atm, mol._bas, mol._env,
                           shls_slice=(0,nbas,ish0,ish1, jsh0,jsh1,0,nbas),
                           aosym='s1', ao_loc=ao_loc, cintopt=ao2mopt._cintopt,
                           out=eribuf)
                tmp_i = numpy.ndarray((nocc,(i1-i0)*(j1-j0)*nao), buffer=buf_i)
                tmp_li = numpy.ndarray((nocc,nocc*(i1-i0)*(j1-j0)), buffer=buf_li)
                lib.ddot(orbo.T, eri.reshape(nao,(i1-i0)*(j1-j0)*nao), c=tmp_i)
                lib.ddot(orbo.T, tmp_i.reshape(nocc*(i1-i0)*(j1-j0),nao).T, c=tmp_li)
                tmp_li = tmp_li.reshape(nocc,nocc,(i1-i0),(j1-j0))
                save(str(count), tmp_li.transpose(1,0,2,3))
                buf_li, buf1 = buf1, buf_li
                count += 1
                time1 = log.timer_debug1('partial ao2mo [%d:%d,%d:%d]' %
                                         (ish0,ish1,jsh0,jsh1), *time1)
    time1 = time0 = log.timer('mp2 ao2mo_ovov pass1', *time0)
    eri = eribuf = tmp_i = tmp_li = buf_i = buf_li = buf1 = None

    chunks = (nvir,nvir)
    h5dat = feri.create_dataset('ovov', (nocc*nvir,nocc*nvir), 'f8',
                                chunks=chunks)
    occblk = int(min(nocc, max(4, 250/nocc, max_memory*.9e6/8/(nao**2*nocc)/5)))
    def load(i0, eri):
        if i0 < nocc:
            i1 = min(i0+occblk, nocc)
            for k, (p0,p1,q0,q1) in enumerate(jk_blk_slices):
                eri[:i1-i0,:,p0:p1,q0:q1] = ftmp[str(k)][i0:i1]
                if p0 != q0:
                    dat = numpy.asarray(ftmp[str(k)][:,i0:i1])
                    eri[:i1-i0,:,q0:q1,p0:p1] = dat.transpose(1,0,3,2)

    def save(i0, i1, dat):
        for i in range(i0, i1):
            h5dat[i*nvir:(i+1)*nvir] = dat[i-i0].reshape(nvir,nocc*nvir)

    orbv = numpy.asarray(orbv, order='F')
    buf_prefecth = numpy.empty((occblk,nocc,nao,nao))
    buf = numpy.empty_like(buf_prefecth)
    bufw = numpy.empty((occblk*nocc,nvir**2))
    bufw1 = numpy.empty_like(bufw)
    with lib.call_in_background(load) as prefetch:
        with lib.call_in_background(save) as bsave:
            load(0, buf_prefecth)
            for i0, i1 in lib.prange(0, nocc, occblk):
                buf, buf_prefecth = buf_prefecth, buf
                prefetch(i1, buf_prefecth)
                eri = buf[:i1-i0].reshape((i1-i0)*nocc,nao,nao)

                dat = _ao2mo.nr_e2(eri, orbv, (0,nvir,0,nvir), 's1', 's1', out=bufw)
                bsave(i0, i1, dat.reshape(i1-i0,nocc,nvir,nvir).transpose(0,2,1,3))
                bufw, bufw1 = bufw1, bufw
                time1 = log.timer_debug1('pass2 ao2mo [%d:%d]' % (i0,i1), *time1)

    time0 = log.timer('mp2 ao2mo_ovov pass2', *time0)
    return h5dat

if __name__ == '__main__':
    from pyscf import scf
    from pyscf import gto
    mol = gto.Mole()
    mol.atom = [
        [8 , (0. , 0.     , 0.)],
        [1 , (0. , -0.757 , 0.587)],
        [1 , (0. , 0.757  , 0.587)]]

    mol.basis = 'cc-pvdz'
    mol.build()
    mf = scf.RHF(mol).run()
    mp = MP2(mf)
    mp.verbose = 5

    pt = MP2(mf)
    emp2, t2 = pt.kernel()
    print(emp2 - -0.204019967288338)
    pt.max_memory = 1
    emp2, t2 = pt.kernel()
    print(emp2 - -0.204019967288338)

    pt = MP2(scf.density_fit(mf, 'weigend'))
    print(pt.kernel()[0] - -0.204254500454)
