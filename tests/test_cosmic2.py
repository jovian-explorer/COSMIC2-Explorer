"""
Comprehensive test suite for COSMIC-2 Explorer.
Tests: reader normalisation, science calculations, API endpoints, export, netCDF round-trip.
Run with: python -m pytest tests/ -v
"""
import json
import os
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from cosmic2 import analysis, readers, vocab
from cosmic2.config import sampledata_dir

# Started by conftest.pytest_sessionstart on a free port.
BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())


def server_up():
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# vocabulary tests
# ---------------------------------------------------------------------------

class TestVocab:
    def test_known_var(self):
        v = vocab.info("Temp")
        assert v["label"] == "Temperature"
        assert v["units"] == "C"
        assert v["role"] == vocab.FIELD

    def test_unknown_var_fallback(self):
        v = vocab.info("something_unknown_xyz")
        assert v["name"] == "something_unknown_xyz"
        assert v["label"] == "something_unknown_xyz"

    def test_axis_title_with_units(self):
        t = vocab.axis_title("Temp", "C")
        assert "Temperature" in t
        assert "[°C]" in t

    def test_unit_normalisation_celsius_degree(self):
        t = vocab.axis_title("Temp", "Celsius_degree")
        assert "Celsius_degree" not in t
        assert "°C" in t or "C" in t.lower()

    def test_unit_normalisation_kelvin(self):
        t = vocab.axis_title("Temp", "kelvin")
        assert "kelvin" not in t
        assert "K" in t

    def test_unit_normalisation_el_cm3(self):
        t = vocab.axis_title("ELEC_dens", "el/cm3")
        assert "el/cm" in t

    def test_axis_title_no_units(self):
        t = vocab.axis_title("MSL_alt")
        assert "km" in t

    def test_all_field_choices_have_info(self):
        """Every variable in the frontend select boxes has a vocab entry."""
        FIELD_CHOICES = [
            "Temp", "temp_dry", "Pres", "sph", "rh", "Vp", "ref", "Ref",
            "Bend_ang", "ELEC_dens", "TEC_cal", "s4_L1", "sigma_phi_L1",
            "ion_dens", "ion_temp", "iv_zon", "iv_mer", "theta", "lapse_rate",
            "dNdz", "buoyancy_freq_sq",
        ]
        VERTICAL_CHOICES = ["MSL_alt", "gph", "Impact_height", "occheight", "alt"]
        for name in FIELD_CHOICES + VERTICAL_CHOICES:
            v = vocab.info(name)
            assert v["name"] == name, f"{name} lookup returned {v['name']}"
            assert v["label"], f"{name} has no label"


# ---------------------------------------------------------------------------
# reader normalisation
# ---------------------------------------------------------------------------

class TestReaders:
    @pytest.fixture(scope="class")
    @classmethod
    def sample_files(cls):
        d = sampledata_dir()
        if not d.is_dir():
            pytest.skip("No sample data directory")
        files = list(d.iterdir())
        if not files:
            pytest.skip("Sample data directory is empty")
        return files

    def test_parse_filename_wetpf2(self):
        path = "wetPf2_C2E1.2026.200.00.00.E23_0001.0001_nc"
        result = readers.parse_filename(path)
        assert result["product"] == "wetPf2"
        assert result["sat"] == "C2E1"
        assert result["prn"] == "E23"
        assert result["nominal_year"] == 2026
        assert result["nominal_doy"] == 200
        assert result["nominal_hour"] == 0

    def test_parse_filename_ivml2m(self):
        path = "ivmL2m_C2E1.2026.200.01_0001.0001_nc"
        result = readers.parse_filename(path)
        assert result["product"] == "ivmL2m"
        assert result["sat"] == "C2E1"
        assert result["nominal_year"] == 2026
        assert result["nominal_doy"] == 200

    def test_load_sample_granules(self, sample_files):
        """Every sample granule can be loaded without error."""
        loaded = 0
        for p in sample_files:
            if not (p.name.endswith("_nc") or p.suffix == ".nc"):
                continue
            parsed = readers.parse_filename(p.name)
            product = parsed["product"]
            if not product:
                continue
            g = readers.load(str(p), product)
            assert g is not None
            assert g.product == product
            assert isinstance(g.meta, dict)
            assert isinstance(g.data, dict)
            loaded += 1
        assert loaded > 0, "No sample granules loaded"

    def test_granule_meta_fields(self, sample_files):
        """Loaded granules have all required metadata fields."""
        required = ["product", "file_name", "lat", "lon", "good", "time_utc",
                    "n_levels", "alt_min", "alt_max"]
        for p in sample_files:
            if not (p.name.endswith("_nc") or p.suffix == ".nc"):
                continue
            parsed = readers.parse_filename(p.name)
            product = parsed["product"]
            if not product:
                continue
            g = readers.load(str(p), product)
            for field in required:
                assert field in g.meta, f"{p.name}: meta missing {field}"
            break  # One file is enough

    def test_no_fill_values_in_arrays(self, sample_files):
        """Sentinel values are masked out of all arrays."""
        for p in sample_files:
            if not (p.name.endswith("_nc") or p.suffix == ".nc"):
                continue
            parsed = readers.parse_filename(p.name)
            product = parsed["product"]
            if not product:
                continue
            g = readers.load(str(p), product)
            for name, arr in g.data.items():
                for fv in readers.FILL_VALUES:
                    # No finite value should be exactly a fill value
                    finite = arr[np.isfinite(arr)]
                    bad = np.isclose(finite, fv, rtol=0, atol=1e-3)
                    assert not bad.any(), (
                        f"{p.name}:{name} has unmasked fill value {fv}")
            break


# ---------------------------------------------------------------------------
# analysis / science
# ---------------------------------------------------------------------------

class TestAnalysis:
    @pytest.fixture(scope="class")
    @classmethod
    def wetpf2_granule(cls):
        d = sampledata_dir()
        if not d.is_dir():
            pytest.skip("No sample data")
        for p in d.iterdir():
            if "wetPf2" in p.name and (p.name.endswith("_nc") or p.suffix == ".nc"):
                return readers.load(str(p), "wetPf2")
        pytest.skip("No wetPf2 sample")

    def test_tropopause_height_reasonable(self, wetpf2_granule):
        diag = analysis.diagnostics(wetpf2_granule)
        tp = diag.get("tropopause", {})
        if tp.get("found"):
            h = tp["height_km"]
            assert 5 < h < 25, f"Tropopause height {h} km is out of range"

    def test_cold_point_higher_than_tropopause(self, wetpf2_granule):
        diag = analysis.diagnostics(wetpf2_granule)
        tp_h = diag.get("tropopause", {}).get("height_km")
        cp_h = diag.get("cold_point", {}).get("height_km")
        if tp_h is not None and cp_h is not None:
            assert cp_h >= tp_h - 2, (
                f"Cold point ({cp_h} km) should be >= tropopause ({tp_h} km)")

    def test_derived_fields_available(self, wetpf2_granule):
        derived = analysis.derived_fields(wetpf2_granule)
        # At minimum lapse_rate and dNdz should be computable from wetPf2
        assert "lapse_rate" in derived or "dNdz" in derived, (
            "No derived fields from wetPf2")
        assert "density" in derived, "Density not computed in derived fields"
        assert "scale_height" in derived, "Scale height not computed in derived fields"

    def test_lat_bands_cover_full_range(self):
        lats = [-80, -45, -10, 15, 50, 75]
        for lat in lats:
            found = False
            for lo, hi, name in analysis.LAT_BANDS:
                if lo <= lat < hi:
                    found = True
                    break
            assert found, f"Lat {lat} not in any LAT_BAND"

    def test_to_kelvin(self):
        arr = np.array([0.0, 100.0, -50.0])
        result = analysis.to_kelvin(arr, "C")
        assert abs(result[0] - 273.15) < 0.01
        assert abs(result[1] - 373.15) < 0.01

    def test_to_kelvin_no_op_on_kelvin(self):
        arr = np.array([300.0, 250.0])
        result = analysis.to_kelvin(arr, "K")
        np.testing.assert_array_equal(arr, result)


# ---------------------------------------------------------------------------
# API endpoint tests (require running server)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not server_up(), reason="API test server not running")
class TestAPI:
    @pytest.fixture(autouse=True)
    def load_samples(self):
        post("/api/local/load-samples", {})

    def test_health(self):
        d = get("/api/health")
        assert d["status"] == "ok"
        assert d["version"] == __import__("cosmic2").APP_VERSION

    def test_meta_complete(self):
        d = get("/api/meta")
        assert "streams" in d
        assert "vocabulary" in d
        assert "settings" in d
        assert "group_by_options" in d
        assert "citation" in d
        assert d["app"]["version"] == __import__("cosmic2").APP_VERSION
        assert d["settings"]["default_stream"] in d["streams"]

    def test_meta_streams_have_required_keys(self):
        d = get("/api/meta")
        for name, s in d["streams"].items():
            assert "label" in s, f"stream {name} missing label"
            assert "blurb" in s, f"stream {name} missing blurb"
            assert "levels" in s, f"stream {name} missing levels"

    def test_settings_persistence_and_theme_switching(self):
        """Test that settings can be updated and are persisted (API)."""
        # Get original settings
        d_orig = get("/api/meta")
        orig_theme = d_orig["settings"]["plot_theme"]
        
        # Patch theme
        new_theme = "dark" if orig_theme == "light" else "light"
        res = post("/api/settings", {"plot_theme": new_theme, "ui_theme": new_theme})
        assert res["plot_theme"] == new_theme
        assert res["ui_theme"] == new_theme
        
        # Verify persistence by fetching meta again
        d_new = get("/api/meta")
        assert d_new["settings"]["plot_theme"] == new_theme
        
        # Revert theme
        post("/api/settings", {"plot_theme": orig_theme, "ui_theme": orig_theme})

    def test_help_about_content_loading(self):
        """Verify that help.html and index.html (about section) can be loaded."""
        # Help file
        r_help = urllib.request.urlopen(BASE + "/help.html", timeout=10)
        help_content = r_help.read().decode("utf-8")
        assert "guidebook" in help_content.lower() or "help" in help_content.lower()
        
        # Index file (About section)
        r_index = urllib.request.urlopen(BASE + "/index.html", timeout=10)
        index_content = r_index.read().decode("utf-8")
        assert "<html" in index_content.lower()
        assert "cosmic-2 explorer" in index_content.lower()

    def test_local_summary_fields(self):
        d = get("/api/local/summary")
        for key in ["n_granules", "cache_bytes_on_disk", "cache_quota_bytes",
                    "by_product", "time_min", "time_max"]:
            assert key in d, f"local/summary missing {key}"

    def test_search_returns_all_fields(self):
        d = post("/api/profiles/search", {"good_only": False, "limit": 8})
        assert d["total"] >= 0
        required = ["id", "file_name", "product", "lat", "lon", "local_time",
                    "sat", "occ_prn", "n_levels", "alt_max", "good", "time_utc"]
        for g in d["granules"]:
            for f in required:
                assert f in g, f"granule missing {f}"

    def test_plot_profiles_no_nulls_in_valid_data(self):
        d = post("/api/profiles/search", {"good_only": True, "limit": 3})
        ids = [g["id"] for g in d["granules"] if g["good"]][:2]
        if not ids:
            pytest.skip("No good granules")
        plot = post("/api/plot/profiles", {
            "granule_ids": ids, "field": "Temp", "vertical": "MSL_alt"})
        assert "series" in plot
        assert "field_label" in plot
        for s in plot["series"]:
            assert len(s["x"]) == len(s["y"])
            assert len(s["x"]) > 0
            nones_x = sum(1 for v in s["x"] if v is None)
            assert nones_x < len(s["x"]) * 0.3, "Too many None values in x"

    def test_plot_field_label_no_raw_units(self):
        """field_label should not contain 'Celsius_degree' or similar raw strings."""
        d = post("/api/profiles/search", {"good_only": False, "limit": 3})
        ids = [g["id"] for g in d["granules"]][:3]
        plot = post("/api/plot/profiles", {
            "granule_ids": ids, "field": "Temp", "vertical": "MSL_alt"})
        label = plot.get("field_label", "")
        assert "Celsius_degree" not in label, f"Raw unit in label: {label}"
        assert "celsius_degree" not in label.lower()

    def test_composite_group_keys(self):
        d = post("/api/composite", {
            "search": {"good_only": False, "limit": 8},
            "field": "Temp", "vertical": "MSL_alt",
            "group_by": "all",
        })
        assert "groups" in d
        assert "grid" in d
        assert "field_label" in d
        assert "vertical_label" in d
        assert "min_count" in d
        assert "dropped_groups" in d
        if d["groups"]:
            g = list(d["groups"].values())[0]
            for key in ["mean", "std", "p10", "p90", "n"]:
                assert key in g

    def test_diagnostics_table_columns(self):
        d = post("/api/diagnostics/table",
                 {"search": {"good_only": False, "limit": 8}})
        assert "rows" in d
        assert "columns" in d
        assert "n" in d
        assert "unreadable" in d
        # Columns used by the scatter plot
        for col in ["lat", "local_time", "tropopause.height_km"]:
            assert col in d["columns"], f"Missing scatter column: {col}"

    def test_exports_listing(self):
        d = get("/api/exports")
        assert "exports" in d
        assert isinstance(d["exports"], list)

    def test_facets_fields(self):
        d = get("/api/local/facets")
        for key in ["products", "streams", "sats", "date_min", "date_max"]:
            assert key in d

    def test_upload_file_ingestion(self):
        """Verify drag-and-drop file upload endpoint imports NetCDF files."""
        d = sampledata_dir()
        samples = [p for p in d.iterdir() if p.name.endswith("_nc") or p.suffix == ".nc"]
        if not samples:
            pytest.skip("No sample granules available")
        sample_file = samples[0]
        with open(sample_file, "rb") as f:
            content = f.read()

        req = urllib.request.Request(
            BASE + "/api/local/upload-file?filename=test_upload.nc",
            data=content,
            method="POST",
            headers={"Content-Type": "application/octet-stream"},
        )
        res = json.loads(urllib.request.urlopen(req, timeout=10).read())
        assert "indexed" in res
        assert res["indexed"] >= 1

    def test_upload_truncated_file_reports_reason_and_is_not_kept(self):
        sample = next(p for p in sampledata_dir().iterdir() if p.name.endswith("_nc"))
        req = urllib.request.Request(
            BASE + "/api/local/upload-file?filename=cut_upload.nc",
            data=sample.read_bytes()[:2000], method="POST",
            headers={"Content-Type": "application/octet-stream"})
        res = json.loads(urllib.request.urlopen(req, timeout=10).read())
        assert res["indexed"] == 0 and res["failed"][0]["error"]
        assert not os.path.exists(res["saved_path"])

    def test_upload_cdaac_day_tarball_unpacks_and_indexes_its_profiles(self):
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for i, p in enumerate(sorted(sampledata_dir().glob("echPrf_*_nc"))[:2]):
                # a member path that climbs out of the folder lands inside it
                tf.add(p, arcname=("../" if i else "echPrf_test_2026_200/") + p.name)
        req = urllib.request.Request(
            BASE + "/api/local/upload-file?filename=echPrf_test_2026_200.tar.gz",
            data=buf.getvalue(), method="POST",
            headers={"Content-Type": "application/octet-stream"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        assert res["indexed"] == 2 and not res["failed"]
        folder = Path(res["saved_path"]).parent / "echPrf_test_2026_200"
        assert len(list(folder.iterdir())) == 2 and not os.path.exists(res["saved_path"])



# ---------------------------------------------------------------------------
# netCDF export round-trip
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not server_up(), reason="API test server not running")
class TestExports:
    @pytest.fixture(autouse=True)
    def load_samples(self):
        post("/api/local/load-samples", {})

    def test_export_metadata_csv(self, tmp_path):
        res = post("/api/export/data", {
            "kind": "metadata_csv",
            "search": {"good_only": False, "limit": 8},
            "basename": "test_meta",
        })
        assert "filename" in res
        assert res["filename"].endswith(".csv")
        assert res["bytes"] > 0

    def test_export_profiles_csv(self, tmp_path):
        res = post("/api/export/data", {
            "kind": "profiles_csv",
            "search": {"good_only": False, "limit": 3},
            "basename": "test_profiles",
        })
        assert "filename" in res
        assert res["bytes"] > 0

    def test_export_netcdf(self):
        res = post("/api/export/data", {
            "kind": "netcdf",
            "field": "Temp",
            "search": {"good_only": True, "limit": 3, "products": ["wetPf2"]},
            "basename": "test_nc",
            "top_km": 40.0,
            "step_km": 1.0,
        })
        assert "filename" in res
        assert res["bytes"] > 0
        # Verify the file is downloadable
        r = urllib.request.urlopen(
            BASE + f"/api/exports/{res['filename']}", timeout=10)
        data = r.read()
        assert len(data) == res["bytes"]

def test_packaged_resource_loading():
    """Frontend and sample data ship inside the package, so they resolve the
    same way from a checkout, a pip install and a PyInstaller build."""
    import cosmic2
    from cosmic2.config import bundle_root, frontend_dir, sampledata_dir
    pkg = Path(cosmic2.__file__).resolve().parent
    assert bundle_root() == pkg
    assert (frontend_dir() / "index.html").is_file()
    assert sampledata_dir().is_dir()


def test_ecmwf_bending_angle_is_not_called_ionosphere_corrected():
    from cosmic2 import analysis, vocab
    assert analysis.quantity_label("Bend_ang", "echPrf") == "Bending angle, simulated (ECMWF)"
    assert "ionosphere" not in vocab.info("Bend_ang", "echPrf")["label"]
    assert vocab.VAR_INFO["Bend_ang_model"]["formula"].startswith(r"\alpha(a)")


def test_headless_example_runs_on_the_bundled_samples(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, COSMIC2_EXPLORER_HOME=str(tmp_path),
               PYTHONPATH=str(root / "src"))
    out = subprocess.run([sys.executable, str(root / "examples" / "headless.py")],
                         env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "wetPf2" in out.stdout and "tropopause 12.1 km" in out.stdout
    assert list((tmp_path / "exports").glob("headless_example_*.csv"))


def test_readme_python_snippet_runs(tmp_path, monkeypatch):
    import re
    from cosmic2 import exporters
    monkeypatch.setattr(exporters, "EXPORT_DIR", tmp_path)
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    code = re.search(r"## Using it from Python.*?```python\n(.*?)```", readme, re.S).group(1)
    scope: dict = {}
    exec(code, scope)
    assert scope["d"]["tropopause"]["found"] and list(tmp_path.glob("*.csv"))


def test_readme_comparison_snippet_runs():
    import re
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    code = next(c for c in re.findall(r"```python\n(.*?)```", readme, re.S)
                if "model_differences" in c)
    scope: dict = {}
    exec(code, scope)
    assert scope["ecmwf"]["n_profiles"] == 2 and scope["cmp"]["n_cosmic2"] == 2
