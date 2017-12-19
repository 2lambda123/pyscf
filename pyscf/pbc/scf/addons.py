#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#         Timothy Berkelbach <tim.berkelbach@gmail.com>
#

import sys
import copy
from functools import reduce
import numpy
import scipy.linalg
import scipy.special
import scipy.optimize
from pyscf import lib
from pyscf.pbc import gto as pbcgto
from pyscf.lib import logger


def project_mo_nr2nr(cell1, mo1, cell2, kpts=None):
    r''' Project orbital coefficients

    .. math::

        |\psi1> = |AO1> C1

        |\psi2> = P |\psi1> = |AO2>S^{-1}<AO2| AO1> C1 = |AO2> C2

        C2 = S^{-1}<AO2|AO1> C1
    '''
    s22 = cell2.pbc_intor('int1e_ovlp_sph', hermi=1, kpts=kpts)
    s21 = pbcgto.intor_cross('int1e_ovlp_sph', cell2, cell1, kpts=kpts)
    if kpts is None or numpy.shape(kpts) == (3,):  # A single k-point
        return scipy.linalg.solve(s22, s21.dot(mo1), sym_pos=True)
    else:
        assert(len(kpts) == len(mo1))
        return [scipy.linalg.solve(s22[k], s21[k].dot(mo1[k]), sym_pos=True)
                for k, kpt in enumerate(kpts)]


def smearing_(mf, sigma=None, method='fermi'):
    '''Fermi-Dirac or Gaussian smearing'''
    from pyscf.scf import uhf
    from pyscf.pbc.scf import khf
    mf_class = mf.__class__
    is_uhf = isinstance(mf, uhf.UHF)
    is_khf = isinstance(mf, khf.KSCF)
    cell_nelec = mf.cell.nelectron

    def fermi_smearing_occ(m, mo_energy_kpts, sigma):
        occ = numpy.zeros_like(mo_energy_kpts)
        de = (mo_energy_kpts - m) / sigma
        occ[de<40] = 1./(numpy.exp(de[de<40])+1.)
        return occ
    def gaussian_smearing_occ(m, mo_energy_kpts, sigma):
        return .5 - .5*scipy.special.erf((mo_energy_kpts-m)/sigma)

    def partition_occ(mo_occ, mo_energy_kpts):
        mo_occ_kpts = []
        p1 = 0
        for e in mo_energy_kpts:
            p0, p1 = p1, p1 + e.size
            occ = mo_occ[p0:p1]
            mo_occ_kpts.append(occ)
        return mo_occ_kpts

    def get_occ(mo_energy_kpts=None, mo_coeff_kpts=None):
        '''Label the occupancies for each orbital for sampled k-points.

        This is a k-point version of scf.hf.SCF.get_occ
        '''
        mo_occ_kpts = mf_class.get_occ(mf, mo_energy_kpts, mo_coeff_kpts)
        if mf.sigma == 0 or not mf.sigma or not mf.smearing_method:
            return mo_occ_kpts

        if is_khf:
            nkpts = len(mf.kpts)
        else:
            nkpts = 1
        if is_uhf:
            nocc = cell_nelec * nkpts
            mo_es = numpy.append(numpy.hstack(mo_energy_kpts[0]),
                                 numpy.hstack(mo_energy_kpts[1]))
        else:
            nocc = cell_nelec * nkpts // 2
            mo_es = numpy.hstack(mo_energy_kpts)

        if mf.smearing_method.lower() == 'fermi':  # Fermi-Dirac smearing
            f_occ = fermi_smearing_occ
        else:  # Gaussian smearing
            f_occ = gaussian_smearing_occ

        mo_energy = numpy.sort(mo_es.ravel())
        fermi = mo_energy[nocc-1]
        sigma = mf.sigma
        def nelec_cost_fn(m):
            mo_occ_kpts = f_occ(m, mo_es, sigma)
            if not is_uhf:
                mo_occ_kpts *= 2
            return ( mo_occ_kpts.sum()/nkpts - cell_nelec )**2
        res = scipy.optimize.minimize(nelec_cost_fn, fermi, method='Powell')
        mu = res.x
        mo_occs = f = f_occ(mu, mo_es, sigma)

        # See https://www.vasp.at/vasp-workshop/slides/k-points.pdf
        if mf.smearing_method.lower() == 'fermi':
            f = f[(f>0) & (f<1)]
            mf.entropy = -(f*numpy.log(f) + (1-f)*numpy.log(1-f)).sum() / nkpts
        else:
            mf.entropy = (numpy.exp(-((mo_es-mu)/mf.sigma)**2).sum()
                          / (2*numpy.sqrt(numpy.pi)) / nkpts)
        if not is_uhf:
            mo_occs *= 2
            mf.entropy *= 2

        # DO NOT use numpy.array for mo_occ_kpts and mo_energy_kpts, they may
        # have different dimensions for different k-points
        if is_uhf:
            if is_khf:
                nao_tot = mo_occs.size//2
                mo_occ_kpts =(partition_occ(mo_occs[:nao_tot], mo_energy_kpts[0]),
                              partition_occ(mo_occs[nao_tot:], mo_energy_kpts[1]))
            else:
                mo_occ_kpts = partition_occ(mo_occs, mo_energy_kpts)
        else:
            if is_khf:
                mo_occ_kpts = partition_occ(mo_occs, mo_energy_kpts)
            else:
                mo_occ_kpts = mo_occs

        logger.debug(mf, '    Fermi level %g  Sum mo_occ_kpts = %s  should equal nelec = %s',
                     fermi, mo_occs.sum()/nkpts, cell_nelec)
        logger.info(mf, '    sigma = %g  Optimized mu = %.12g  entropy = %.12g',
                    mf.sigma, mu, mf.entropy)

        return mo_occ_kpts

    def get_grad_tril(mo_coeff_kpts, mo_occ_kpts, fock):
        if is_khf:
            grad_kpts = []
            for k, mo in enumerate(mo_coeff_kpts):
                f_mo = reduce(numpy.dot, (mo.T.conj(), fock[k], mo))
                nmo = f_mo.shape[0]
                grad_kpts.append(f_mo[numpy.tril_indices(nmo, -1)])
            return numpy.hstack(grad_kpts)
        else:
            f_mo = reduce(numpy.dot, (mo_coeff_kpts.T.conj(), fock, mo_coeff_kpts))
            nmo = f_mo.shape[0]
            return f_mo[numpy.tril_indices(nmo, -1)]

    def get_grad(mo_coeff_kpts, mo_occ_kpts, fock=None):
        if mf.sigma == 0 or not mf.sigma or not mf.smearing_method:
            return mf_class.get_grad(mf, mo_coeff_kpts, mo_occ_kpts, fock)
        if fock is None:
            dm1 = mf.make_rdm1(mo_coeff_kpts, mo_occ_kpts)
            fock = mf.get_hcore() + mf.get_veff(mf.cell, dm1)
        if is_uhf:
            ga = get_grad_tril(mo_coeff_kpts[0], mo_occ_kpts[0], fock[0])
            gb = get_grad_tril(mo_coeff_kpts[1], mo_occ_kpts[1], fock[1])
            return numpy.hstack((ga,gb))
        else:
            return get_grad_tril(mo_coeff_kpts, mo_occ_kpts, fock)

    def energy_tot(dm_kpts=None, h1e_kpts=None, vhf_kpts=None):
        e_tot = mf.energy_elec(dm_kpts, h1e_kpts, vhf_kpts)[0] + mf.energy_nuc()
        if (mf.sigma and mf.smearing_method and
            mf.entropy is not None and mf.verbose >= logger.INFO):
            mf.e_free = e_tot - mf.sigma * mf.entropy
            mf.e_zero = e_tot - mf.sigma * mf.entropy * .5
            logger.info(mf, '    Total E(T) = %.15g  Free energy = %.15g  E0 = %.15g',
                        e_tot, mf.e_free, mf.e_zero)
        return e_tot

    mf.sigma = sigma
    mf.smearing_method = method
    mf.entropy = None
    mf.e_free = None
    mf.e_zero = None
    mf._keys = mf._keys.union(['sigma', 'smearing_method',
                               'entropy', 'e_free', 'e_zero'])

    mf.get_occ = get_occ
    mf.energy_tot = energy_tot
    mf.get_grad = get_grad
    return mf


def canonical_occ_(mf):
    '''Label the occupancies for each orbital for sampled k-points.
    This is for KUHF objects.
    Each k-point has a fixed number of up and down electrons in this,
    which results in a finite size error for metallic systems
    but can accelerate convergence '''
    from pyscf.pbc.scf import kuhf
    assert(isinstance(mf, kuhf.KUHF))

    def get_occ(mo_energy_kpts=None,mo_coeff=None):
        if mo_energy_kpts is None: mo_energy_kpts = mf.mo_energy
        mo_energy_kpts = numpy.asarray(mo_energy_kpts)
        mo_occ_kpts = numpy.zeros_like(mo_energy_kpts)
        logger.debug1(mf, "mo_occ_kpts.shape", mo_occ_kpts.shape)

        nkpts = len(mo_energy_kpts[0])
        homo=[-1e8,-1e8]
        lumo=[1e8,1e8]

        for k in range(nkpts):
            for s in [0,1]:
                e_idx = numpy.argsort(mo_energy_kpts[s,k])
                e_sort = mo_energy_kpts[s,k][e_idx]
                n = mf.nelec[s]
                mo_occ_kpts[s,k,e_idx[:n]]=1
                homo[s]=max(homo[s],e_sort[n-1])
                lumo[s]=min(lumo[s],e_sort[n])

        for nm,s in zip(['alpha','beta'],[0,1]):
            logger.info(mf, nm+' HOMO = %.12g  LUMO = %.12g', homo[s], lumo[s])
            if homo[s] > lumo[s]:
                logger.warn(mf, "WARNING! HOMO is greater than LUMO! This may result in errors with canonical occupation.")

        return mo_occ_kpts

    mf.get_occ=get_occ
    return mf
canonical_occ=canonical_occ_


def convert_to_uhf(mf, out=None):
    '''Convert the given mean-field object to the corresponding unrestricted
    HF/KS object
    '''
    from pyscf import scf as mol_scf
    from pyscf.pbc import scf
    from pyscf.pbc import dft

    if out is None:
        scf_class = ((dft.krks.KRKS, dft.kuks.KUKS),
                     (scf.khf.KRHF , scf.kuhf.KUHF),
                     (dft.rks.RKS  , dft.uks.UKS  ),
                     (scf.hf.RHF   , scf.uhf.UHF  ))

        if isinstance(mf, (scf.uhf.UHF, scf.kuhf.KUHF)):
            return copy.copy(mf)

        else:
            for cls, newcls in scf_class:
                if isinstance(mf, cls):
                    out = newcls(mf.cell)
                    break
            if out is None:
                raise RuntimeError('Unsupported SCF class %s' % mf)
    else:
        assert(isinstance(out, (scf.uhf.UHF, scf.kuhf.KUHF)))

    return mol_scf.addons.convert_to_uhf(mf, out)

def convert_to_rhf(mf, out=None):
    '''Convert the given mean-field object to the corresponding restricted
    HF/KS object
    '''
    from pyscf import scf as mol_scf
    from pyscf.pbc import scf
    from pyscf.pbc import dft

    if out is None:
        scf_class = ((dft.kuks.KUKS, dft.krks.KRKS),
                     (scf.kuhf.KUHF, scf.khf.KRHF ),
                     (dft.uks.UKS  , dft.rks.RKS  ),
                     (scf.uhf.UHF  , scf.hf.RHF   ))

        if isinstance(mf, (scf.hf.RHF, scf.khf.KRHF)):
            return copy.copy(mf)

        else:
            for cls, newcls in scf_class:
                if isinstance(mf, cls):
                    out = newcls(mf.cell)
                    break
            if out is None:
                raise RuntimeError('Unsupported SCF class %s' % mf)

    else:
        assert(isinstance(out, (scf.hf.RHF, scf.khf.KRHF)))

    return mol_scf.addons.convert_to_rhf(mf, out)

def convert_to_ghf(mf, out=None, convert_df=None):
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
    from pyscf.scf.addons import get_ghf_orbspin
    from pyscf import scf as mol_scf
    from pyscf.pbc import scf

    if isinstance(mf, scf.ghf.GHF):
        if out is None:
            return copy.copy(mf)
        else:
            assert(isinstance(out, (scf.ghf.GHF, scf.ghf.KGHF)))
            out.__dict__.update(mf.__dict__)
            return out

    elif isinstance(mf, scf.khf.KSCF):

        def update_mo_(mf, mf1):
            _keys = mf._keys.union(mf1._keys)
            mf1.__dict__.update(mf.__dict__)
            mf1._keys = _keys
            if mf.mo_energy is not None:
                mf1.mo_energy = []
                mf1.mo_occ = []
                mf1.mo_coeff = []
                nkpts = len(mf.kpts)
                is_rhf = isinstance(mf, scf.hf.RHF)
                for k in range(nkpts):
                    if is_rhf:
                        mo_a = mo_b = mf.mo_coeff[k]
                        ea = eb = mf.mo_energy[k]
                        occa = mf.mo_occ[k] > 0
                        occb = mf.mo_occ[k] == 2
                        orbspin = get_ghf_orbspin(ea, mf.mo_occ[k], True)
                    else:
                        mo_a, mo_b = mf.mo_coeff[k]
                        ea, eb = mf.mo_energy[k]
                        occa, occb = mf.mo_occ[k]
                        orbspin = get_ghf_orbspin((ea, eb), (occa, occb), False)

                    nao, nmo = mo_a.shape

                    mo_energy = numpy.empty(nmo*2)
                    mo_energy[orbspin==0] = ea
                    mo_energy[orbspin==1] = eb
                    mo_occ = numpy.empty(nmo*2)
                    mo_occ[orbspin==0] = occa
                    mo_occ[orbspin==1] = occb

                    mo_coeff = numpy.zeros((nao*2,nmo*2), dtype=mo_a.dtype)
                    mo_coeff[:nao,orbspin==0] = mo_a
                    mo_coeff[nao:,orbspin==1] = mo_b
                    mo_coeff = lib.tag_array(mo_coeff, orbspin=orbspin)

                    mf1.mo_energy.append(mo_energy)
                    mf1.mo_occ.append(mo_occ)
                    mf1.mo_coeff.append(mo_coeff)

            return mf1

        return update_mo_(mf, scf.kghf.KGHF(mf.cell))

    else:
        out = scf.ghf.GHF(mf.cell)
        return mol_scf.addons.convert_to_ghf(mf, out)

def convert_to_khf(mf, out=None):
    '''Convert gamma point SCF object to k-point SCF object
    '''
    raise NotImplementedError


if __name__ == '__main__':
    import pyscf.pbc.scf as pscf
    cell = pbcgto.Cell()
    cell.atom = '''
    He 0 0 1
    He 1 0 1
    '''
    cell.basis = 'ccpvdz'
    cell.a = numpy.eye(3) * 4
    cell.mesh = [17] * 3
    cell.verbose = 4
    cell.build()
    nks = [2,1,1]
    mf = pscf.KUHF(cell, cell.make_kpts(nks))
    mf = smearing_(mf, .1) # -5.86052594663696 
    #mf = smearing_(mf, .1, method='gauss')
    mf.kernel()
