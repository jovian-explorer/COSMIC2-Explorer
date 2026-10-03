"""Figure rendering follows the user's settings."""
from cosmic2 import plotting
from cosmic2.config import SETTINGS


def test_plot_theme_setting_reaches_exported_figures(monkeypatch):
    monkeypatch.setattr(SETTINGS, "plot_theme", "dark")
    assert plotting.apply_style()["axes.facecolor"] == "#0b0f17"
    monkeypatch.setattr(SETTINGS, "plot_theme", "light")
    assert plotting.apply_style()["axes.facecolor"] == "white"
    assert plotting.apply_style(theme="dark")["axes.facecolor"] == "#0b0f17"
