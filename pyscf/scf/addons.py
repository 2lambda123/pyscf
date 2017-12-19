#!/usr/bin/env python
#
# Authors: Qiming Sun <osirpt.sun@gmail.com>
#          Junzi Liu <latrix1247@gmail.com>
#


import sys
import copy
from functools import reduce
import numpy
from pyscf import lib
from pyscf.gto import mole
from pyscf.lib import logger
from pyscf.symm import sph
from pyscf.scf import hf


def frac_occ_(mf, tol=1e-3):
    assert(isinstance(mf, hf.RHF))
    old_get_occ = mf.get_occ
    def get_occ(mo_energy, mo_coeff=None):
        mol = mf.mol
        nocc = mol.nelectron // 2
        sort_mo_energy = numpy.sort(mo_energy)
        lumo = sort_mo_energy[nocc]
        if abs(sort_mo_energy[nocc-1] - lumo) < tol:
            mo_occ = numpy.zeros_like(mo_energy)
            mo_occ[mo_energy<lumo] = 2
            lst = abs(mo_energy-lumo) < tol
            degen = int(lst.sum())
            frac = 2.*numpy.count_nonzero(lst & (mo_occ == 2))/degen
            mo_occ[lst] = frac
            logger.warn(mf, 'fraction occ = %6g  for orbitals %s',
                        frac, numpy.where(lst)[0])
            logger.info(mf, 'HOMO = %.12g  LUMO = %.12g',
                        sort_mo_energy[nocc-1], sort_mo_energy[nocc])
            logger.debug(mf, '  mo_energy = %s', mo_energy)
        else:
            mo_occ = old_get_occ(mo_energy, mo_coeff)
        return mo_occ

    def get_grad(mo_coeff, mo_occ, fock_ao):
        mol = mf.mol
        fock = reduce(numpy.dot, (mo_coeff.T.conj(), fock_ao, mo_coeff))
        fock *= mo_occ.reshape(-1,1)
        nocc = mol.nelectron // 2
        g = fock[:nocc,nocc:].T
        return g.ravel()

    mf.get_occ = get_occ
    mf.get_grad = get_grad
    return mf
frac_occ = frac_occ_

def dynamic_occ_(mf, tol=1e-3):
    assert(isinstance(mf, hf.RHF))
    old_get_occ = mf.get_occ
    def get_occ(mo_energy, mo_coeff=None):
        mol = mf.mol
        nocc = mol.nelectron // 2
        sort_mo_energy = numpy.sort(mo_energy)
        lumo = sort_mo_energy[nocc]
        if abs(sort_mo_energy[nocc-1] - lumo) < tol:
            mo_occ = numpy.zeros_like(mo_energy)
            mo_occ[mo_energy<lumo] = 2
            lst = abs(mo_energy - lumo) < tol
            mo_occ[lst] = 0
            logger.warn(mf, 'set charge = %d', mol.charge+int(lst.sum())*2)
            logger.info(mf, 'HOMO = %.12g  LUMO = %.12g',
                        sort_mo_energy[nocc-1], sort_mo_energy[nocc])
            logger.debug(mf, '  mo_energy = %s', sort_mo_energy)
        else:
            mo_occ = old_get_occ(mo_energy, mo_coeff)
        return mo_occ
    mf.get_occ = get_occ
    return mf
dynamic_occ = dynamic_occ_

def dynamic_level_shift_(mf, factor=1.):
    '''Dynamically change the level shift in each SCF cycle.  The level shift
    value is set to (HF energy change * factor)
    '''
    old_get_fock = mf.get_fock
    last_e = [None]
    def get_fock(h1e, s1e, vhf, dm, cycle=-1, diis=None,
                 diis_start_cycle=None, level_shift_factor=None, damp_factor=None):
        if cycle >= 0 or diis is not None:
            ehf =(numpy.einsum('ij,ji', h1e, dm) +
                  numpy.einsum('ij,ji', vhf, dm) * .5)
            if last_e[0] is not None:
                level_shift_factor = abs(ehf-last_e[0]) * factor
                logger.info(mf, 'Set level shift to %g', level_shift_factor)
            last_e[0] = ehf
        return old_get_fock(h1e, s1e, vhf, dm, cycle, diis, diis_start_cycle,
                            level_shift_factor, damp_factor)
    mf.get_fock = get_fock
    return mf
dynamic_level_shift = dynamic_level_shift_

def float_occ_(mf):
    '''
    For UHF, allowing the Sz value being changed during SCF iteration.
    Determine occupation of alpha and beta electrons based on energy spectrum
    '''
    from pyscf.scf import uhf
    assert(isinstance(mf, uhf.UHF))
    def get_occ(mo_energy, mo_coeff=None):
        mol = mf.mol
        ee = numpy.sort(numpy.hstack(mo_energy))
        n_a = numpy.count_nonzero(mo_energy[0]<(ee[mol.nelectron-1]+1e-3))
        n_b = mol.nelectron - n_a
        if mf.nelec is None:
            nelec = mf.mol.nelec
        else:
            nelec = mf.nelec
        if n_a != nelec[0]:
            logger.info(mf, 'change num. alpha/beta electrons '
                        ' %d / %d -> %d / %d',
                        nelec[0], nelec[1], n_a, n_b)
            mf.nelec = (n_a, n_b)
        return uhf.UHF.get_occ(mf, mo_energy, mo_coeff)
    mf.get_occ = get_occ
    return mf
dynamic_sz_ = float_occ = float_occ_

def symm_allow_occ_(mf, tol=1e-3):
    '''search the unoccupied orbitals, choose the lowest sets which do not
break symmetry as the occupied orbitals'''
    def get_occ(mo_energy, mo_coeff=None):
        mol = mf.mol
        mo_occ = numpy.zeros_like(mo_energy)
        nocc = mol.nelectron // 2
        mo_occ[:nocc] = 2
        if abs(mo_energy[nocc-1] - mo_energy[nocc]) < tol:
            lst = abs(mo_energy - mo_energy[nocc-1]) < tol
            nocc_left = int(lst[:nocc].sum())
            ndocc = nocc - nocc_left
            mo_occ[ndocc:nocc] = 0
            i = ndocc
            nmo = len(mo_energy)
            logger.info(mf, 'symm_allow_occ [:%d] = 2', ndocc)
            while i < nmo and nocc_left > 0:
                deg = (abs(mo_energy[i:i+5]-mo_energy[i]) < tol).sum()
                if deg <= nocc_left:
                    mo_occ[i:i+deg] = 2
                    nocc_left -= deg
                    logger.info(mf, 'symm_allow_occ [%d:%d] = 2, energy = %.12g',
                                i, i+nocc_left, mo_energy[i])
                    break
                else:
                    i += deg
        logger.info(mf, 'HOMO = %.12g, LUMO = %.12g,',
                    mo_energy[nocc-1], mo_energy[nocc])
        logger.debug(mf, '  mo_energy = %s', mo_energy)
        return mo_occ
    mf.get_occ = get_occ
    return mf
symm_allow_occ = symm_allow_occ_

def follow_state_(mf, occorb=None):
    occstat = [occorb]
    old_get_occ = mf.get_occ
    def get_occ(mo_energy, mo_coeff=None):
        if occstat[0] is None:
            mo_occ = old_get_occ(mo_energy, mo_coeff)
        else:
            mo_occ = numpy.zeros_like(mo_energy)
            s = reduce(numpy.dot, (occstat[0].T, mf.get_ovlp(), mo_coeff))
            nocc = mf.mol.nelectron // 2
            #choose a subset of mo_coeff, which maximizes <old|now>
            idx = numpy.argsort(numpy.einsum('ij,ij->j', s, s))
            mo_occ[idx[-nocc:]] = 2
            logger.debug(mf, '  mo_occ = %s', mo_occ)
            logger.debug(mf, '  mo_energy = %s', mo_energy)
        occstat[0] = mo_coeff[:,mo_occ>0]
        return mo_occ
    mf.get_occ = get_occ
    return mf
follow_state = follow_state_

def mom_occ_(mf, occorb, setocc):
    '''Use maximum overlap method to determine occupation number for each orbital in every
    iteration. It can be applied to unrestricted HF/KS and restricted open-shell
    HF/KS.'''
    from pyscf.scf import uhf, rohf
    if isinstance(mf, uhf.UHF):
        coef_occ_a = occorb[0][:, setocc[0]>0]
        coef_occ_b = occorb[1][:, setocc[1]>0]
    elif isinstance(mf, rohf.ROHF):
        if mf.mol.spin != int(numpy.sum(setocc[0]) - numpy.sum(setocc[1])) :
            raise ValueError('Wrong occupation setting for restricted open-shell calculation.') 
        coef_occ_a = occorb[:, setocc[0]>0]
        coef_occ_b = occorb[:, setocc[1]>0]
    else:
        raise AssertionError('Can not support this class of instance.')
    log = logger.Logger(mf.stdout, mf.verbose)
    def get_occ(mo_energy=None, mo_coeff=None):
        if mo_energy is None: mo_energy = mf.mo_energy
        if mo_coeff is None: mo_coeff = mf.mo_coeff
        if isinstance(mf, rohf.ROHF): mo_coeff = numpy.array([mo_coeff, mo_coeff])
        mo_occ = numpy.zeros_like(setocc)
        nocc_a = int(numpy.sum(setocc[0]))
        nocc_b = int(numpy.sum(setocc[1]))
        s_a = reduce(numpy.dot, (coef_occ_a.T, mf.get_ovlp(), mo_coeff[0])) 
        s_b = reduce(numpy.dot, (coef_occ_b.T, mf.get_ovlp(), mo_coeff[1]))
        #choose a subset of mo_coeff, which maximizes <old|now>
        idx_a = numpy.argsort(numpy.einsum('ij,ij->j', s_a, s_a))
        idx_b = numpy.argsort(numpy.einsum('ij,ij->j', s_b, s_b))
        mo_occ[0][idx_a[-nocc_a:]] = 1.
        mo_occ[1][idx_b[-nocc_b:]] = 1.

        if mf.verbose >= logger.DEBUG:
            log.info(' New alpha occ pattern: %s', mo_occ[0])
            log.info(' New beta occ pattern: %s', mo_occ[1])
        if mf.verbose >= logger.DEBUG1:
            if mo_energy.ndim == 2:
                log.info(' Current alpha mo_energy(sorted) = %s', mo_energy[0])
                log.info(' Current beta mo_energy(sorted) = %s', mo_energy[1])
            elif mo_energy.ndim == 1:
                log.info(' Current mo_energy(sorted) = %s', mo_energy)

        if (int(numpy.sum(mo_occ[0])) != nocc_a):
            log.error('mom alpha electron occupation numbers do not match: %d, %d',
                      nocc_a, int(numpy.sum(mo_occ[0])))
        if (int(numpy.sum(mo_occ[1])) != nocc_b):
            log.error('mom alpha electron occupation numbers do not match: %d, %d',
                      nocc_b, int(numpy.sum(mo_occ[1])))

        #output 1-dimension occupation number for restricted open-shell
        if isinstance(mf, rohf.ROHF): mo_occ = mo_occ[0, :] + mo_occ[1, :]
        return mo_occ
    mf.get_occ = get_occ
    return mf
mom_occ = mom_occ_

def project_mo_nr2nr(mol1, mo1, mol2):
    r''' Project orbital coefficients

    .. math::

        |\psi1> = |AO1> C1

        |\psi2> = P |\psi1> = |AO2>S^{-1}<AO2| AO1> C1 = |AO2> C2

        C2 = S^{-1}<AO2|AO1> C1
    '''
    s22 = mol2.intor_symmetric('int1e_ovlp')
    s21 = mole.intor_cross('int1e_ovlp', mol2, mol1)
    return lib.cho_solve(s22, numpy.dot(s21, mo1))

def project_mo_nr2r(mol1, mo1, mol2):
    assert(not mol1.cart)
    s22 = mol2.intor_symmetric('int1e_ovlp_spinor')
    s21 = mole.intor_cross('int1e_ovlp_sph', mol2, mol1)

    ua, ub = sph.real2spinor_whole(mol2)
    s21 = numpy.dot(ua.T.conj(), s21) + numpy.dot(ub.T.conj(), s21) # (*)
    # mo2: alpha, beta have been summed in Eq. (*)
    # so DM = mo2[:,:nocc] * 1 * mo2[:,:nocc].H
    mo2 = numpy.dot(s21, mo1)
    return lib.cho_solve(s22, mo2)

def project_mo_r2r(mol1, mo1, mol2):
    s22 = mol2.intor_symmetric('int1e_ovlp_spinor')
    t22 = mol2.intor_symmetric('int1e_spsp_spinor')
    s21 = mole.intor_cross('int1e_ovlp_spinor', mol2, mol1)
    t21 = mole.intor_cross('int1e_spsp_spinor', mol2, mol1)
    n2c = s21.shape[1]
    pl = lib.cho_solve(s22, s21)
    ps = lib.cho_solve(t22, t21)
    return numpy.vstack((numpy.dot(pl, mo1[:n2c]),
                         numpy.dot(ps, mo1[n2c:])))


def remove_linear_dep_(mf, threshold=1e-8):
    def eigh(h, s):
        d, t = numpy.linalg.eigh(s)
        x = t[:,d>threshold] / numpy.sqrt(d[d>threshold])
        xhx = reduce(numpy.dot, (x.T.conj(), h, x))
        e, c = numpy.linalg.eigh(xhx)
        c = numpy.dot(x, c)
        return e, c
    mf._eigh = eigh
    return mf
remove_linear_dep = remove_linear_dep_

def convert_to_uhf(mf, out=None, convert_df=False):
    '''Convert the given mean-field object to the unrestricted HF/KS object

    Args:
        mf : SCF object

    Kwargs
        convert_df : bool
            Whether to convert the DF-SCF object to the normal SCF object.
            This conversion is not applied by default.

    Returns:
        An unrestricted SCF object
    '''
    from pyscf import scf
    from pyscf import dft
    assert(isinstance(mf, hf.SCF))

    logger.debug(mf, 'Converting %s to UHF', mf.__class__)

    def update_mo_(mf, mf1):
        _keys = mf._keys.union(mf1._keys)
        mf1.__dict__.update(mf.__dict__)
        mf1._keys = _keys
        if mf.mo_energy is not None:
            mf1.mo_energy = numpy.array((mf.mo_energy, mf.mo_energy))
            mf1.mo_coeff = (mf.mo_coeff, mf.mo_coeff)
            if hasattr(mf.mo_coeff, 'orbsym'):
                orbsym = mf.mo_coeff.orbsym
                mf1.mo_coeff = (lib.tag_array(mf1.mo_coeff[0], orbsym=orbsym),
                                lib.tag_array(mf1.mo_coeff[1], orbsym=orbsym))
            mf1.mo_occ = numpy.array((mf.mo_occ>0, mf.mo_occ==2), dtype=numpy.double)
        return mf1

    if out is not None:
        assert(isinstance(out, scf.uhf.UHF))
        if isinstance(mf, scf.uhf.UHF):
            out.__dict.__update(mf)
        else:  # RHF
            out = update_mo_(mf, out)

    elif isinstance(mf, scf.uhf.UHF):
        out = copy.copy(mf)
    elif isinstance(mf, scf.ghf.GHF):
        raise NotImplementedError
    else:
        known_cls = {scf.hf.RHF        : scf.uhf.UHF,
                     scf.rohf.ROHF     : scf.uhf.UHF,
                     scf.hf_symm.RHF   : scf.uhf_symm.UHF,
                     scf.hf_symm.ROHF  : scf.uhf_symm.UHF,
                     dft.rks.RKS       : dft.uks.UKS,
                     dft.roks.ROKS     : dft.uks.UKS,
                     dft.rks_symm.RKS  : dft.uks_symm.UKS,
                     dft.rks_symm.ROKS : dft.uks_symm.UKS}
        out = update_mo_(mf, _recursive_patch(mf.__class__, known_cls,
                                              mf.mol, convert_df))

    if getattr(out, 'with_df', None) and convert_df:
        out.with_df = False
    return out

def _recursive_patch(cls, known_class, mol, convert_df=None):
    if convert_df and 'DFHF' in cls.__name__:
        cls = cls.__base__

    if cls in known_class:
        as_class = known_class[cls]
        if as_class is None:
            raise NotImplementedError('conversion from %s' % cls)
        return as_class(mol)
    elif cls is object:
        raise RuntimeError('Unknown SCF object')
    else:
        return cls(_recursive_patch(cls.__base__, known_class, mol, convert_df))

def convert_to_rhf(mf, out=None, convert_df=False):
    '''Convert the given mean-field object to the restricted HF/KS object

    Args:
        mf : SCF object

    Kwargs
        convert_df : bool
            Whether to convert the DF-SCF object to the normal SCF object.
            This conversion is not applied by default.

    Returns:
        An unrestricted SCF object
    '''
    from pyscf import scf
    from pyscf import dft
    assert(isinstance(mf, hf.SCF))

    logger.debug(mf, 'Converting %s to RHF', mf.__class__)

    def update_mo_(mf, mf1):
        _keys = mf._keys.union(mf1._keys)
        mf1.__dict__.update(mf.__dict__)
        mf1._keys = _keys
        if mf.mo_energy is not None:
            mf1.mo_energy = mf.mo_energy[0]
            mf1.mo_coeff =  mf.mo_coeff[0]
            if hasattr(mf.mo_coeff[0], 'orbsym'):
                mf1.mo_coeff = lib.tag_array(mf1.mo_coeff, orbsym=mf.mo_coeff[0].orbsym)
            mf1.mo_occ = mf.mo_occ[0] + mf.mo_occ[1]
        return mf1

    if out is not None:
        assert(isinstance(out, scf.hf.RHF))
        if isinstance(mf, scf.hf.RHF):
            out.__dict.__update(mf)
        else:  # UHF
            out = update_mo_(mf, out)

    elif isinstance(mf, scf.hf.RHF):
        out = copy.copy(mf)
    elif isinstance(mf, scf.ghf.GHF):
        raise NotImplementedError
    else:
        known_cls = {scf.uhf.UHF      : scf.rohf.ROHF,
                     scf.uhf_symm.UHF : scf.hf_symm.ROHF,
                     dft.uks.UKS      : dft.roks.ROKS,
                     dft.uks_symm.UKS : dft.rks_symm.ROKS}
        out = update_mo_(mf, _recursive_patch(mf.__class__, known_cls, mf.mol,
                                              convert_df))

    if getattr(out, 'with_df', None) and convert_df:
        out.with_df = False
    return out

def convert_to_ghf(mf, out=None, convert_df=False):
    '''Convert the given mean-field object to the generalized HF/KS object

    Args:
        mf : SCF object

    Kwargs
        convert_df : bool
            Whether to convert the DF-SCF object to the normal SCF object.
            This conversion is not applied by default.

    Returns:
        An generalized SCF object
    '''
    from pyscf import scf
    from pyscf import dft
    assert(isinstance(mf, hf.SCF))

    logger.debug(mf, 'Converting %s to GHF', mf.__class__)

    def update_mo_(mf, mf1):
        _keys = mf._keys.union(mf1._keys)
        mf1.__dict__.update(mf.__dict__)
        mf1._keys = _keys
        if mf.mo_energy is not None:
            if isinstance(mf, scf.hf.RHF):
                nao, nmo = mf.mo_coeff.shape
                orbspin = get_ghf_orbspin(mf.mo_energy, mf.mo_occ, True)

                mf1.mo_energy = numpy.empty(nmo*2)
                mf1.mo_energy[orbspin==0] = mf.mo_energy
                mf1.mo_energy[orbspin==1] = mf.mo_energy
                mf1.mo_occ = numpy.empty(nmo*2)
                mf1.mo_occ[orbspin==0] = mf.mo_occ > 0
                mf1.mo_occ[orbspin==1] = mf.mo_occ == 2

                mo_coeff = numpy.zeros((nao*2,nmo*2), dtype=mf.mo_coeff.dtype)
                mo_coeff[:nao,orbspin==0] = mf.mo_coeff
                mo_coeff[nao:,orbspin==1] = mf.mo_coeff
                if hasattr(mf.mo_coeff[0], 'orbsym'):
                    orbsym = numpy.zeros_like(orbspin)
                    orbsym[orbspin==0] = mf.mo_coeff.orbsym
                    orbsym[orbspin==1] = mf.mo_coeff.orbsym
                    mo_coeff = lib.tag_array(mo_coeff, orbsym=orbsym)
                mf1.mo_coeff = lib.tag_array(mo_coeff, orbspin=orbspin)

            else: # UHF
                nao, nmo = mf.mo_coeff[0].shape
                orbspin = get_ghf_orbspin(mf.mo_energy, mf.mo_occ, False)

                mf1.mo_energy = numpy.empty(nmo*2)
                mf1.mo_energy[orbspin==0] = mf.mo_energy[0]
                mf1.mo_energy[orbspin==1] = mf.mo_energy[1]
                mf1.mo_occ = numpy.empty(nmo*2)
                mf1.mo_occ[orbspin==0] = mf.mo_occ[0]
                mf1.mo_occ[orbspin==1] = mf.mo_occ[1]

                mo_coeff = numpy.zeros((nao*2,nmo*2), dtype=mf.mo_coeff[0].dtype)
                mo_coeff[:nao,orbspin==0] = mf.mo_coeff[0]
                mo_coeff[nao:,orbspin==1] = mf.mo_coeff[1]
                if hasattr(mf.mo_coeff[0], 'orbsym'):
                    orbsym = numpy.zeros_like(orbspin)
                    orbsym[orbspin==0] = mf.mo_coeff[0].orbsym
                    orbsym[orbspin==1] = mf.mo_coeff[1].orbsym
                    mo_coeff = lib.tag_array(mo_coeff, orbsym=orbsym)
                mf1.mo_coeff = lib.tag_array(mo_coeff, orbspin=orbspin)
        return mf1

    if out is not None:
        assert(isinstance(out, scf.ghf.GHF))
        if isinstance(mf, scf.ghf.GHF):
            out.__dict.__update(mf)
        else:
            out = update_mo_(mf, out)

    elif isinstance(mf, scf.ghf.GHF):
        out = copy.copy(mf)

    else:
        known_cls = {scf.hf.RHF        : scf.ghf.GHF,
                     scf.rohf.ROHF     : scf.ghf.GHF,
                     scf.uhf.UHF       : scf.ghf.GHF,
                     scf.hf_symm.RHF   : scf.ghf_symm.GHF,
                     scf.hf_symm.ROHF  : scf.ghf_symm.GHF,
                     scf.uhf_symm.UHF  : scf.ghf_symm.GHF,
                     dft.rks.RKS       : None,
                     dft.roks.ROKS     : None,
                     dft.uks.UKS       : None,
                     dft.rks_symm.RKS  : None,
                     dft.rks_symm.ROKS : None,
                     dft.uks_symm.UKS  : None}
        out = update_mo_(mf, _recursive_patch(mf.__class__, known_cls, mf.mol,
                                              convert_df))

    if getattr(out, 'with_df', None) and convert_df:
        out.with_df = False
    return out

def get_ghf_orbspin(mo_energy, mo_occ, is_rhf=None):
    '''Spin of each GHF orbital when the GHF orbitals are converted from
    RHF/UHF orbitals

    For RHF orbitals, the orbspin corresponds to first occupied orbitals then
    unoccupied orbitals.  In the occupied orbital space, if degenerated, first
    alpha then beta, last the (open-shell) singly occupied (alpha) orbitals In
    the unoccupied orbital space, first the (open-shell) unoccupied (beta)
    orbitals if applicable, then alpha and beta orbitals

    For UHF orbitals, the orbspin corresponds to first occupied orbitals then
    unoccupied orbitals.
    '''
    if is_rhf is None:  # guess whether the orbitals are RHF orbitals
        is_rhf = mo_energy[0].ndim == 0

    if is_rhf:
        nmo = mo_energy.size
        nocc = numpy.count_nonzero(mo_occ >0)
        nvir = nmo - nocc
        ndocc = numpy.count_nonzero(mo_occ==2)
        nsocc = nocc - ndocc
        orbspin = numpy.array([0,1]*ndocc + [0]*nsocc + [1]*nsocc + [0,1]*nvir)
    else:
        nmo = mo_energy[0].size
        nocca = numpy.count_nonzero(mo_occ[0]>0)
        nvira = nmo - nocca
        noccb = numpy.count_nonzero(mo_occ[1]>0)
        nvirb = nmo - noccb
        # round(6) to avoid numerical uncertainty in degeneracy
        es = numpy.append(mo_energy[0][mo_occ[0] >0],
                          mo_energy[1][mo_occ[1] >0])
        oidx = numpy.argsort(es.round(6))
        es = numpy.append(mo_energy[0][mo_occ[0]==0],
                          mo_energy[1][mo_occ[1]==0])
        vidx = numpy.argsort(es.round(6))
        orbspin = numpy.append(numpy.array([0]*nocca+[1]*noccb)[oidx],
                               numpy.array([0]*nvira+[1]*nvirb)[vidx])
    return orbspin
