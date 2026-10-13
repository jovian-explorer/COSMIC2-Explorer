"""Figure rendering follows the user's settings."""
from cosmic2 import plotting
from cosmic2.config import SETTINGS


def test_plot_theme_setting_reaches_exported_figures(monkeypatch):
    monkeypatch.setattr(SETTINGS, "plot_theme", "dark")
    assert plotting.apply_style()["axes.facecolor"] == "#0b0f17"
    monkeypatch.setattr(SETTINGS, "plot_theme", "light")
    assert plotting.apply_style()["axes.facecolor"] == "white"
    assert plotting.apply_style(theme="dark")["axes.facecolor"] == "#0b0f17"


def _profile_fig(**kw):
    import numpy as np
    items = [{"x": np.linspace(200, 300, 200), "y": np.linspace(0, 30, 200),
              "label": "a", "value": 1.0}]
    return plotting.profile_figure(items, "Temp", "MSL_alt", dpi=100, **kw)


def test_caption_below_the_axes_is_not_clipped():
    import io
    from PIL import Image
    fig = _profile_fig(caption="A caption under the plot.")
    w, h = fig.get_size_inches() * 100
    im = Image.open(io.BytesIO(plotting.render(fig, "png", 100)))
    # The caption sits below the figure box and survives only through the
    # tight bounding box, which makes the image taller than the bare figure.
    assert im.size[1] > h


def test_pdf_embeds_editable_truetype_not_type3():
    pdf = plotting.render(_profile_fig(), "pdf", 100)
    assert b"/Type3" not in pdf


def test_concurrent_exports_keep_their_own_dpi():
    import io
    import threading
    from PIL import Image
    sizes = {60: set(), 200: set()}

    def work(dpi):
        for _ in range(6):
            import numpy as np
            items = [{"x": np.linspace(200, 300, 200), "y": np.linspace(0, 30, 200),
                      "label": "a", "value": 1.0}]
            fig = plotting.profile_figure(items, "Temp", "MSL_alt", dpi=dpi)
            sizes[dpi].add(Image.open(io.BytesIO(plotting.render(fig, "png", dpi))).size)

    threads = [threading.Thread(target=work, args=(d,)) for d in (60, 200, 60, 200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sizes[60]) == 1 and len(sizes[200]) == 1


def test_log_axis_is_skipped_for_data_without_positive_values():
    import warnings
    import numpy as np
    items = [{"x": np.linspace(-80, 20, 50), "y": np.linspace(0, 30, 50),
              "label": "a", "value": 1.0}]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig = plotting.profile_figure(items, "Temp", "MSL_alt", logx=True,
                                      x_units="C", dpi=72)
        items[0]["x"] = -items[0]["x"] - 100        # all negative
        fig2 = plotting.profile_figure(items, "Temp", "MSL_alt", logx=True, dpi=72)
    assert fig.axes[0].get_xscale() == "log"         # some positive values
    assert fig2.axes[0].get_xscale() == "linear"


def test_figures_use_product_aware_axis_titles():
    import numpy as np
    fig = _profile_fig(x_label="Dry temperature [C]")
    assert fig.axes[0].get_xlabel() == "Dry temperature [C]"
    z = np.linspace(0, 30, 50)
    fig = plotting.panels_figure([{"x": z, "y": z, "x_var": "Temp", "units": "C",
                                   "y_var": "MSL_alt", "product": "atmPrf"}], dpi=100)
    assert fig.axes[0].get_xlabel().startswith("Dry temperature")


def test_scatter_figure_titles_name_the_diagnostics():
    """Scatter axes and colour bar were labelled with raw column names."""
    from cosmic2 import vocab
    fig = plotting.scatter_figure([1, 2, 3], [15, 16, 17], "lat",
                                  "tropopause.height_km", color=[1, 2, 3],
                                  color_var="gravity_waves.ep_J_per_kg", dpi=80)
    ax, cax = fig.axes[0], fig.axes[1]
    assert ax.get_ylabel() == "WMO tropopause height [km]"
    assert ax.get_xlabel() == "Latitude [°N]"
    assert cax.get_ylabel() == "Gravity-wave potential energy Ep [J/kg]"
    # every numeric column the diagnostics table gives the bundled samples
    # has a title of its own
    from cosmic2 import analysis, readers
    from cosmic2.config import sampledata_dir
    cols = set()
    for p in sampledata_dir().iterdir():
        g = readers.load(str(p))
        row = analysis.diagnostics_row({
            "path": str(p), "product": g.product, "id": "x", "file_name": p.name,
            "time_utc": None, "lat": 0.0, "lon": 0.0, "local_time": 0.0,
            "sat": "", "good": 1})
        cols |= {k for k, v in (row or {}).items()
                 if isinstance(v, (int, float)) and not isinstance(v, bool)}
    cols -= {"good", "ducting.critical_gradient"}   # a constant, not offered
    assert cols and cols <= set(vocab.DIAG_COLUMNS), cols - set(vocab.DIAG_COLUMNS)


def test_profile_figure_gives_the_height_its_units():
    items = [{"x": [1.0, 2.0], "y": [0.0, 1.0], "label": "a"}]
    fig = plotting.profile_figure(items, "Temp", "MSL_alt", dpi=72)
    assert fig.axes[0].get_ylabel() == "Altitude above mean sea level [km]"
    fig = plotting.profile_figure(items, "ion_dens", "elapsed_h", dpi=72)
    assert fig.axes[0].get_ylabel() == "Time since the first sample [h]"


def test_composite_figure_of_no_group_says_so():
    import pytest
    with pytest.raises(ValueError, match="nothing to draw"):
        plotting.composite_figure({"grid": [0.0, 1.0], "groups": {}, "min_count": 3,
                                   "field": "Temp", "vertical": "MSL_alt"})


def test_vector_figures_have_every_glyph_the_titles_use():
    # degree, superscripts and a middle dot in the titles: a font without them
    # would print empty boxes (matplotlib warns "Glyph ... missing from font")
    import warnings
    items = [{"x": [1.0, 2.0], "y": [0.0, 1.0], "label": "a"}]
    fig = plotting.profile_figure(items, "ion_dens", "lat", dpi=72,
                                  x_label="Ion density [ions/cm³] · N² [s⁻²] · T [°C]")
    for fmt in ("pdf", "svg"):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            data = plotting.render(fig, fmt, 72)
        missing = [str(w.message) for w in caught if "missing" in str(w.message).lower()]
        assert not missing, (fmt, missing)
        if fmt == "pdf":
            assert b"/FontFile2" in data           # TrueType embedded, text stays editable
