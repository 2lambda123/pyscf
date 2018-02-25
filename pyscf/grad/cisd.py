#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
CISD analytical nuclear gradients
'''

from pyscf import lib
from pyscf.lib import logger
from pyscf.scf import rhf_grad
from pyscf.ci import cisd
from pyscf.grad import ccsd as ccsd_grad


def kernel(myci, civec=None, eris=None, atmlst=None, mf_grad=None,
           verbose=logger.INFO):
    if civec is None: civec = mycc.ci
    nocc = myci.nocc
    nmo = myci.nmo
    d1 = cisd._gamma1_intermediates(myci, civec, nmo, nocc)
    fd2intermediate = lib.H5TmpFile()
    d2 = cisd._gamma2_outcore(myci, civec, nmo, nocc, fd2intermediate, True)
    t1 = t2 = l1 = l2 = civec
    return ccsd_grad.kernel(myci, t1, t2, l1, l2, eris, atmlst, mf_grad,
                            d1, d2, verbose)


def as_scanner(grad_ci):
    '''Generating a nuclear gradients scanner/solver (for geometry optimizer).

    The returned solver is a function. This function requires one argument
    "mol" as input and returns total CISD energy.

    The solver will automatically use the results of last calculation as the
    initial guess of the new calculation.  All parameters assigned in the
    CISD and the underlying SCF objects (conv_tol, max_memory etc) are
    automatically applied in the solver.

    Note scanner has side effects.  It may change many underlying objects
    (_scf, with_df, with_x2c, ...) during calculation.

    Examples::

        >>> from pyscf import gto, scf, ci
        >>> mol = gto.M(atom='H 0 0 0; F 0 0 1')
        >>> ci_scanner = ci.CISD(scf.RHF(mol)).nuc_grad_method().as_scanner()
        >>> e_tot, grad = ci_scanner(gto.M(atom='H 0 0 0; F 0 0 1.1'))
        >>> e_tot, grad = ci_scanner(gto.M(atom='H 0 0 0; F 0 0 1.5'))
    '''
    logger.info(grad_ci, 'Set nuclear gradients of %s as a scanner', grad_ci.__class__)
    class CISD_GradScanner(grad_ci.__class__, lib.GradScanner):
        def __init__(self, g):
            self.__dict__.update(g.__dict__)
            self._ci = grad_ci._ci.as_scanner()
        def __call__(self, mol, **kwargs):
            ci_scanner = self._ci
            ci_scanner(mol)
            mf_grad = ci_scanner._scf.nuc_grad_method()
            de = self.kernel(ci_scanner.ci, mf_grad=mf_grad)
            return ci_scanner.e_tot, de
        @property
        def converged(self):
            ci_scanner = self._ci
            return all((ci_scanner._scf.converged, ci_scanner.converged))
    return CISD_GradScanner(grad_ci)

class Gradients(lib.StreamObject):
    def __init__(self, myci):
        self._ci = myci
        self.mol = myci.mol
        self.stdout = myci.stdout
        self.verbose = myci.verbose
        self.atmlst = range(myci.mol.natm)
        self.de = None

    def kernel(self, civec=None, eris=None, atmlst=None,
               mf_grad=None, verbose=None, _kern=kernel):
        log = logger.new_logger(self, verbose)
        if civec is None: civec = self._ci.ci
        if civec is None: civec = self._ci.kernel(eris=eris)
        if atmlst is None:
            atmlst = self.atmlst
        else:
            self.atmlst = atmlst

        self.de = _kern(self._ci, civec, eris, atmlst, mf_grad, log)
        if self.verbose >= logger.NOTE:
            log.note('--------------- %s gradients ---------------',
                     self.__class__.__name__)
            rhf_grad._write(self, self.mol, self.de, atmlst)
            log.note('----------------------------------------------')
        return self.de

    as_scanner = as_scanner


if __name__ == '__main__':
    from pyscf import gto
    from pyscf import scf
    from pyscf import ao2mo
    from pyscf import grad

    mol = gto.M(
        atom = [
            ["O" , (0. , 0.     , 0.)],
            [1   , (0. ,-0.757  , 0.587)],
            [1   , (0. , 0.757  , 0.587)]],
        basis = '631g'
    )
    mf = scf.RHF(mol)
    ehf = mf.scf()

    myci = cisd.CISD(mf)
    myci.kernel()
    g1 = Gradients(myci).kernel()
# O     0.0000000000    -0.0000000000     0.0065498854
# H    -0.0000000000     0.0208760610    -0.0032749427
# H    -0.0000000000    -0.0208760610    -0.0032749427
    print(lib.finger(g1) - -0.032562200777204092)

    print('-----------------------------------')
    mol = gto.M(
        atom = [
            ["O" , (0. , 0.     , 0.)],
            [1   , (0. ,-0.757  , 0.587)],
            [1   , (0. , 0.757  , 0.587)]],
        basis = '631g'
    )
    mf = scf.RHF(mol)
    ehf = mf.scf()

    myci = cisd.CISD(mf)
    myci.frozen = [0,1,10,11,12]
    myci.max_memory = 1
    myci.kernel()
    g1 = Gradients(myci).kernel()
# O    -0.0000000000     0.0000000000     0.0106763547
# H     0.0000000000    -0.0763194988    -0.0053381773
# H     0.0000000000     0.0763194988    -0.0053381773
    print(lib.finger(g1) - 0.1022427304650084)

    mol = gto.M(
        atom = 'H 0 0 0; H 0 0 1.76',
        basis = '631g',
        unit='Bohr')
    mf = scf.RHF(mol).run(conv_tol=1e-14)
    myci = cisd.CISD(mf)
    myci.conv_tol = 1e-10
    myci.kernel()
    g1 = Gradients(myci).kernel()
#[[ 0.          0.         -0.07080036]
# [ 0.          0.          0.07080036]]
