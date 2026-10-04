"""Gravity-wave potential energy against a wave of known energy.

For T = T0 + A sin(2 pi z / L) on an isothermal background, N^2 = g^2 / (cp T0)
and the layer mean of (T'/T0)^2 is A^2 / (2 T0^2), so

    Ep = 0.5 (g/N)^2 <(T'/T0)^2> = cp A^2 / (4 T0)

independently of g.  Each background filter must pass short waves and
remove long ones as documented in analysis.gravity_wave_energy.
"""
import numpy as np
import pytest

from cosmic2 import analysis

T0, A = 220.0, 2.0
EXPECTED = analysis.CP_DRY * A ** 2 / (4 * T0)


def _ep(wavelength, **kw):
    z = np.arange(10.0, 50.0, 0.05)
    t = T0 + A * np.sin(2 * np.pi * z / wavelength)
    return analysis.gravity_wave_energy(z, t, **kw)["ep_J_per_kg"] / EXPECTED


@pytest.mark.parametrize("wavelength,lo,hi", [(2, 0.97, 1.0), (5, 0.88, 0.92),
                                              (10, 0.72, 0.78), (20, 0.0, 0.03)])
def test_polynomial_background_transfer(wavelength, lo, hi):
    assert lo <= _ep(wavelength) <= hi


@pytest.mark.parametrize("wavelength,lo,hi", [(2, 0.98, 1.0), (5, 0.96, 1.0),
                                              (10, 0.2, 0.3), (15, 0.0, 0.01)])
def test_highpass_background_transfer(wavelength, lo, hi):
    assert lo <= _ep(wavelength, method="highpass", cutoff_km=10.0) <= hi


def test_no_wave_no_energy_and_bad_input():
    z = np.arange(10.0, 50.0, 0.1)
    t = 290.0 - 2.0 * z            # smooth background only
    for m in analysis.GW_METHODS:
        assert analysis.gravity_wave_energy(z, t, method=m)["ep_J_per_kg"] < 1e-3
    with pytest.raises(ValueError):
        analysis.gravity_wave_energy(z, t, method="spline")
    # a profile that stops inside the layer cannot be high-passed
    short = z < 32
    assert not analysis.gravity_wave_energy(z[short], t[short],
                                            method="highpass")["found"]
