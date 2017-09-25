#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
domain decomposition PCM
(In testing)

See also
JCP, 144, 054101
JCP, 144, 160901
'''

import ctypes
import numpy
from pyscf import lib
from pyscf.lib import logger
from pyscf import gto
from pyscf import df
from pyscf.dft import gen_grid, numint
from pyscf.data import radii
from pyscf.pcm import ddcosmo

ddpcm_for_scf = ddcosmo.ddcosmo_for_scf

def gen_ddpcm_solver(pcmobj, grids=None, verbose=None):
    mol = pcmobj.mol
    if grids is None:
        grids = gen_grid.Grids(mol)
        grids.level = pcmobj.becke_grids_level
        grids.build(with_non0tab=True)

    natm = mol.natm
    lmax = pcmobj.lmax

    r_vdw = ddcosmo.get_atomic_radii(pcmobj)
    coords_1sph, weights_1sph = ddcosmo.make_grids_one_sphere(pcmobj.lebedev_order)
    ylm_1sph = numpy.vstack(ddcosmo.make_ylm(coords_1sph, lmax))

    fi = ddcosmo.make_fi(pcmobj, r_vdw)
    ui = 1 - fi
    ui[ui<0] = 0
    nexposed = numpy.count_nonzero(ui==1)
    nbury = numpy.count_nonzero(ui==0)
    on_shell = numpy.count_nonzero(ui>0) - nexposed
    logger.debug(pcmobj, 'Num points exposed %d', nexposed)
    logger.debug(pcmobj, 'Num points buried %d', nbury)
    logger.debug(pcmobj, 'Num points on shell %d', on_shell)

    nlm = (lmax+1)**2
    Lmat = ddcosmo.make_L(pcmobj, r_vdw, ylm_1sph, fi)
    Lmat = Lmat.reshape(natm*nlm,-1)

    Amat = make_A(pcmobj, r_vdw, ylm_1sph, ui).reshape(natm*nlm,-1)
    fac = 2*numpy.pi * (pcmobj.eps+1) / (pcmobj.eps-1)
    A_diele = Amat + fac * numpy.eye(natm*nlm)
    A_inf = Amat + 2*numpy.pi * numpy.eye(natm*nlm)

    cached_pol = ddcosmo.cache_fake_multipoler(grids, r_vdw, lmax)

    def gen_vind(dm):
        v_phi = ddcosmo.make_phi(pcmobj, dm, r_vdw, ui, grids)
        phi = -numpy.einsum('n,xn,jn,jn->jx', weights_1sph, ylm_1sph,
                            ui, v_phi)
        phi = numpy.linalg.solve(A_diele, A_inf.dot(phi.ravel()))

        L_X = numpy.linalg.solve(Lmat, phi.ravel()).reshape(natm,-1)
        psi, vmat = ddcosmo.make_psi_vmat(pcmobj, dm, r_vdw, ui, grids,
                                          ylm_1sph, cached_pol, L_X, Lmat)
        dielectric = pcmobj.eps
        f_epsilon = (dielectric-1.)/dielectric
        epcm = .5 * f_epsilon * numpy.einsum('jx,jx', psi, L_X)
        return epcm, vmat
    return gen_vind

def regularize_xt(t, eta, scale=1):
    eta *= scale
    xt = numpy.zeros_like(t)
    inner = t <= 1-eta
    on_shell = (1-eta < t) & (t < 1)
    xt[inner] = 1
    ti = t[on_shell] - eta*.5
# JCP, 144, 054101
    xt[on_shell] = 1./eta**4 * (1-ti)**2 * (ti-1+2*eta)**2
    return xt

def make_A(pcmobj, r_vdw, ylm_1sph, ui):
    # Part of A matrix defined in JCP, 144, 054101, Eq (43), (44)
    mol = pcmobj.mol
    natm = mol.natm
    lmax = pcmobj.lmax
    eta = pcmobj.eta
    nlm = (lmax+1)**2

    coords_1sph, weights_1sph = ddcosmo.make_grids_one_sphere(pcmobj.lebedev_order)
    ngrid_1sph = weights_1sph.size
    atom_coords = mol.atom_coords()
    ylm_1sph = ylm_1sph.reshape(nlm,ngrid_1sph)
    Amat = numpy.zeros((natm,nlm,natm,nlm))

    for ja in range(natm):
        # w_u = precontract w_n U_j
        w_u = weights_1sph * ui[ja]
        p1 = 0
        for l in range(lmax+1):
            fac = 2*numpy.pi/(l*2+1)
            p0, p1 = p1, p1 + (l*2+1)
            a = numpy.einsum('xn,n,mn->xm', ylm_1sph, w_u, ylm_1sph[p0:p1])
            Amat[ja,:,ja,p0:p1] += -fac * a

        for ka in ddcosmo.atoms_with_vdw_overlap(ja, atom_coords, r_vdw):
            vjk = r_vdw[ja] * coords_1sph + atom_coords[ja] - atom_coords[ka]
            rjk = lib.norm(vjk, axis=1)
            pol = ddcosmo.make_multipole(vjk, lmax)
            p1 = 0
            weights = w_u / rjk**(l*2+1)
            for l in range(lmax+1):
                fac = 4*numpy.pi*l/(l*2+1) * r_vdw[ka]**(l+1)
                p0, p1 = p1, p1 + (l*2+1)
                a = numpy.einsum('xn,n,mn->xm', ylm_1sph, weights, pol[l])
                Amat[ja,:,ka,p0:p1] += -fac * a
    return Amat

class DDPCM(ddcosmo.DDCOSMO):
    gen_solver = as_solver = gen_ddpcm_solver

    def regularize_xt(self, t, eta, scale=1):
        return regularize_xt(t, eta, scale)


if __name__ == '__main__':
    from pyscf import scf
    mol = gto.M(atom='H 0 0 0; H 0 1 1.2; H 1. .1 0; H .5 .5 1')
    numpy.random.seed(1)

    nao = mol.nao_nr()
    dm = numpy.random.random((nao,nao))
    dm = dm + dm.T
    #dm = scf.RHF(mol).run().make_rdm1()
    e, vmat = DDPCM(mol).kernel(dm)
    print(e + 1.2446306643473923)
    print(lib.finger(vmat) - 0.77873361914445294)

    mol = gto.Mole()
    mol.atom = ''' O                  0.00000000    0.00000000   -0.11081188
                   H                 -0.00000000   -0.84695236    0.59109389
                   H                 -0.00000000    0.89830571    0.52404783 '''
    mol.basis = '3-21g' #cc-pvdz'
    mol.build()
    cm = DDPCM(mol)
    cm.verbose = 4
    mf = ddpcm_for_scf(scf.RHF(mol), cm)#.newton()
    mf.verbose = 4
    mf.kernel()
