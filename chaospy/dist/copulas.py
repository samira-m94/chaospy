r"""
Copulas are a type dependency structure imposed on independent variables to
achieve to more complex problems without adding too much complexity.

A cumulative distribution function of an independent multivariate random
variable can be made dependent through a copula as follows:

.. math::
    F_{Q_0,\dots,Q_{D-1}} (q_0,\dots,q_{D-1}) =
    C(F_{Q_0}(q_0), \dots, F_{Q_{D-1}}(q_{D-1}))

where :math:`C` is the copula function, and :math:`F_{Q_i}` are marginal
distribution functions.  One of the more popular classes of copulas is the
Archimedean copulas.
.. \cite{sklar_random_1996}.
They are defined as follows:

.. math::
    C(u_1,\dots,u_n) =
    \phi^{[-1]} (\phi(u_1)+\dots+\phi(u_n)),

where :math:`\phi` is a generator and :math:`\phi^{[-1]}` is its
pseudo-inverse. Support for Archimedean copulas in `chaospy` is possible
through reformulation of the Rosenblatt transformation.  In two dimension, this
reformulation is as follows:

.. math::

    F_{U_0}(u_0) = \frac{C(u_0,1)}{C(1,1)}

    F_{U_1\mid U_0}(u_1\mid u_0) =
    \frac{\tfrac{\partial}{\partial u_0}
    C(u_0,u_1)}{\tfrac{\partial}{\partial u_0} C(u_0,1)}

This definition can also be generalized in to multiple variables using the
formula provided by Nelsen 1999.
.. cite:: nelsen_introduction_1999

The definition of the Rosenblatt transform can require multiple
differentiations.  An analytical formulation is usually not feasible, so the
expressions are estimated using difference scheme similar to the one outlined
for probability density function defined in :ref:`distribution`. The accurate
might therefore be affected.

Since copulas are meant as a replacement for Rosenblatt
transformation, it is usually assumed that the distribution it is
used on is stochastically independent.
However in the definition of a copula does not actually require it, and sine
the Rosenblatt transformation allows for it, multiple copulas can be stacked
together in `chaospy`.

To construct a copula one needs a copula transformation and the
Copula wrapper::

    >>> dist = cp.Iid(cp.Uniform(), 2)
    >>> copula = cp.Gumbel(dist, theta=1.5)

The resulting copula is then ready for use::

    >>> cp.seed(1000)
    >>> print(copula.sample(5))
    [[ 0.65358959  0.11500694  0.95028286  0.4821914   0.87247454]
    [ 0.02388273  0.10004972  0.00127477  0.10572619  0.4510529 ]]
"""

import numpy as np
import scipy as sp
from .backend import Dist
from .cores import student_t, mvstudentt


class Copula(Dist):

    def __init__(self, dist, trans):
        """
        Args:
            dist (Dist) : Distribution to wrap the copula around.
            trans (Dist) : The copula wrapper `[0,1]^D \into [0,1]^D`.
        """
        Dist.__init__(self, dist=dist, trans=trans,
                _advance=True, _length=len(trans))

    def _cdf(self, x, G):
        dist, trans = G.D["dist"], G.D["trans"]
        q = G(G(x, dist), trans)
        return q

    def _bnd(self, x, G):
        return G(x, G.D["dist"])

    def _ppf(self, q, G):
        dist, trans = G.D["dist"], G.D["trans"]
        return G(G(q, trans), dist)

    def _pdf(self, x, G):
        dist, trans = G.D["dist"], G.D["trans"]
        return G(G.fwd_as_pdf(x, dist), trans)*G(x, dist)


class Archimedia(Dist):
    """
    Archimedean copula superclass.

    Subset this to generate an archimedean.
    """

    def _ppf(self, x, th, eps):

        for i in xrange(1, len(x)):

            q = x[:i+1].copy()
            lo, up = 0,1
            dq = np.zeros(i+1)
            dq[i] = eps
            flo, fup = -q[i],1-q[i]

            for iteration in range(1, 10):
                fq = self._diff(q[:i+1], th, eps)
                dfq = self._diff((q[:i+1].T+dq).T, th, eps)
                dfq = (dfq-fq)/eps
                dfq = np.where(dfq==0, np.inf, dfq)

                fq = fq-x[i]
                if not np.any(np.abs(fq)>eps):
                    break

                # reduce boundaries
                flo = np.where(fq<=0, fq, flo)
                lo = np.where(fq<=0, q[i], lo)

                fup = np.where(fq>=0, fq, fup)
                up = np.where(fq>=0, q[i], up)

                # Newton increment
                qdq = q[i]-fq/dfq

                # if new val on interior use Newton
                # else binary search
                q[i] = np.where((qdq<up)*(qdq>lo),
                        qdq, .5*(up+lo))

            x[i] = q[i]
        return x


    def _cdf(self, x, th, eps):
        out = np.zeros(x.shape)
        out[0] = x[0]
        for i in xrange(1,len(x)):
            out[i][x[i]==1] = 1
            out[i] = self._diff(x[:i+1], th, eps)

        return out

    def _pdf(self, x, th, eps):
        out = np.ones(x.shape)
        sign = 1-2*(x>.5)
        for i in xrange(1,len(x)):
            x[i] += eps*sign[i]
            out[i] = self._diff(x[:i+1], th, eps)
            x[i] -= eps*sign[i]
            out[i] -= self._diff(x[:i+1], th, eps)
            out[i] /= eps

        out = abs(out)
        return out

    def _diff(self, x, th, eps):
        """
        Differentiation function.

        Numerical approximation of a Rosenblatt transformation created from
        copula formulation.
        """
        foo = lambda y: self.igen(np.sum(self.gen(y, th), 0), th)

        out1 = out2 = 0.
        sign = 1 - 2*(x>.5).T
        for I in np.ndindex(*((2,)*(len(x)-1)+(1,))):

            eps_ = np.array(I)*eps
            x_ = (x.T + sign*eps_).T
            out1 += (-1)**sum(I)*foo(x_)

            x_[-1] = 1
            out2 += (-1)**sum(I)*foo(x_)

        out = out1/out2
        return out


    def _bnd(self, **prm):
        return 0,1


class gumbel(Archimedia):
    "Gumbel copula backend"

    def __init__(self, N, theta=1., eps=1e-6):
        theta = float(theta)
        Dist.__init__(self, th=theta, eps=eps, _length=N)
    def gen(self, x, th):
        return (-np.log(x))**th
    def igen(self, x, th):
        return np.e**(-x**th)


def Gumbel(dist, theta=2., eps=1e-6):
    r"""
    Gumbel Copula

    .. math::
        \phi(x;th) = \frac{x^{-th}-1}{th}
        \phi^{-1}(q;th) = (q*th + 1)^{-1/th}

    where `th` (or theta) is defined on the interval `[1,inf)`.

Args:
    dist (Dist) : The Distribution to wrap
    theta (float) : Copula parameter

Returns:
    (Dist) : The resulting copula distribution.

Examples:
    >>> dist = cp.J(cp.Uniform(), cp.Normal())
    >>> copula = cp.Gumbel(dist, theta=2)
    >>> print(copula.sample(3, "S"))
    [[ 0.5         0.75        0.25      ]
    [ 0.07686128 -1.50814454  1.65112325]]
"""
    return Copula(dist, gumbel(len(dist), theta, eps))


class clayton(Archimedia):
    "clayton copula backend"

    def __init__(self, N, theta=1., eps=1e-6):
        Dist.__init__(self, th=float(theta), _length=N, eps=eps)
    def gen(self, x, th):
        return (x**-th-1)/th
    def igen(self, x, th):
        return (1.+th*x)**(-1./th)

def Clayton(dist, theta=2., eps=1e-6):
    return Copula(dist, clayton(len(dist), theta, eps))


class ali_mikhail_haq(Archimedia):
    "Ali Mikhail Haq copula backend"

    def __init__(self, N, theta=.5, eps=1e-6):
        theta = float(theta)
        assert -1<=theta<1
        Dist.__init__(self, th=theta, _length=N, eps=eps)
    def gen(self, x, th):
        return np.log((1-th*(1-x))/x)
    def igen(self, x, th):
        return (1-th)/(np.e**x-th)


def Ali_mikhail_haq(dist, theta=2., eps=1e-6):
    "Ali Mikhail Haq copula"
    trans = ali_mikhail_haq(len(dist), theta, eps)
    return Copula(dist, trans)

class frank(Archimedia):
    "Frank copula backend"

    def __init__(self, N, theta, eps=1e-6):
        "theta!=0"
        theta = float(theta)
        assert theta!=0
        Dist.__init__(self, th=theta, _length=N, eps=eps)

    def gen(self, x, th):
        return -np.log((np.e**(-th*x)-1)/(np.e**-th-1))
    def igen(self, q, th):
        return -np.log(1+np.e**-q*(np.e**-th-1))/th

def Frank(dist, theta=1., eps=1e-4):
    "Frank copula"
    return Copula(dist, frank(len(dist), theta, eps))

class joe(Archimedia):
    "Joe copula backend"

    def __init__(self, N, theta, eps=1e-6):
        "theta in [1,inf)"
        theta = float(theta)
        assert theta>=1
        Dist.__init__(self, th=theta, _length=N, eps=eps)

    def gen(self, x, th):
        return -np.log(1-(1-x)**th)

    def igen(self, q, th):
        return 1-(1-np.e**-q)**(1/th)

def Joe(dist, theta=2., eps=1e-6):
    "Joe copula"
    return Copula(dist, joe(len(dist), theta, eps))

class nataf(Dist):
    "Nataf (normal) copula backend"

    def __init__(self, R, ordering=None):
        "R symmetric & positive definite matrix"

        if ordering is None:
            ordering = range(len(R))
        ordering = np.array(ordering)

        P = np.eye(len(R))[ordering]

        R = np.dot(P, np.dot(R, P.T))
        R = np.linalg.cholesky(R)
        R = np.dot(P.T, np.dot(R, P))
        Ci = np.linalg.inv(R)
        Dist.__init__(self, C=R, Ci=Ci, _length=len(R))

    def _cdf(self, x, C, Ci):
        out = sp.special.ndtr(np.dot(Ci, sp.special.ndtri(x)))
        return out

    def _ppf(self, q, C, Ci):
        out = sp.special.ndtr(np.dot(C, sp.special.ndtri(q)))
        return out

    def _bnd(self, C, Ci):
        return 0.,1.

def Nataf(dist, R, ordering=None):
    "Nataf (normal) copula"
    return Copula(dist, nataf(R, ordering))


class t_copula(Dist):

    def __init__(self, a, R):
        self.MV = mvstudentt(a, np.zeros(len(R)), R)
        self.UV = student_t(a)
        Dist.__init__(self, _length=len(R))

    def _cdf(self, x):
        out = self.MV.fwd(self.UV.inv(x))
        return out

    def _ppf(self, q):
        out = self.MV.inv(q)
        out = self.UV.fwd(out)
        return out

    def _bnd(self):
        return 0.,1.

def T_copula(dist, a, R):
    return Copula(dist, t_copula(a, R))



if __name__=="__main__":
    import chaospy as cp
    import numpy as np
    import doctest
    doctest.testmod()
