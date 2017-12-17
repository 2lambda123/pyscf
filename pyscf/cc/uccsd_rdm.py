#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#         Jun Yang <junyang4711@gmail.com>
#

import time
import numpy
from pyscf import lib
from pyscf.lib import logger
from pyscf import ao2mo

#einsum = numpy.einsum
einsum = lib.einsum

def gamma1_intermediates(cc, t1, t2, l1, l2):
    t1a, t1b = t1
    t2aa, t2ab, t2bb = t2
    l1a, l1b = l1
    l2aa, l2ab, l2bb = l2
    nocca, nvira = t1a.shape
    noccb, nvirb = t1b.shape

    dooa  = -einsum('ie,je->ij', t1a, l1a)
    dooa -=  einsum('imef,jmef->ij', t2ab, l2ab)
    dooa -=  einsum('imef,jmef->ij', t2aa, l2aa) * .5
    doob  = -einsum('ie,je->ij', t1b, l1b)
    doob -=  einsum('mief,mjef->ij', t2ab, l2ab)
    doob -=  einsum('imef,jmef->ij', t2bb, l2bb) * .5

    dvva  = einsum('ma,mb->ab', l1a, t1a)
    dvva += einsum('mnae,mnbe->ab', l2ab, t2ab)
    dvva += einsum('mnae,mnbe->ab', l2aa, t2aa) * .5
    dvvb  = einsum('ma,mb->ab', l1b, t1b)
    dvvb += einsum('mnea,mneb->ab', l2ab, t2ab)
    dvvb += einsum('mnae,mnbe->ab', l2bb, t2bb) * .5

    xt1a  = einsum('mnef,inef->mi', l2aa, t2aa) * .5
    xt1a += einsum('mnef,inef->mi', l2ab, t2ab)
    xt2a  = einsum('mnaf,mnef->ae', t2aa, l2aa) * .5
    xt2a += einsum('mnaf,mnef->ae', t2ab, l2ab)
    xt2a += einsum('ma,me->ae', t1a, l1a)

    dova  = einsum('imae,me->ia', t2aa, l1a)
    dova += einsum('imae,me->ia', t2ab, l1b)
    dova -= einsum('mi,ma->ia', xt1a, t1a)
    dova -= einsum('ie,ae->ia', t1a, xt2a)
    dova += t1a

    xt1b  = einsum('mnef,inef->mi', l2bb, t2bb) * .5
    xt1b += einsum('nmef,nief->mi', l2ab, t2ab)
    xt2b  = einsum('mnaf,mnef->ae', t2bb, l2bb) * .5
    xt2b += einsum('mnfa,mnfe->ae', t2ab, l2ab)
    xt2b += einsum('ma,me->ae', t1b, l1b)

    dovb  = einsum('imae,me->ia', t2bb, l1b)
    dovb += einsum('miea,me->ia', t2ab, l1a)
    dovb -= einsum('mi,ma->ia', xt1b, t1b)
    dovb -= einsum('ie,ae->ia', t1b, xt2b)
    dovb += t1b

    dvoa = l1a.T.copy()
    dvob = l1b.T.copy()

    return ((dooa, doob), (dova, dovb), (dvoa, dvob), (dvva, dvvb))

# gamma2 intermediates in Chemist's notation
def gamma2_intermediates(cc, t1, t2, l1, l2):
    t1a, t1b = t1
    t2aa, t2ab, t2bb = t2
    l1a, l1b = l1
    l2aa, l2ab, l2bb = l2

    tauaa = t2aa + numpy.einsum('ia,jb->ijab', 2*t1a, t1a)
    tauab = t2ab + numpy.einsum('ia,jb->ijab',   t1a, t1b)
    taubb = t2bb + numpy.einsum('ia,jb->ijab', 2*t1b, t1b)
    miajb = einsum('ikac,kjcb->iajb', l2aa, t2aa)
    miajb+= einsum('ikac,jkbc->iajb', l2ab, t2ab)
    miaJB = einsum('ikac,kjcb->iajb', l2aa, t2ab)
    miaJB+= einsum('ikac,kjcb->iajb', l2ab, t2bb)
    mIAjb = einsum('kica,jkbc->iajb', l2bb, t2ab)
    mIAjb+= einsum('kica,kjcb->iajb', l2ab, t2aa)
    mIAJB = einsum('ikac,kjcb->iajb', l2bb, t2bb)
    mIAJB+= einsum('kica,kjcb->iajb', l2ab, t2ab)
    miAjB = einsum('ikca,jkcb->iajb', l2ab, t2ab)
    mIaJb = einsum('kiac,kjbc->iajb', l2ab, t2ab)

    goovv = (l2aa.conj() + tauaa) * .25
    goOvV = (l2ab.conj() + tauab) * .5
    gOOVV = (l2bb.conj() + taubb) * .25

    tmpa  = einsum('kc,kica->ia', l1a, t2aa)
    tmpa += einsum('kc,ikac->ia', l1b, t2ab)
    tmpb  = einsum('kc,kica->ia', l1b, t2bb)
    tmpb += einsum('kc,kica->ia', l1a, t2ab)
    goovv += einsum('ia,jb->ijab', tmpa, t1a)
    goOvV += einsum('ia,jb->ijab', tmpa, t1b) * .5
    goOvV += einsum('ia,jb->jiba', tmpb, t1a) * .5
    gOOVV += einsum('ia,jb->ijab', tmpb, t1b)

    tmpa = einsum('kc,kb->cb', l1a, t1a)
    tmpb = einsum('kc,kb->cb', l1b, t1b)
    goovv += einsum('cb,ijca->ijab', tmpa, t2aa) * .5
    goOvV -= einsum('cb,ijac->ijab', tmpb, t2ab) * .5
    goOvV -= einsum('cb,jica->jiba', tmpa, t2ab) * .5
    gOOVV += einsum('cb,ijca->ijab', tmpb, t2bb) * .5
    tmpa = einsum('kc,jc->kj', l1a, t1a)
    tmpb = einsum('kc,jc->kj', l1b, t1b)
    goovv += einsum('kiab,kj->ijab', tauaa, tmpa) * .5
    goOvV -= einsum('ikab,kj->ijab', tauab , tmpb) * .5
    goOvV -= einsum('kiba,kj->jiba', tauab , tmpa) * .5
    gOOVV += einsum('kiab,kj->ijab', taubb, tmpb) * .5

    tmpa  = numpy.einsum('ldjd->lj', miajb)
    tmpa += numpy.einsum('ldjd->lj', miAjB)
    tmpb  = numpy.einsum('ldjd->lj', mIAJB)
    tmpb += numpy.einsum('ldjd->lj', mIaJb)
    goovv -= einsum('lj,liba->ijab', tmpa, tauaa) * .25
    goOvV -= einsum('lj,ilab->ijab', tmpb, tauab) * .25
    goOvV -= einsum('lj,liba->jiba', tmpa, tauab) * .25
    gOOVV -= einsum('lj,liba->ijab', tmpb, taubb) * .25
    tmpa  = numpy.einsum('ldlb->db', miajb)
    tmpa += numpy.einsum('ldlb->db', mIaJb)
    tmpb  = numpy.einsum('ldlb->db', mIAJB)
    tmpb += numpy.einsum('ldlb->db', miAjB)
    goovv -= einsum('db,jida->ijab', tmpa, tauaa) * .25
    goOvV -= einsum('db,ijad->ijab', tmpb, tauab) * .25
    goOvV -= einsum('db,jida->jiba', tmpa, tauab) * .25
    gOOVV -= einsum('db,jida->ijab', tmpb, taubb) * .25

    goovv -= einsum('ldia,ljbd->ijab', miajb, tauaa) * .5
    goovv += einsum('LDia,jLbD->ijab', mIAjb, t2ab ) * .5
    gOOVV -= einsum('ldia,ljbd->ijab', mIAJB, taubb) * .5
    gOOVV += einsum('ldia,ljdb->ijab', miaJB, t2ab ) * .5
    goOvV -= einsum('LDia,LJBD->iJaB', mIAjb, taubb) * .25
    goOvV += einsum('ldia,lJdB->iJaB', miajb, t2ab ) * .25
    goOvV -= einsum('ldIA,ljbd->jIbA', miaJB, tauaa) * .25
    goOvV += einsum('LDIA,jLbD->jIbA', mIAJB, t2ab ) * .25
    goOvV += einsum('lDiA,lJbD->iJbA', miAjB, tauab) * .5
    goOvV += einsum('LdIa,jd,LB->jIaB', mIaJb, t1a, t1b) * .5

    tmpaa = einsum('klcd,ijcd->ijkl', l2aa, tauaa) * .25**2
    tmpbb = einsum('klcd,ijcd->ijkl', l2bb, taubb) * .25**2
    tmpabab = einsum('kLcD,iJcD->iJkL', l2ab, tauab) * .5
    goovv += einsum('ijkl,klab->ijab', tmpaa, tauaa)
    goOvV += einsum('ijkl,klab->ijab', tmpabab, tauab)
    gOOVV += einsum('ijkl,klab->ijab', tmpbb, taubb)
    goovv = goovv.conj()
    goOvV = goOvV.conj()
    gOOVV = gOOVV.conj()

    gvvvv = einsum('ijab,ijcd->abcd', tauaa, l2aa) * .125
    gvVvV = einsum('ijab,ijcd->abcd', tauab, l2ab) * .25
    gVVVV = einsum('ijab,ijcd->abcd', taubb, l2bb) * .125

    goooo = einsum('ijab,klab->ijkl', l2aa, tauaa) * .125
    goOoO = einsum('ijab,klab->ijkl', l2ab, tauab) * .25
    gOOOO = einsum('ijab,klab->ijkl', l2bb, taubb) * .125

    gooov = einsum('jkba,ib->jkia', tauaa, -0.25 * l1a)
    goOoV = einsum('jkba,ib->jkia', tauab, -0.5  * l1a)
    gOoOv = einsum('kjab,ib->jkia', tauab, -0.5  * l1b)
    gOOOV = einsum('jkba,ib->jkia', taubb, -0.25 * l1b)

    gooov += einsum('iljk,la->jkia', goooo, t1a)
    goOoV += einsum('iljk,la->jkia', goOoO, t1b) * 2
    gOoOv += einsum('likj,la->jkia', goOoO, t1a) * 2
    gOOOV += einsum('iljk,la->jkia', gOOOO, t1b)

    tmpa  = numpy.einsum('icjc->ij', miajb) * .25
    tmpa += numpy.einsum('icjc->ij', miAjB) * .25
    tmpb  = numpy.einsum('icjc->ij', mIAJB) * .25
    tmpb += numpy.einsum('icjc->ij', mIaJb) * .25
    gooov -= einsum('ij,ka->jkia', tmpa, t1a)
    goOoV -= einsum('ij,ka->jkia', tmpa, t1b)
    gOoOv -= einsum('ij,ka->jkia', tmpb, t1a)
    gOOOV -= einsum('ij,ka->jkia', tmpb, t1b)

    gooov += einsum('icja,kc->jkia', miajb, .5 * t1a)
    goOoV += einsum('icja,kc->jkia', miAjB, .5 * t1b)
    goOoV -= einsum('icJA,kc->kJiA', miaJB, .5 * t1a)
    gOoOv += einsum('icja,kc->jkia', mIaJb, .5 * t1a)
    gOoOv -= einsum('ICja,KC->KjIa', mIAjb, .5 * t1b)
    gOOOV += einsum('icja,kc->jkia', mIAJB, .5 * t1b)

    gooov = gooov.conj()
    goOoV = goOoV.conj()
    gOoOv = gOoOv.conj()
    gOOOV = gOOOV.conj()
    gooov += einsum('jkab,ib->jkia', l2aa, .25*t1a)
    goOoV -= einsum('jkba,ib->jkia', l2ab, .5 *t1a)
    gOoOv -= einsum('kjab,ib->jkia', l2ab, .5 *t1b)
    gOOOV += einsum('jkab,ib->jkia', l2bb, .25*t1b)

    govvv = einsum('ja,ijcb->iacb', .25 * l1a, tauaa)
    goVvV = einsum('ja,ijcb->iacb', .5  * l1b, tauab)
    gOvVv = einsum('ja,jibc->iacb', .5  * l1a, tauab)
    gOVVV = einsum('ja,ijcb->iacb', .25 * l1b, taubb)

    govvv += einsum('bcad,id->iabc', gvvvv, t1a)
    goVvV -= einsum('bcda,id->iabc', gvVvV, t1a) * 2
    gOvVv -= einsum('cbad,id->iabc', gvVvV, t1b) * 2
    gOVVV += einsum('bcad,id->iabc', gVVVV, t1b)

    tmpa  = numpy.einsum('kakb->ab', miajb) * .25
    tmpa += numpy.einsum('kakb->ab', mIaJb) * .25
    tmpb  = numpy.einsum('kakb->ab', mIAJB) * .25
    tmpb += numpy.einsum('kakb->ab', miAjB) * .25
    govvv += einsum('ab,ic->iacb', tmpa, t1a)
    goVvV += einsum('ab,ic->iacb', tmpb, t1a)
    gOvVv += einsum('ab,ic->iacb', tmpa, t1b)
    gOVVV += einsum('ab,ic->iacb', tmpb, t1b)

    govvv += einsum('kaib,kc->iabc', miajb, .5 * t1a)
    goVvV += einsum('KAib,KC->iAbC', mIAjb, .5 * t1b)
    goVvV -= einsum('kAiB,kc->iAcB', miAjB, .5 * t1a)
    gOvVv += einsum('kaIB,kc->IaBc', miaJB, .5 * t1a)
    gOvVv -= einsum('KaIb,KC->IaCb', mIaJb, .5 * t1b)
    gOVVV += einsum('kaib,kc->iabc', mIAJB, .5 * t1b)
    govvv = govvv.conj()
    goVvV = goVvV.conj()
    gOvVv = gOvVv.conj()
    gOVVV = gOVVV.conj()
    govvv += einsum('ijbc,ja->iabc', l2aa, .25*t1a)
    goVvV += einsum('iJbC,JA->iAbC', l2ab, .5 *t1b)
    gOvVv += einsum('jIcB,ja->IaBc', l2ab, .5 *t1a)
    gOVVV += einsum('ijbc,ja->iabc', l2bb, .25*t1b)

    govvo = einsum('ia,jb->ibaj', l1a, t1a)
    goVvO = einsum('ia,jb->ibaj', l1a, t1b)
    gOvVo = einsum('ia,jb->ibaj', l1b, t1a)
    gOVVO = einsum('ia,jb->ibaj', l1b, t1b)

    govvo += numpy.einsum('iajb->ibaj', miajb)
    goVvO += numpy.einsum('iajb->ibaj', miaJB)
    gOvVo += numpy.einsum('iajb->ibaj', mIAjb)
    gOVVO += numpy.einsum('iajb->ibaj', mIAJB)
    goVoV = numpy.einsum('iajb->ibja', miAjB)
    gOvOv = numpy.einsum('iajb->ibja', mIaJb)

    govvo -= einsum('ikac,jc,kb->ibaj', l2aa, t1a, t1a)
    goVvO -= einsum('iKaC,JC,KB->iBaJ', l2ab, t1b, t1b)
    gOvVo -= einsum('kIcA,jc,kb->IbAj', l2ab, t1a, t1a)
    gOVVO -= einsum('ikac,jc,kb->ibaj', l2bb, t1b, t1b)
    goVoV += einsum('iKcA,jc,KB->iBjA', l2ab, t1a, t1b)
    gOvOv += einsum('kIaC,JC,kb->IbJa', l2ab, t1b, t1a)

    dovov = goovv.transpose(0,2,1,3) - goovv.transpose(0,3,1,2)
    dvvvv = gvvvv.transpose(0,2,1,3) - gvvvv.transpose(0,3,1,2)
    doooo = goooo.transpose(0,2,1,3) - goooo.transpose(0,3,1,2)
    dovvv = govvv.transpose(0,2,1,3) - govvv.transpose(0,3,1,2)
    dooov = gooov.transpose(0,2,1,3) - gooov.transpose(1,2,0,3)
    dovvo = govvo.transpose(0,2,1,3)
    dovov =(dovov + dovov.transpose(2,3,0,1)) * .5
    dvvvv = dvvvv + dvvvv.transpose(1,0,3,2).conj()
    doooo = doooo + doooo.transpose(1,0,3,2).conj()
    dovvo =(dovvo + dovvo.transpose(3,2,1,0).conj()) * .5
    doovv =-dovvo.transpose(0,3,2,1)
    dvvov = None

    dOVOV = gOOVV.transpose(0,2,1,3) - gOOVV.transpose(0,3,1,2)
    dVVVV = gVVVV.transpose(0,2,1,3) - gVVVV.transpose(0,3,1,2)
    dOOOO = gOOOO.transpose(0,2,1,3) - gOOOO.transpose(0,3,1,2)
    dOVVV = gOVVV.transpose(0,2,1,3) - gOVVV.transpose(0,3,1,2)
    dOOOV = gOOOV.transpose(0,2,1,3) - gOOOV.transpose(1,2,0,3)
    dOVVO = gOVVO.transpose(0,2,1,3)
    dOVOV =(dOVOV + dOVOV.transpose(2,3,0,1)) * .5
    dVVVV = dVVVV + dVVVV.transpose(1,0,3,2).conj()
    dOOOO = dOOOO + dOOOO.transpose(1,0,3,2).conj()
    dOVVO =(dOVVO + dOVVO.transpose(3,2,1,0).conj()) * .5
    dOOVV =-dOVVO.transpose(0,3,2,1)
    dVVOV = None

    dovOV = goOvV.transpose(0,2,1,3)
    dvvVV = gvVvV.transpose(0,2,1,3) * 2
    dooOO = goOoO.transpose(0,2,1,3) * 2
    dovVV = goVvV.transpose(0,2,1,3)
    dooOV = goOoV.transpose(0,2,1,3)
    dovVO = goVvO.transpose(0,2,1,3)

    dOVvv = gOvVv.transpose(0,2,1,3)
    dOOov = gOoOv.transpose(0,2,1,3)
    dOVvo = gOvVo.transpose(0,2,1,3)
    dooVV = goVoV.transpose(0,2,1,3)
    dOOvv = gOvOv.transpose(0,2,1,3)

    dvvVV = dvvVV + dvvVV.transpose(1,0,3,2).conj()
    dooOO = dooOO + dooOO.transpose(1,0,3,2).conj()
    dovVO = (dovVO + dOVvo.transpose(3,2,1,0).conj()) * .5
    dooVV =-(dooVV + dooVV.transpose(1,0,3,2).conj()) * .5
    dvvOV = None

    dOVov = None
    dVVvv = None
    dOOoo = None
    dOVvo =  dovVO.transpose(3,2,1,0).conj()
    dOOvv =-(dOOvv + dOOvv.transpose(1,0,3,2).conj()) * .5
    dVVov = None

    return ((dovov, dovOV, dOVov, dOVOV),
            (dvvvv, dvvVV, dVVvv, dVVVV),
            (doooo, dooOO, dOOoo, dOOOO),
            (doovv, dooVV, dOOvv, dOOVV),
            (dovvo, dovVO, dOVvo, dOVVO),
            (dvvov, dvvOV, dVVov, dVVOV),
            (dovvv, dovVV, dOVvv, dOVVV),
            (dooov, dooOV, dOOov, dOOOV))

def _gamma2_outcore(mycc, t1, t2, l1, l2, h5fobj):
    d2 = gamma2_intermediates(mycc, t1, t2, l1, l2)
    dovov, dovOV, dOVov, dOVOV = d2[0]
    dvvvv, dvvVV, dVVvv, dVVVV = d2[1]
    doooo, dooOO, dOOoo, dOOOO = d2[2]
    doovv, dooVV, dOOvv, dOOVV = d2[3]
    dovvo, dovVO, dOVvo, dOVVO = d2[4]
    dvvov, dvvOV, dVVov, dVVOV = d2[5]
    dovvv, dovVV, dOVvv, dOVVV = d2[6]
    dooov, dooOV, dOOov, dOOOV = d2[7]
    nocca, nvira, noccb, nvirb = dovOV.shape

    dvvvv = dvvvv + dvvvv.transpose(1,0,2,3)
    dvvvv = ao2mo.restore(4, dvvvv, nvira) * .5
    dvvVV = dvvVV + dvvVV.transpose(1,0,2,3)
    dvvVV = lib.pack_tril(dvvVV[numpy.tril_indices(nvira)])
    dVVVV = dVVVV + dVVVV.transpose(1,0,2,3)
    dVVVV = ao2mo.restore(4, dVVVV, nvirb) * .5

    return ((dovov, dovOV, dOVov, dOVOV),
            (dvvvv, dvvVV, dVVvv, dVVVV),
            (doooo, dooOO, dOOoo, dOOOO),
            (doovv, dooVV, dOOvv, dOOVV),
            (dovvo, dovVO, dOVvo, dOVVO),
            (dvvov, dvvOV, dVVov, dVVOV),
            (dovvv, dovVV, dOVvv, dOVVV),
            (dooov, dooOV, dOOov, dOOOV))

def make_rdm1(mycc, t1, t2, l1, l2):
    d1 = gamma1_intermediates(mycc, t1, t2, l1, l2)
    return _make_rdm1(mycc, d1, with_frozen=True)

# spin-orbital rdm2 in Chemist's notation
def make_rdm2(mycc, t1, t2, l1, l2):
    d1 = gamma1_intermediates(mycc, t1, t2, l1, l2)
    d2 = gamma2_intermediates(mycc, t1, t2, l1, l2)
    return _make_rdm2(mycc, d1, d2, with_dm1=True, with_frozen=True)

def _make_rdm1(mycc, d1, with_frozen=True):
    doo, dOO = d1[0]
    dov, dOV = d1[1]
    dvo, dVO = d1[2]
    dvv, dVV = d1[3]
    nocca, nvira = dov.shape
    noccb, nvirb = dOV.shape
    nmoa = nocca + nvira
    nmob = noccb + nvirb

    dm1a = numpy.empty((nmoa,nmoa))
    dm1a[:nocca,:nocca] = doo + doo.conj().T
    dm1a[:nocca,nocca:] = dov + dvo.conj().T
    dm1a[nocca:,:nocca] = dm1a[:nocca,nocca:].conj().T
    dm1a[nocca:,nocca:] = dvv + dvv.conj().T
    dm1a *= .5
    dm1a[numpy.diag_indices(nocca)] += 1

    dm1b = numpy.empty((nmoa,nmoa))
    dm1b[:noccb,:noccb] = dOO + dOO.conj().T
    dm1b[:noccb,noccb:] = dOV + dVO.conj().T
    dm1b[noccb:,:noccb] = dm1b[:noccb,noccb:].conj().T
    dm1b[noccb:,noccb:] = dVV + dVV.conj().T
    dm1b *= .5
    dm1b[numpy.diag_indices(noccb)] += 1

    if with_frozen and not (mycc.frozen is 0 or mycc.frozen is None):
        nmoa = mycc.mo_occ[0].size
        nmob = mycc.mo_occ[1].size
        nocca = numpy.count_nonzero(mycc.mo_occ[0] > 0)
        noccb = numpy.count_nonzero(mycc.mo_occ[1] > 0)
        rdm1a = numpy.zeros((nmoa,nmoa))
        rdm1b = numpy.zeros((nmob,nmob))
        rdm1a[numpy.diag_indices(nocca)] = 1
        rdm1b[numpy.diag_indices(noccb)] = 1
        moidx = mycc.get_frozen_mask()
        moidxa = numpy.where(moidx[0])[0]
        moidxb = numpy.where(moidx[1])[0]
        rdm1a[moidxa[:,None],moidxa] = dm1a
        rdm1b[moidxb[:,None],moidxb] = dm1b
        dm1a = rdm1a
        dm1b = rdm1b
    return dm1a, dm1b

def _make_rdm2(mycc, d1, d2, with_dm1=True, with_frozen=True):
    dovov, dovOV, dOVov, dOVOV = d2[0]
    dvvvv, dvvVV, dVVvv, dVVVV = d2[1]
    doooo, dooOO, dOOoo, dOOOO = d2[2]
    doovv, dooVV, dOOvv, dOOVV = d2[3]
    dovvo, dovVO, dOVvo, dOVVO = d2[4]
    dvvov, dvvOV, dVVov, dVVOV = d2[5]
    dovvv, dovVV, dOVvv, dOVVV = d2[6]
    dooov, dooOV, dOOov, dOOOV = d2[7]
    nocca, nvira, noccb, nvirb = dovOV.shape
    nmoa = nocca + nvira
    nmob = noccb + nvirb

    dm2aa = numpy.empty((nmoa,nmoa,nmoa,nmoa))
    dm2ab = numpy.empty((nmoa,nmoa,nmob,nmob))
    dm2bb = numpy.empty((nmob,nmob,nmob,nmob))

# dm2aa
    dovov = numpy.asarray(dovov)
    dm2aa[:nocca,nocca:,:nocca,nocca:] = dovov
    dm2aa[nocca:,:nocca,nocca:,:nocca] = dm2aa[:nocca,nocca:,:nocca,nocca:].transpose(1,0,3,2).conj()
    dovov = None

    dovvo = numpy.asarray(dovvo)
    dm2aa[:nocca,:nocca,nocca:,nocca:] =-dovvo.transpose(0,3,2,1)
    dm2aa[nocca:,nocca:,:nocca,:nocca] = dm2aa[:nocca,:nocca,nocca:,nocca:].transpose(2,3,0,1)
    dm2aa[:nocca,nocca:,nocca:,:nocca] = dovvo
    dm2aa[nocca:,:nocca,:nocca,nocca:] = dm2aa[:nocca,nocca:,nocca:,:nocca].transpose(1,0,3,2).conj()
    dovvo = None

    dm2aa[nocca:,nocca:,nocca:,nocca:] = dvvvv
    dm2aa[:nocca,:nocca,:nocca,:nocca] = doooo

    dovvv = numpy.asarray(dovvv)
    dm2aa[:nocca,nocca:,nocca:,nocca:] = dovvv
    dm2aa[nocca:,nocca:,:nocca,nocca:] = dovvv.transpose(2,3,0,1)
    dm2aa[nocca:,nocca:,nocca:,:nocca] = dovvv.transpose(3,2,1,0).conj()
    dm2aa[nocca:,:nocca,nocca:,nocca:] = dovvv.transpose(1,0,3,2).conj()
    dovvv = None

    dooov = numpy.asarray(dooov)
    dm2aa[:nocca,:nocca,:nocca,nocca:] = dooov
    dm2aa[:nocca,nocca:,:nocca,:nocca] = dooov.transpose(2,3,0,1)
    dm2aa[:nocca,:nocca,nocca:,:nocca] = dooov.transpose(1,0,3,2).conj()
    dm2aa[nocca:,:nocca,:nocca,:nocca] = dooov.transpose(3,2,1,0).conj()
    dooov = None

# dm2bb
    dOVOV = numpy.asarray(dOVOV)
    dm2bb[:noccb,noccb:,:noccb,noccb:] = dOVOV
    dm2bb[noccb:,:noccb,noccb:,:noccb] = dm2bb[:noccb,noccb:,:noccb,noccb:].transpose(1,0,3,2).conj()
    dOVOV = None

    dOVVO = numpy.asarray(dOVVO)
    dm2bb[:noccb,:noccb,noccb:,noccb:] =-dOVVO.transpose(0,3,2,1)
    dm2bb[noccb:,noccb:,:noccb,:noccb] = dm2bb[:noccb,:noccb,noccb:,noccb:].transpose(2,3,0,1)
    dm2bb[:noccb,noccb:,noccb:,:noccb] = dOVVO
    dm2bb[noccb:,:noccb,:noccb,noccb:] = dm2bb[:noccb,noccb:,noccb:,:noccb].transpose(1,0,3,2).conj()
    dOVVO = None

    dm2bb[noccb:,noccb:,noccb:,noccb:] = dVVVV
    dm2bb[:noccb,:noccb,:noccb,:noccb] = dOOOO

    dOVVV = numpy.asarray(dOVVV)
    dm2bb[:noccb,noccb:,noccb:,noccb:] = dOVVV
    dm2bb[noccb:,noccb:,:noccb,noccb:] = dOVVV.transpose(2,3,0,1)
    dm2bb[noccb:,noccb:,noccb:,:noccb] = dOVVV.transpose(3,2,1,0).conj()
    dm2bb[noccb:,:noccb,noccb:,noccb:] = dOVVV.transpose(1,0,3,2).conj()
    dOVVV = None

    dOOOV = numpy.asarray(dOOOV)
    dm2bb[:noccb,:noccb,:noccb,noccb:] = dOOOV
    dm2bb[:noccb,noccb:,:noccb,:noccb] = dOOOV.transpose(2,3,0,1)
    dm2bb[:noccb,:noccb,noccb:,:noccb] = dOOOV.transpose(1,0,3,2).conj()
    dm2bb[noccb:,:noccb,:noccb,:noccb] = dOOOV.transpose(3,2,1,0).conj()
    dOOOV = None

# dm2ab
    dovOV = numpy.asarray(dovOV)
    dm2ab[:nocca,nocca:,:noccb,noccb:] = dovOV
    dm2ab[nocca:,:nocca,noccb:,:noccb] = dm2ab[:nocca,nocca:,:noccb,noccb:].transpose(1,0,3,2).conj()
    dovOV = None

    dovVO = numpy.asarray(dovVO)
    dm2ab[:nocca,:nocca,noccb:,noccb:] = dooVV
    dm2ab[nocca:,nocca:,:noccb,:noccb] = dOOvv.transpose(2,3,0,1)
    dm2ab[:nocca,nocca:,noccb:,:noccb] = dovVO
    dm2ab[nocca:,:nocca,:noccb,noccb:] = dovVO.transpose(1,0,3,2).conj()
    dovVO = None

    dm2ab[nocca:,nocca:,noccb:,noccb:] = dvvVV
    dm2ab[:nocca,:nocca,:noccb,:noccb] = dooOO

    dovVV = numpy.asarray(dovVV)
    dm2ab[:nocca,nocca:,noccb:,noccb:] = dovVV
    dm2ab[nocca:,nocca:,:noccb,noccb:] = dOVvv.transpose(2,3,0,1)
    dm2ab[nocca:,nocca:,noccb:,:noccb] = dOVvv.transpose(3,2,1,0).conj()
    dm2ab[nocca:,:nocca,noccb:,noccb:] = dovVV.transpose(1,0,3,2).conj()
    dovVV = None

    dooOV = numpy.asarray(dooOV)
    dm2ab[:nocca,:nocca,:noccb,noccb:] = dooOV
    dm2ab[:nocca,nocca:,:noccb,:noccb] = dOOov.transpose(2,3,0,1)
    dm2ab[:nocca,:nocca,noccb:,:noccb] = dooOV.transpose(1,0,3,2).conj()
    dm2ab[nocca:,:nocca,:noccb,:noccb] = dOOov.transpose(3,2,1,0).conj()
    dooOV = None

    if with_frozen and not (mycc.frozen is 0 or mycc.frozen is None):
        nmoa0 = dm2aa.shape[0]
        nmob0 = dm2bb.shape[0]
        nmoa = mycc.mo_occ[0].size
        nmob = mycc.mo_occ[1].size
        nocca = numpy.count_nonzero(mycc.mo_occ[0] > 0)
        noccb = numpy.count_nonzero(mycc.mo_occ[1] > 0)

        rdm2aa = numpy.zeros((nmoa,nmoa,nmoa,nmoa))
        rdm2ab = numpy.zeros((nmoa,nmoa,nmob,nmob))
        rdm2bb = numpy.zeros((nmob,nmob,nmob,nmob))
        moidxa, moidxb = mycc.get_frozen_mask()
        moidxa = numpy.where(moidxa)[0]
        moidxb = numpy.where(moidxb)[0]
        idxa = (moidxa.reshape(-1,1) * nmoa + moidxa).ravel()
        idxb = (moidxb.reshape(-1,1) * nmob + moidxb).ravel()
        lib.takebak_2d(rdm2aa.reshape(nmoa**2,nmoa**2),
                       dm2aa.reshape(nmoa0**2,nmoa0**2), idxa, idxa)
        lib.takebak_2d(rdm2bb.reshape(nmob**2,nmob**2),
                       dm2bb.reshape(nmob0**2,nmob0**2), idxb, idxb)
        lib.takebak_2d(rdm2ab.reshape(nmoa**2,nmob**2),
                       dm2ab.reshape(nmoa0**2,nmob0**2), idxa, idxb)
        dm2aa, dm2ab, dm2bb = rdm2aa, rdm2ab, rdm2bb

    if with_dm1:
        dm1a, dm1b = _make_rdm1(mycc, d1, with_frozen=True)
        dm1a[numpy.diag_indices(nocca)] -= 1
        dm1b[numpy.diag_indices(noccb)] -= 1

        for i in range(nocca):
            dm2aa[i,i,:,:] += dm1a
            dm2aa[:,:,i,i] += dm1a
            dm2aa[:,i,i,:] -= dm1a
            dm2aa[i,:,:,i] -= dm1a
            dm2ab[i,i,:,:] += dm1b
        for i in range(noccb):
            dm2bb[i,i,:,:] += dm1b
            dm2bb[:,:,i,i] += dm1b
            dm2bb[:,i,i,:] -= dm1b
            dm2bb[i,:,:,i] -= dm1b
            dm2ab[:,:,i,i] += dm1a

        for i in range(nocca):
            for j in range(nocca):
                dm2aa[i,i,j,j] += 1
                dm2aa[i,j,j,i] -= 1
        for i in range(noccb):
            for j in range(noccb):
                dm2bb[i,i,j,j] += 1
                dm2bb[i,j,j,i] -= 1
        for i in range(nocca):
            for j in range(noccb):
                dm2ab[i,i,j,j] += 1

    return dm2aa, dm2ab, dm2bb


if __name__ == '__main__':
    from pyscf import gto
    from pyscf import scf
    from pyscf import ao2mo
    from pyscf.cc import uccsd
    from pyscf.cc import gccsd
    from pyscf.cc import addons

    nocc = 5
    nvir = 7
    mol = gto.M()
    mf = scf.UHF(mol)
    mf.mo_occ = numpy.zeros((2,nocc+nvir))
    mf.mo_occ[:,:nocc] = 1
    mycc = uccsd.UCCSD(mf)

    def antisym(t2):
        t2 = t2 - t2.transpose(0,1,3,2)
        t2 = t2 - t2.transpose(1,0,2,3)
        return t2
    orbspin = numpy.zeros((nocc+nvir)*2, dtype=int)
    orbspin[1::2] = 1
    numpy.random.seed(1)
    t1 = numpy.random.random((2,nocc,nvir))*.1 - .1
    t2ab = numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1
    t2aa = antisym(numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1)
    t2bb = antisym(numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1)
    t2 = (t2aa,t2ab,t2bb)
    l1 = numpy.random.random((2,nocc,nvir))*.1 - .1
    l2ab = numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1
    l2aa = antisym(numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1)
    l2bb = antisym(numpy.random.random((nocc,nocc,nvir,nvir))*.1 - .1)
    l2 = (l2aa,l2ab,l2bb)

    dm1a, dm1b = make_rdm1(mycc, t1, t2, l1, l2)
    dm2aa, dm2ab, dm2bb = make_rdm2(mycc, t1, t2, l1, l2)
    ia = orbspin == 0
    ib = orbspin == 1
    oa = orbspin[:nocc*2] == 0
    ob = orbspin[:nocc*2] == 1
    va = orbspin[nocc*2:] == 0
    vb = orbspin[nocc*2:] == 1

    t1 = addons.spatial2spin(t1, orbspin)
    t2 = addons.spatial2spin(t2, orbspin)
    l1 = addons.spatial2spin(l1, orbspin)
    l2 = addons.spatial2spin(l2, orbspin)
    mf1 = scf.GHF(mol)
    mf1.mo_occ = numpy.zeros((nocc+nvir)*2)
    mf.mo_occ[:,:nocc*2] = 1
    mycc1 = gccsd.GCCSD(mf1)
    dm1 = mycc1.make_rdm1(t1, t2, l1, l2)
    dm2 = mycc1.make_rdm2(t1, t2, l1, l2)
    print(abs(dm1[ia][:,ia]-dm1a).max())
    print(abs(dm1[ib][:,ib]-dm1b).max())
    print(abs(dm2[ia][:,ia][:,:,ia][:,:,:,ia]-dm2aa).max())
    print(abs(dm2[ia][:,ia][:,:,ib][:,:,:,ib]-dm2ab).max())
    print(abs(dm2[ib][:,ib][:,:,ib][:,:,:,ib]-dm2bb).max())

    mol = gto.Mole()
    mol.atom = [
        [8 , (0. , 0.     , 0.)],
        [1 , (0. , -0.757 , 0.587)],
        [1 , (0. , 0.757  , 0.587)]]
    mol.basis = '631g'
    mol.spin = 2
    mol.build()
    mf = scf.UHF(mol).run()

    mycc = uccsd.UCCSD(mf)
    mycc.frozen = 2
    ecc, t1, t2 = mycc.kernel()
    l1, l2 = mycc.solve_lambda()
    dm1a,dm1b = make_rdm1(mycc, t1, t2, l1, l2)
    dm2aa,dm2ab,dm2bb = make_rdm2(mycc, t1, t2, l1, l2)
    mo_a = mf.mo_coeff[0]
    mo_b = mf.mo_coeff[1]
    nmoa = mo_a.shape[1]
    nmob = mo_b.shape[1]
    eriaa = ao2mo.kernel(mf._eri, mo_a, compact=False).reshape([nmoa]*4)
    eribb = ao2mo.kernel(mf._eri, mo_b, compact=False).reshape([nmob]*4)
    eriab = ao2mo.kernel(mf._eri, (mo_a,mo_a,mo_b,mo_b), compact=False)
    eriab = eriab.reshape([nmoa,nmoa,nmob,nmob])
    hcore = mf.get_hcore()
    h1a = reduce(numpy.dot, (mo_a.T.conj(), hcore, mo_a))
    h1b = reduce(numpy.dot, (mo_b.T.conj(), hcore, mo_b))
    e1 = numpy.einsum('ij,ji', h1a, dm1a)
    e1+= numpy.einsum('ij,ji', h1b, dm1b)
    e1+= numpy.einsum('ijkl,jilk', eriaa, dm2aa) * .5
    e1+= numpy.einsum('ijkl,jilk', eriab, dm2ab)
    e1+= numpy.einsum('ijkl,jilk', eribb, dm2bb) * .5
    e1+= mol.energy_nuc()
    print(e1 - mycc.e_tot)

    from pyscf.fci import direct_uhf
    mol = gto.Mole()
    mol.verbose = 0
    mol.atom = [
        ['H', ( 1.,-1.    , 0.   )],
        ['H', ( 0.,-1.    ,-1.   )],
        ['H', ( 1.,-0.5   , 0.   )],
        ['H', ( 0.,-1.    , 1.   )],
    ]
    mol.charge = 2
    mol.spin = 2
    mol.basis = '6-31g'
    mol.build()
    mf = scf.UHF(mol).run(conv_tol=1e-14)
    ehf0 = mf.e_tot - mol.energy_nuc()
    mycc = uccsd.UCCSD(mf).run()
    mycc.solve_lambda()
    eri_aa = ao2mo.kernel(mf._eri, mf.mo_coeff[0])
    eri_bb = ao2mo.kernel(mf._eri, mf.mo_coeff[1])
    eri_ab = ao2mo.kernel(mf._eri, [mf.mo_coeff[0], mf.mo_coeff[0],
                                    mf.mo_coeff[1], mf.mo_coeff[1]])
    h1a = reduce(numpy.dot, (mf.mo_coeff[0].T, mf.get_hcore(), mf.mo_coeff[0]))
    h1b = reduce(numpy.dot, (mf.mo_coeff[1].T, mf.get_hcore(), mf.mo_coeff[1]))
    efci, fcivec = direct_uhf.kernel((h1a,h1b), (eri_aa,eri_ab,eri_bb),
                                     h1a.shape[0], mol.nelec)
    dm1ref, dm2ref = direct_uhf.make_rdm12s(fcivec, h1a.shape[0], mol.nelec)
    t1, t2 = mycc.t1, mycc.t2
    l1, l2 = mycc.l1, mycc.l2
    rdm1 = make_rdm1(mycc, t1, t2, l1, l2)
    rdm2 = make_rdm2(mycc, t1, t2, l1, l2)
    print('dm1a', abs(dm1ref[0] - rdm1[0]).max())
    print('dm1b', abs(dm1ref[1] - rdm1[1]).max())
    print('dm2aa', abs(dm2ref[0] - rdm2[0]).max())
    print('dm2ab', abs(dm2ref[1] - rdm2[1]).max())
    print('dm2bb', abs(dm2ref[2] - rdm2[2]).max())
