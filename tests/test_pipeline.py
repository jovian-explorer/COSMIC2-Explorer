import pytest
import numpy as np
from cosmic2.pipeline import apply_pipeline, ProcessedProfile

def test_pipeline_outlier_sigma():
    z = np.arange(100.0)
    v = np.sin(z * 0.1)
    # Add a huge outlier
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, outlier_method="sigma", outlier_kwargs={"threshold": 2.0})
    
    # 50th index should be nan
    assert np.isnan(prof.v[50])
    assert not prof.mask[50]
    
    # Provenance
    assert len(prof.provenance) > 0
    assert prof.provenance[0].operation == "outlier_removal"
    assert prof.provenance[0].parameters["method"] == "sigma"

def test_pipeline_outlier_mad():
    z = np.arange(100.0)
    v = np.ones(100)
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, outlier_method="mad", outlier_kwargs={"threshold": 3.0})
    
    assert np.isnan(prof.v[50])
    assert not prof.mask[50]

def test_pipeline_smoothing_gaussian():
    z = np.arange(100.0)
    v = np.random.randn(100)
    
    prof = apply_pipeline(z, v, smooth_method="gaussian", smooth_kwargs={"window": 5})
    
    # Gaussian smoothing should reduce variance
    assert np.std(prof.v) < np.std(prof.original_v)
    
    # Provenance check
    ops = [p.operation for p in prof.provenance]
    assert "smoothing" in ops

def test_pipeline_uncertainty():
    z = np.arange(10.0)
    v = np.arange(10.0)
    
    prof = apply_pipeline(z, v, uncert_method="standard_deviation", uncert_kwargs={"window": 3})
    
    assert prof.uncertainty is not None
    # A noise-free straight line has no scatter about its running mean, so
    # its interior error bars are zero (the raw rolling std would be 1.0 here,
    # i.e. the slope, not an uncertainty).
    np.testing.assert_allclose(prof.uncertainty[2:8], 0.0, atol=1e-12)


def test_pipeline_uncertainty_recovers_noise_on_a_steep_profile():
    rng = np.random.default_rng(1)
    z = np.arange(4000.0)
    v = 300.0 - 0.5 * z + rng.normal(0.0, 0.5, z.size)   # gradient >> noise
    prof = apply_pipeline(z, v, uncert_method="standard_deviation",
                          uncert_kwargs={"window": 9})
    assert np.nanmedian(prof.uncertainty) == pytest.approx(0.5, rel=0.1)

def test_pipeline_filtering_median():
    z = np.arange(100.0)
    v = np.ones(100)
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, smooth_method="median", smooth_kwargs={"window": 5})
    
    # Median filter should remove the spike entirely
    assert prof.v[50] == 1.0
    
    ops = [p.operation for p in prof.provenance]
    assert "smoothing" in ops

def test_pipeline_filtering_savgol():
    z = np.arange(100.0)
    v = np.sin(z * 0.1)
    
    prof = apply_pipeline(z, v, smooth_method="savgol", smooth_kwargs={"window": 5, "polyorder": 2})
    
    # Savgol preserves the polynomial shape locally
    assert np.all(np.isfinite(prof.v))
    
    ops = [p.operation for p in prof.provenance]
    assert "smoothing" in ops

def test_pipeline_outlier_iqr():
    z = np.arange(100.0)
    v = np.ones(100)
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, outlier_method="iqr", outlier_kwargs={"threshold": 1.5})
    
    assert np.isnan(prof.v[50])
    assert not prof.mask[50]

def test_pipeline_outlier_percentile():
    z = np.arange(100.0)
    v = np.ones(100)
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, outlier_method="percentile", outlier_kwargs={"lower": 1.0, "upper": 99.0})
    
    assert np.isnan(prof.v[50])
    assert not prof.mask[50]

def test_pipeline_smoothing_moving_average():
    z = np.arange(100.0)
    v = np.ones(100)
    v[50] = 100.0
    
    prof = apply_pipeline(z, v, smooth_method="moving_average", smooth_kwargs={"window": 5})
    
    # moving average of [1, 1, 100, 1, 1] is 104/5 = 20.8
    assert np.isclose(prof.v[50], 20.8)

def test_pipeline_uncertainty_standard_error():
    rng = np.random.default_rng(2)
    z = np.arange(4000.0)
    v = np.arange(4000.0) + rng.normal(0.0, 1.0, z.size)

    prof = apply_pipeline(z, v, uncert_method="standard_error", uncert_kwargs={"window": 9})

    assert prof.uncertainty is not None
    # sigma = 1 noise, 9 levels per window: standard error ~ 1/3
    assert np.nanmedian(prof.uncertainty) == pytest.approx(1.0 / 3.0, rel=0.1)


def test_inapplicable_savgol_is_not_recorded_as_applied():
    z = np.arange(20.0)
    v = np.sin(z)
    prof = apply_pipeline(z, v, smooth_method="savgol",
                          smooth_kwargs={"window": 5, "polyorder": 6})
    np.testing.assert_array_equal(prof.v, v)
    assert "smoothing" not in [p.operation for p in prof.provenance]


def test_provenance_records_the_running_version(monkeypatch):
    from cosmic2 import pipeline
    from cosmic2.config import APP_VERSION
    prof = apply_pipeline(np.arange(10.0), np.arange(10.0), smooth_method="median",
                          smooth_kwargs={"window": 3})
    assert prof.provenance[0].software_version == APP_VERSION
    assert pipeline.ProvenanceRecord.__dataclass_fields__["software_version"].default \
        is APP_VERSION


def test_outliers_are_departures_from_the_profile_not_extreme_values():
    # a clean exponential refractivity profile, sampled like atmPrf (20 m,
    # 0.1 % noise), keeps its lower levels; only the spike goes
    import numpy as np
    from cosmic2 import pipeline
    z = np.arange(0.0, 60.0, 0.02)
    n = 300.0 * np.exp(-z / 7.0) * (1 + 1e-3 * np.random.default_rng(1).standard_normal(z.size))
    n[200] *= 1.2
    for method in ("mad", "iqr"):
        p = pipeline.apply_pipeline(z, n, outlier_method=method, outlier_kwargs={"threshold": 5.0})
        assert np.flatnonzero(np.isnan(p.v)).tolist() == [200], method
    p = pipeline.apply_pipeline(z, n, outlier_method="sigma", outlier_kwargs={"threshold": 3.0})
    assert np.flatnonzero(np.isnan(p.v)).tolist() == [200]
