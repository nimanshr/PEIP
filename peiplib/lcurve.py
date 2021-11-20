"""
L-curve criteria.

Copyright (c) 2021 Nima Nooshiri (@nimanzik)
"""

import numpy as np
from numpy import linalg as nla

from peiplib.plot import nice_sci_notation
from peiplib.util import loglinspace


def tikh_svd(U, s, d, npoints, alpha_min=None, alpha_max=None):
    """
    L-curve parameters for Tikhonov standard-form regularization.

    If the system matrix ``G`` is m-by-n, then singular value
    decomposition (SVD) of ``G`` is:

        U, s, V = svd(G)

    Parameters
    ----------
    U : array-like
        Matrix of data space basis vectors from the SVD.
    s : array-like
        Vector of singular values from the SVD.
    d : array-like
        The data vector.
    npoints : int
        Number of logarithmically spaced regularization parameters.
    alpha_min : float (optional)
        If specified, minimum of the regularization parameters range.
    alpha_max : float (optional)
        If specified, maximum of the reqularization parameters range.

    Returns
    -------
    rhos : array-like
        Vector of residual norm `||Gm-d||_2`.
    etas : array-like
        Vector of solution norm `||m||_2`.
    alphas : array-like
        Vector of corresponding regularization parameters.

    References
    ----------
    .. [1] Hansen, P. C. (2001), The L-curve and its use in the
       numerical treatment of inverse problems, in book: Computational
       Inverse Problems in Electrocardiology, pp 119-142.
    """

    smin_ratio = 16 * np.finfo(np.float64).eps
    start = alpha_max or s[0]
    stop = alpha_min or max(s[-1], s[0] * smin_ratio)
    start, stop = sorted((start, stop), reverse=True)   # alpha[0] will be s[0]
    alphas = loglinspace(start, stop, npoints)

    m, n = U.shape
    p = s.size

    if len(d.shape) == 2:
        d = d.reshape(d.size,)

    # Projection, and residual error introduced by the projection
    d_proj = np.dot(U.T, d)
    dr = nla.norm(d)**2 - nla.norm(d_proj)**2

    d_proj = d_proj[:p]

    # Scale series terms by singular values
    d_proj_scale = d_proj / s

    # Initialize storage space
    etas = np.zeros(npoints, dtype=np.float64)
    rhos = np.zeros_like(etas)

    s2 = s**2
    for i in range(npoints):
        f = s2 / (s2 + alphas[i]**2)
        etas[i] = nla.norm(f * d_proj_scale)
        rhos[i] = nla.norm((1 - f) * d_proj)

    # If we couldn't match the data exactly add the projection-induced misfit
    if (m > n) and (dr > 0):
        rhos = np.sqrt(rhos**2 + dr)

    return (rhos, etas, alphas)


def tikh_gsvd(
        U, X, LAM, MU, d, G, L, npoints, alpha_min=None, alpha_max=None):
    """
    L-curve parameters for Tikhonov general-form regularization.

    If the system matrix ``G`` is m-by-n and the corresponding
    roughening matrix ``L`` is p-by-n, then the generalized singular
    value decomposition (GSVD) of ``A=[G; L]`` is:

        U, V, X, LAM, MU = gsvd(G, L)

    Parameters
    ----------
    U : array-like
        m-by-m matrix of data space basis vectors from the GSVD.
    X : array-like
        n-by-n nonsingular matrix computed by the GSVD.
    LAM : array-like
        m-by-n matrix, computed by the GSVD, with diagonal entries that
        may be shifted from the main diagonal.
    MU : array-like
        p-by-n diagonal matrix computed by the GSVD.
    d : array-like
        The data vector.
    G : array-like
        The system matrix (forward operator or design matrix).
    L : array-like
        The roughening matrix.
    npoints : int
        Number of logarithmically spaced regularization parameters.
    alpha_min : float (optional)
        Minimum of the regularization parameters range.
    alpha_max : float (optional)
        Maximum of the reqularization parameters range.

    Returns
    -------
    rhos : array-like
        Vector of residual norm `||Gm-d||_2`.
    etas : array-like
        Vector of solution seminorm `||Lm||_2`.
    alphas : array-like
        Vector of corresponding regularization parameters.

    References
    ----------
    .. [1] Aster, R., Borchers, B. & Thurber, C. (2011), `Parameter
       Estimation and Inverse Problems`, Elsevier, pp 103-107.
    """

    m, n = G.shape
    p = nla.matrix_rank(L)

    if len(d.shape) == 2:
        d = d.reshape(d.size,)

    lams = np.sqrt(np.diag(LAM.T @ LAM))
    mus = np.sqrt(np.diag(MU.T @ MU))
    gammas = lams / mus

    if alpha_min and alpha_max:
        start = alpha_max
        stop = alpha_min
    else:
        gmin_ratio = 16 * np.finfo(np.float64).eps
        if m <= n:
            # The under-determined or square case.
            i1, i2 = sorted((n-m, p-1))
            start = alpha_max or gammas[i2]
            stop = alpha_min or max(gammas[i1], gammas[i2]*gmin_ratio)
        else:
            # The over-determined case.
            start = alpha_max or gammas[p-1]
            stop = alpha_min or max(gammas[0], gammas[p-1]*gmin_ratio)

    # alpha[0] will be s[0]
    start, stop = sorted((start, stop), reverse=True)
    alphas = loglinspace(start, stop, npoints)

    if m > n:
        k = 0
    else:
        k = n - m

    # Initialization.
    etas = np.zeros(npoints, dtype=np.float64)
    rhos = np.zeros_like(etas)

    # Solve for each solution.
    Y = np.transpose(nla.inv(X))
    for ireg in range(npoints):

        # Series filter coeficients for this regularization parameter.
        f = np.zeros(n, dtype=np.float64)
        for igam in range(k, n):
            gam = gammas[igam]

            if np.isinf(gam) or np.isnan(gam):
                f[igam] = 1
            elif (lams[igam] == 0) and (mus[igam] == 0):
                f[igam] = 0
            else:
                f[igam] = gam**2 / (gam**2 + alphas[ireg]**2)

        # Build the solution (see Aster er al. (2011), eq. (4.49) & (4.56)).
        d_proj_scale = np.dot(U[:, :n-k].T, d) / lams[k:n]
        F = np.diag(f)
        mod = np.dot(Y[:, k:], np.dot(F, d_proj_scale))
        rhos[ireg] = nla.norm(np.dot(G, mod) - d)
        etas[ireg] = nla.norm(np.dot(L, mod))

    return (rhos, etas, alphas)


def corner_maxcurv(rhos, etas, alphas):
    """
    Determination of Tikhonov regularization parameter using L-curve criterion.

    Triangular/circumscribed circle simple approximation to curvature.

    Parameters
    ----------
    rhos : array-like
        Vector of residual norm `||Gm-d||_2`.
    etas : array-like
        Vector of solution norm `||m||_2` or seminorm `||Lm||_2`.
    alphas : array-like
        Vector of corresponding regularization parameters.

    Returns
    -------
    rho_corner : float
        The residual norm corresponding to ``alpha_corner``.
    eta_corner : float
        The solution norm/seminorm corresponding to ``alpha_corner``.
    alpha_corner : float
        The value of regularization parameter corresponding to the
        corner of the L-curve (i.e. the value of ``alphas`` with
        maximum curvature).

    References
    ----------
    .. [1] https://de.mathworks.com/matlabcentral/answers/284245-matlab-code-for-computing-curvature-equation#answer_222173   # noqa
    .. [2] https://en.wikipedia.org/wiki/Circumscribed_circle#Triangle_centers_on_the_circumcircle_of_triangle_ABC   # noqa
    """

    xs = np.log(rhos)
    ys = np.log(etas)

    x1 = xs[:-2]
    x2 = xs[1:-1]
    x3 = xs[2:]
    y1 = ys[:-2]
    y2 = ys[1:-1]
    y3 = ys[2:]

    # The side length for each triangle
    a = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
    b = np.sqrt((x2 - x3)**2 + (y2 - y3)**2)
    c = np.sqrt((x3 - x1)**2 + (y3 - y1)**2)

    # Semi-perimiter
    s = (a + b + c) / 2.0

    # Area of triangles (Herron's formula)
    areas = np.sqrt(s * (s - a) * (s - b) * (s - c))

    # The radius of each circle
    radii = (a * b * c) / (4.0 * areas)

    # The curvature for each estimate for each value which is the
    # reciprocal of its circumscribed radius. Since there aren't
    # circles for the end points they have no curvature.
    kappa = np.hstack([0.0, 1.0 / radii, 0.0])

    i_corner = np.nanargmax(np.abs(kappa[1:-1]))
    alpha_corner = alphas[i_corner]
    rho_corner = rhos[i_corner]
    eta_corner = etas[i_corner]

    return (rho_corner, eta_corner, alpha_corner)


def corner_mdf_svd(U, s, d, alpha_init=None, tol=1.0e-16, maxiter=1200):
    """
    Determination of Tikhonov regularization parameter using L-curve criterion.

    Minimum distance function (MDF) optimization.

    Parameters
    ----------
    U : array-like
        Matrix of data space basis vectors from the SVD.
    s : array-like
        Vector of singular values from the SVD.
    d : array-like
        The data vector.
    alpha_init : float (optional)
        An appropriate initial regularization parameter.
    tol : float
        Absolute error in ``alpha_corner`` between iterations that is
        acceptable for convergence.
    maxiter : int
        Maximum number of iterations to perform.

    Returns
    -------
    alpha_corner : float
        The value of regularization parameter corresponding to the
        corner of the L-curve.
    rho_corner : float
        The residual norm corresponding to ``alpha_corner``.
    eta_corner : float
        The solution norm/seminorm corresponding to ``alpha_corner``.

    References
    ----------
    .. [1] Belgey, M., Kilmerz, M. E. & Miller, E. L. (2002), `Efficient
       determination of multiple regularization parameters in a
       generalized L-curve framework`, Inverse Problems, 18, 1161-1183.
    """

    # Origin point O=(a,b)
    rhos, etas, alphas = tikh_svd(U, s, d, 2)
    a = np.log10(rhos[np.argmin(alphas)]**2)
    b = np.log10(etas[np.argmax(alphas)]**2)

    if not alpha_init:
        q = loglinspace(alphas[0], alphas[1], 3)
        alpha_init = q[1]

    def f(alpha_pre):
        rho_pre, eta_pre, _ = tikh_svd(
            U, s, d, 1, alpha_min=alpha_pre, alpha_max=alpha_pre)
        rho_pre = np.asscalar(rho_pre)
        eta_pre = np.asscalar(eta_pre)
        dum1 = (rho_pre/eta_pre)**2
        dum2 = np.log10(eta_pre**2) - b
        dum3 = np.log10(rho_pre**2) - a
        alpha_next = np.sqrt(dum1 * (dum2/dum3))
        return alpha_next

    alpha_next = f(alpha_init)
    change = abs((alpha_next/alpha_init) - 1.0)

    counter = 1
    while (change > tol) and (counter < maxiter):
        alpha_pre = alpha_next
        alpha_next = f(alpha_pre)
        change = abs((alpha_next/alpha_pre) - 1.0)
        counter += 1

    rho_corner, eta_corner, alpha_corner = map(
        np.asscalar,
        tikh_svd(U, s, d, 1, alpha_min=alpha_next, alpha_max=alpha_next))

    return (alpha_corner, rho_corner, eta_corner)


def corner_mdf_gsvd(
        U, X, LAM, MU, d, G, L, alpha_init=None, tol=1.0e-16, maxiter=1200):
    """
    Determination of Tikhonov regularization parameter using L-curve criterion.

    Minimum distance function (MDF) optimization.

    Parameters
    ----------
    U : array-like
        m-by-m matrix of data space basis vectors from the GSVD.
    X : array-like
        n-by-n nonsingular matrix computed by the GSVD.
    LAM : array-like
        m-by-n matrix, computed by the GSVD, with diagonal entries that
        may be shifted from the main diagonal.
    MU : array-like
        p-by-n diagonal matrix computed by the GSVD.
    d : array-like
        The data vector.
    G : array-like
        The system matrix (forward operator or design matrix).
    L : array-like
        The roughening matrix.
    alpha_init : float (optional)
        An appropriate initial regularization parameter.
    tol : float
        Absolute error in ``alpha_corner`` between iterations that is
        acceptable for convergence.
    maxiter : int
        Maximum number of iterations to perform.

    Returns
    -------
    alpha_corner : float
        The value of regularization parameter corresponding to the
        corner of the L-curve.
    rho_corner : float
        The residual norm corresponding to ``alpha_corner``.
    eta_corner : float
        The solution norm/seminorm corresponding to ``alpha_corner``.

    References
    ----------
    .. [1] Belge, M., Kilmer, M. E. & Miller, E. L. (2002), `Efficient
       determination of multiple regularization parameters in a
       generalized L-curve framework`, Inverse Problems, 18, 1161-1183.
    """

    # Origin point O=(a,b)
    rhos, etas, alphas = tikh_gsvd(U, X, LAM, MU, d, G, L, 2)
    a = np.log10(rhos[np.argmin(alphas)]**2)
    b = np.log10(etas[np.argmax(alphas)]**2)

    if not alpha_init:
        q = loglinspace(alphas[0], alphas[1], 9)
        alpha_init = q[4]

    def f(alpha_pre):
        rho_pre, eta_pre, _ = tikh_gsvd(
            U, X, LAM, MU, d, G, L, 1, alpha_min=alpha_pre,
            alpha_max=alpha_pre)
        rho_pre = np.asscalar(rho_pre)
        eta_pre = np.asscalar(eta_pre)
        dum1 = (rho_pre/eta_pre)**2
        dum2 = np.log10(eta_pre**2) - b
        dum3 = np.log10(rho_pre**2) - a
        alpha_next = np.sqrt(dum1 * (dum2/dum3))
        return alpha_next

    alpha_next = f(alpha_init)
    change = abs((alpha_next/alpha_init) - 1.0)

    counter = 1
    while (change > tol) and (counter < maxiter):
        alpha_pre = alpha_next
        alpha_next = f(alpha_pre)
        change = abs((alpha_next/alpha_pre) - 1.0)
        counter += 1

    rho_corner, eta_corner, alpha_corner = map(np.asscalar, tikh_gsvd(
        U, X, LAM, MU, d, G, L, 1, alpha_min=alpha_next, alpha_max=alpha_next))

    return (alpha_corner, rho_corner, eta_corner)


def lcurve_freq(
        Gspec, Dspec, deltat, order, npoints, alpha_min, alpha_max):
    """
    Tikhonov regularization in the frequency domain.

    Parameters
    ----------
    Gspec : array-like of length N
        Discrete Fourier transform of the real-valued array of the
        sampled impulse response **g**, i.e ``Gspec=np.fft.rfft(g)``.

    Dspec : array-like of length N
        Discrete Fourier transform of the real-valued array of the data
        vector **d**, i.e. ``Dspec=np.fft.rfft(d)``.

    deltat : float
        Sampling interval in time/spatial domain.

    order : int, {0, 1, 2}
        The order of the derivative to approximate.

    npoints : int
        Number of logarithmically spaced regularization parameters.

    alpha_min : float
        If specified, minimum of the regularization parameters range.

    alpha_max : float
        If specified, maximum of the reqularization parameters range.

    Returns
    -------
    rhos : array-like of length (npoints - 1)
        Vector of residual norm `||GM-D||_2`.

    etas : array-like of length (npoints - 1)
        Vector of solution norm `||M||_2` or solution seminorm
        `||LM||_2`.

    alphas : array-like of length (npoints - 1)
        Vector of corresponding regularization parameters.

    References
    ----------
    .. [1] Aster, R., Borchers, B. & Thurber, C. (2011), `Parameter
       Estimation and Inverse Problems`, Elsevier, pp 103-107.
    """

    N = Gspec.size
    if N % 2 == 0:
        ntrans = 2 * (N-1)
    else:
        ntrans = (2*N) - 1

    freqs = np.fft.rfftfreq(ntrans, d=deltat)

    alpha_min, alpha_max = sorted((alpha_min, alpha_max), reverse=True)
    alphas = loglinspace(alpha_max, alpha_min, npoints)

    GHD = np.conj(Gspec) * Dspec
    GHG = np.conj(Gspec) * Gspec
    k2p = np.power(2*np.pi*freqs, 2*order, dtype=np.complex)

    # Initialize storage spaces
    rhos = np.zeros(npoints, dtype=np.float64)
    etas = np.zeros(npoints, dtype=np.float64)

    for i, alpha in enumerate(alphas):

        # Predicted model; freq domain
        numer = GHD
        denom = GHG + np.full_like(GHG, alpha*alpha*k2p)
        idx = np.where((np.abs(numer) != 0) & (np.abs(denom) != 0))
        Mf = np.zeros_like(GHG, dtype=np.complex)
        Mf[idx] = numer[idx] / denom[idx]

        # Keep track of the residual norm for each alpha
        rhos[i] = nla.norm(Gspec*Mf - Dspec)

        # Keep track of the model norm for each alpha
        etas[i] = nla.norm(Mf)

    return (rhos, etas, alphas)


class UpdateFrequncyModel(object):

    def __init__(
            self, ax, xdata, Gspec, Dspec, deltat, order, npoints,
            alpha_min, alpha_max):
        self.ax = ax
        self.xdata = np.asarray(xdata)
        self.Gspec = Gspec
        self.Dspec = Dspec
        self.deltat = deltat
        self.order = order
        self.alphas = loglinspace(alpha_min, alpha_max, npoints)
        if Gspec.size % 2 == 0:
            self.ntrans = 2 * (Gspec.size-1)
        else:
            self.ntrans = (2*Gspec.size) - 1
        self.freqs = np.fft.rfftfreq(self.ntrans, d=self.deltat)
        self.ndata = self.xdata.size
        self.ydata = np.zeros((npoints, self.ndata), dtype=np.float64)
        self.rhos = np.zeros(npoints, dtype=np.float64)
        self.etas = np.zeros(npoints, dtype=np.float64)
        self.__GHD = np.conj(Gspec) * Dspec
        self.__GHG = np.conj(Gspec) * Gspec
        self.__k2p = np.power(2*np.pi*self.freqs, 2*order)
        self.line, = ax.plot([], [], 'k-')

    def init_func(self):
        self.ax.set_title(r'$\alpha$={}'.format(self.alphas[0]))
        self.line.set_data([], [])
        return self.line,

    def __call__(self, i):

        alpha = self.alphas[i]

        # Predicted model; freq domain
        numer = self.__GHD
        denom = self.__GHG + np.full_like(self.__GHG, alpha*alpha*self.__k2p)
        idx = np.where((np.abs(numer) != 0) & (np.abs(denom) != 0))
        Mf = np.zeros_like(self.__GHG, dtype=np.complex)
        Mf[idx] = numer[idx] / denom[idx]

        # Predicted model; time domain
        md = np.fft.irfft(Mf)

        # Store predicted model for each alpha
        self.ydata[i] = md[:self.ndata]

        # Keep track of the residual norm for each alpha
        self.rhos[i] = nla.norm(self.Gspec*Mf-self.Dspec)

        # Keep track of the model norm/seminorm for each alpha
        self.etas[i] = nla.norm(Mf)

        # Plot the newly fit model
        self.line.set_data(self.xdata, md[:len(self.xdata)])
        self.ax.set_title(r'$\alpha$={}'.format(nice_sci_notation(alpha)))

        return self.line,


__all__ = """
    tikh_svd
    tikh_gsvd
    corner_maxcurv
    corner_mdf_svd
    corner_mdf_gsvd
    lcurve_freq
    UpdateFrequncyModel
""".split()
