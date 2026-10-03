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
