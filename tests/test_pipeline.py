import pytest
import numpy as np
from backend.cosmic2.pipeline import apply_pipeline, ProcessedProfile

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
    # For a straight line with slope 1, rolling std over 3 elements is 1.0 (since elements are spaced by 1)
    # Using sample std (ddof=1) over [0,1,2] -> mean 1, diff [-1, 0, 1] -> var = (1+0+1)/2 = 1. std = 1
    np.testing.assert_allclose(prof.uncertainty[1:9], 1.0, rtol=1e-5)

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
    z = np.arange(10.0)
    v = np.arange(10.0)
    
    prof = apply_pipeline(z, v, uncert_method="standard_error", uncert_kwargs={"window": 3})
    
    assert prof.uncertainty is not None
    # For a straight line with slope 1, rolling std over 3 elements is 1.0. 
    # sqrt(3) is ~1.732. std_err = 1.0 / 1.732 = 0.57735
    np.testing.assert_allclose(prof.uncertainty[1:9], 1.0 / np.sqrt(3), rtol=1e-4)
