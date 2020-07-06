"""Strategies for property-based testing."""

from functools import lru_cache

import hypothesis.extra.numpy as hynp
import hypothesis.strategy as hyst
import numpy as np


@hyst.composite
def polynomial_functions(
    draw, domain=(0.0, 1.0), max_val=None, terms=hyst.integers(1, 11)
):
    """Generates callable functions f(x) which are polynomials.

    Parameters
    ----------
    domain: Tuple[float, float]
        The domain over which the resulting function should be called. It can
        be called outside of this range, but values may be very large.
    max_coeff: float
        The maximum value of the coefficient on any term in the series.
    terms: int or strategy for ints
        The number of terms to include in the series.

    Returns
    -------
    : Callable[[ArrayLike], ArrayLike]
        A smoothly varying function.

    """
    min_val = -max_val if max_val else max_val
    nterms = draw(terms)
    coeffs = draw(
        hyst.lists(
            draw(hyst.floats(min_val, max_val, allow_infinity=False, allow_nan=False)),
            min_size=nterms,
            max_size=nterms,
        )
    )

    def f(x):
        x = (x - domain[0]) / (domain[1] - domain[0])
        term = 1
        y = 0.0
        for coeff in coeffs:
            y += coeff * term
            term *= x
        return y

    return f


@hyst.composite
def sine_functions(draw, domain=(0.0, 1.0), max_val=None, terms=hyst.integers(0, 10)):
    """Generates callable functions f(x) which are sums of sines and cosines.

    Parameters
    ----------
    domain: Tuple[float, float]
        The domain over which the resulting function should be called. It can
        be called outside of this range, but will exhibit periodicity.
    max_coeff: float
        The maximum value of the coefficient on any term in the series.
    terms: int or strategy for ints
        The number of sine terms to include in the series.

    Returns
    -------
    : Callable[[ArrayLike], ArrayLike]
        A smoothly varying function.

    """
    min_val = -max_val if max_val else max_val
    nterms = draw(terms)
    sin_coeffs = draw(
        hyst.lists(
            draw(hyst.floats(min_val, max_val, allow_infinity=False, allow_nan=False)),
            min_size=nterms,
            max_size=nterms,
        )
    )
    cos_coeffs = draw(
        hyst.lists(
            draw(hyst.floats(min_val, max_val, allow_infinity=False, allow_nan=False)),
            min_size=nterms,
            max_size=nterms,
        )
    )
    offset = draw(hyst.floats(min_val, max_val, allow_infinity=False, allow_nan=False))

    def f(x):
        x = (x - domain[0]) / (domain[1] - domain[0])
        y = offset
        for i, (scoeff, ccoeff) in enumerate(zip(sin_coeffs, cos_coeffs)):
            y += scoeff * np.sin(np.pi * (i + 1) * x)
            y += ccoeff * np.cos(np.pi * (i + 1) * x)
        return y

    return f


@hyst.composite
def smooth_functions(draw, domain=(0.0, 1.0), max_val=None, terms=hyst.integers(0, 10)):
    """Generates callable functions f(x) which are smoothly varying

    Parameters
    ----------
    domain: Tuple[float, float]
        The domain over which the resulting function should be called. It can
        be called outside of this range, but will exhibit periodicity.
    max_coeff: float
        The maximum value of the coefficient on any term in the series.
    terms: int or strategy for ints
        The number of non-constant terms to include in the function.

    Returns
    -------
    : Callable[[ArrayLike], ArrayLike]
        A smoothly varying function.

    """
    nterms = draw(terms()) + 1
    return draw(
        hyst.one_of(
            polynomial_functions(domain, max_val, nterms + 1),
            sine_functions(domain, max_val, nterms),
        )
    )


@hyst.composite
def noisy_functions(draw, func, rel_sigma=0.02, abs_sigma=1e-3, cache=False):
    """Returns a function which is ``func`` plus some Guassian noise.

    Results are of the form ::

        y = f(x)
        (1. + random.gauss(y, rel_sigma))*y + random.guass(0, abs_sigma)

    By default, successive calls with the same ``x`` will have
    different noise. This behaviour can be changed by setting the
    argument ``cache=True``, but this will use quite a lot of memory.

    Parameters
    ----------
    func: Callable[[...], float]
        A function to which random noise should be added.
    rel_sigma: float
        The standard deviation of the Guassian noise profile for the relative
        error.
    abs_sigma: float
        The standard deviation of the Guassian noise profile for the absolute
        error.
    cache: bool
        If true, the noisy function will save results to ensure future calls
        with the same value of ``x`` will give the same ``y``.

    Returns
    -------
    : Callable[[...], float]
        A function which is the equivalent of the input function plus some
        random noise.

    """
    rand = draw(hyst.randoms())

    def noisy(*args):
        y = func(*args)
        return (1 + rand.gauss(y, rel_sigma)) * y + rand.gauss(0.0, abs_sigma)

    if cache:
        return lru_cache(None)(noisy)
    return noisy


@hyst.composite
def irregular_space(
    draw, start, stop, num=50, endpoint=True, retstep=False, dtype=None
):
    """Strategy for generating arrays where values irregularly spaced between
    two endpoints. Interface mimics that of :py:func:`numpy.linspace`. This may
    be useful for generating irregular coordinate grids.

    Parameters
    ----------
    start: float
        The starting value of the sequence.
    stop: float
        The end value of the sequence, unless endpoint is set to False. In that
        case, the sequence consists of all but the last of num + 1 evenly
        spaced samples, so that stop is excluded. Note that the step size
        changes when endpoint is False.
    num: int, optional
        Number of samples to generate. Default is 50. Must be non-negative.
    endpoint: bool, optional
        If True, stop is the last sample. Otherwise, it is not included.
        Default is True.
    retstep: bool, optional
        If True, return (samples, steps), where steps is the spacing between
        samples.
    dtype: dtype, optional
        The type of the output array. If dtype is not given, infer the data
        type from the other input arguments.

    Returns
    -------
    samples: ndarray
        An array of ``num`` irregularly spaced samples.

    steps: ndarray, optional
        Only returned if ``restep`` is True. Size of spacing between samples.

    """
    space_func = draw(smooth_functions())
    n = num - 1 if endpoint else num
    lin = np.linspace(0.0, 1.0, n, True, False, dtype)
    spacing = abs(space_func(lin)) + 1 / (num * 10)
    norm = (stop - start) / spacing.sum()
    spacing *= norm
    if not endpoint:
        spacing = spacing[:-1]
    result = np.empty(num, dtype)
    result[0] = 0.0
    np.cumsum(spacing, out=result[1:])
    if retstep:
        return result + start, spacing
    return result + start


@hyst.composite
def arbitrary_coordinates(
    draw, min_value=(None, None, None), max_value=(None, None, None), unique=False
):
    """Strategy to generate valid sets of coordinates as input for conversions.

    Parameters
    ----------
    min_value
        The minimum value to use for each coordinate
    max_value
        The maximum value to use for each coordinate
    unique
        Whether values in each coordinate array should be unique

    Returns
    -------
    x1 : ArrayLike
        The first spatial coordinate
    x2 : ArrayLike
        The second spatial coordinate
    t : ArrayLike
        The time coordinate

    """
    shapes = draw(
        hynp.mutually_broadcastable_shapes(num_shapes=3, max_dims=3)
    ).input_shapes
    return draw(
        hynp.arrays(
            np.float,
            shapes[i],
            elements=hyst.floats(
                min_value[i], max_value[i], allow_nan=False, allow_infinity=False
            ),
            unique=unique,
        )
        for i in range(3)
    )


@hyst.composite
def basis_coordinates(draw, min_value=(None, None, None), max_value=(None, None, None)):
    """Generates sets of coordinates to form the basis/grid for a
    coordinate system. The grid spacing will be smoothly varying, but
    not necessarily regular.

    Parameters
    ----------
    min_value
        The minimum value to use for each coordinate
    max_value
        The maximum value to use for each coordinate

    Returns
    -------
    x1 : ArrayLike
        The first spatial coordinate
    x2 : ArrayLike
        The second spatial coordinate
    t : ArrayLike
        The time coordinate

    """
    min_vals = [
        min_value[i] if min_value[i] is not None else draw(hyst.floats(-1e6, 1e6))
        for i in range(3)
    ]
    max_vals = [
        max_value[i]
        if max_value[i] is not None
        else draw(hyst.floats(min_vals[i], 1e7))
        for i in range(3)
    ]
    x1 = draw(irregular_space(min_vals[0], max_vals[0], draw(hyst.integers(1))))
    x2 = np.expand_dims(
        draw(irregular_space(min_vals[1], max_vals[1], draw(hyst.integers(1)))), 0
    )
    t = np.expand_dims(
        draw(irregular_space(min_vals[1], max_vals[1], draw(hyst.integers(1)))), (0, 1)
    )
    return x1, x2, t
