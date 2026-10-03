"""Server-side, publication-grade figure rendering.

The browser gets interactive Plotly charts; this module exists for the moment
the user wants a file to put in a paper.  Matplotlib is driven with an
explicit three-size font ladder, outward ticks, frameless legends and direct
end-of-line series labels, and writes PNG/PDF/SVG at a configurable DPI.

Coastlines for the map export are decoded from the bundled TopoJSON, so no
mapping toolkit is required and the export works offline.
"""
from __future__ import annotations

import io
import json
import threading
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterable, Sequence

import matplotlib
import matplotlib.ticker
matplotlib.use("Agg")  # no display in a packaged desktop app
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from . import analysis, vocab
from .config import SETTINGS, frontend_dir

# Font ladder: base / annotation / tick.  Three sizes, mapped to role.
SIZES = (9, 8, 7)
FOCAL = "#0284c7"        # focal series (celestial blue)
ACCENT = "#e11d48"       # single alarm/highlight hue
META_GREY = "#64748b"
CATEGORICAL = ["#0284c7", "#f97316", "#10b981", "#8b5cf6", "#f43f5e", "#06b6d4", "#eab308", "#ec4899"]


def apply_style(dpi: int | None = None, theme: str | None = None) -> dict:
    """Return rcParams for a publication figure.

    ``theme`` defaults to the "Plot Theme" setting (which no figure read
    before, so choosing Dark had no effect on exports).
    """
    if theme is None:
        theme = getattr(SETTINGS, "plot_theme", "light")
    base, ann, tick = SIZES
    fg = "#0f172a" if theme == "light" else "#f1f5f9"
    bg = "white" if theme == "light" else "#0b0f17"
    return {
        "figure.dpi": dpi or SETTINGS.plot_dpi,
        "savefig.dpi": dpi or SETTINGS.plot_dpi,
        "figure.facecolor": bg, "axes.facecolor": bg, "savefig.facecolor": bg,
        "font.size": base, "axes.titlesize": base, "axes.labelsize": base,
        "legend.fontsize": ann, "xtick.labelsize": tick, "ytick.labelsize": tick,
        "text.color": fg, "axes.labelcolor": fg, "axes.edgecolor": fg,
        "xtick.color": fg, "ytick.color": fg,
        "axes.titlelocation": "left", "axes.titleweight": "regular",
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.direction": "out", "ytick.direction": "out",
        "legend.frameon": False, "legend.handlelength": 1.6,
        "lines.linewidth": 1.6, "lines.markersize": 3.5,
        "axes.grid": True, "grid.alpha": 0.18, "grid.linewidth": 0.5,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
        "pdf.fonttype": 42, "ps.fonttype": 42,  # editable text in vector output
    }


# rcParams are process-global and FastAPI serves requests on a thread pool,
# so two figure exports at once could build or save with each other's DPI,
# theme or fonts.  One lock serialises the (short) styled sections.
_STYLE_LOCK = threading.RLock()


@contextmanager
def _styled(dpi: int | None = None):
    with _STYLE_LOCK, plt.rc_context(apply_style(dpi)):
        yield


def safe_mathtext(text: str) -> str:
    """Ensure title or label text compiles safely without Matplotlib mathtext errors."""
    if not text or not isinstance(text, str):
        return ""
    if text.count("$") % 2 != 0:
        text = text.replace("$", r"\$")
    return text


def _series_key(ax, labels, colors) -> None:
    """Identify each series.

    Direct end-of-line labels are the usual preference, but every multi-series
    plot here shares a vertical axis (altitude) and the series all terminate at
    the same height, so their labels would stack on one point.  A frameless
    legend parked in the panel's emptiest corner is the correct choice for this
    data shape.
    """
    handles = [plt.Line2D([], [], color=c, linewidth=1.3) for c in colors]
    ax.legend(handles, labels, loc="best", frameon=False,
              fontsize=SIZES[1], handlelength=1.4, borderaxespad=0.2,
              labelspacing=0.35)


def _thin_ticks(ax, axis: str = "x", nbins: int = 4) -> None:
    """Fewer, pruned ticks so labels of abutting panels cannot collide."""
    loc = matplotlib.ticker.MaxNLocator(nbins=nbins, prune="both")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_locator(loc)


# ---------------------------------------------------------------------------
# coastlines
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2)
def coastlines(resolution: str = "110m") -> list[np.ndarray]:
    """Decode bundled TopoJSON coastlines into (N,2) lon/lat polylines."""
    path = frontend_dir() / "vendor" / "topojson" / f"world_{resolution}.json"
    if not path.exists():
        return []
    topo = json.loads(path.read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = np.empty((len(arc), 2))
        for i, (dx, dy) in enumerate(arc):
            x += dx
            y += dy
            pts[i] = (x * sx + tx, y * sy + ty)
        arcs.append(pts)

    def resolve(idx_list):
        out = []
        for i in idx_list:
            out.append(arcs[~i][::-1] if i < 0 else arcs[i])
        return np.vstack(out) if out else np.empty((0, 2))

    lines = []
    for geom in topo["objects"]["coastlines"].get("geometries", []):
        if geom["type"] == "LineString":
            lines.append(resolve(geom["arcs"]))
        elif geom["type"] == "MultiLineString":
            for part in geom["arcs"]:
                lines.append(resolve(part))
    return [ln for ln in lines if len(ln) > 1]


def _draw_basemap(ax, resolution: str = "110m") -> None:
    lines = coastlines(resolution)
    if lines:
        ax.add_collection(LineCollection(lines, colors=META_GREY, linewidths=0.4,
                                         zorder=1))
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 60))
    ax.set_yticks(range(-90, 91, 30))
    ax.set_xlabel("Longitude [deg E]")
    ax.set_ylabel("Latitude [deg N]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.15, linewidth=0.4)


# ---------------------------------------------------------------------------
# figure builders
# ---------------------------------------------------------------------------

def profile_figure(series: Sequence[dict], x_var: str, y_var: str,
                   title: str = "", x_units: str = "", y_units: str = "",
                   color_by: str | None = None, logx: bool = False,
                   invert_y: bool = False, caption: str = "",
                   figsize: tuple[float, float] = (3.6, 4.4),
                   dpi: int | None = None) -> Figure:
    """Overlay vertical profiles.

    ``series`` items are ``{"x": [...], "y": [...], "label": str,
    "value": float|None}``.  Up to six series are direct-labelled at the end
    of the line; beyond that they are coloured by ``value`` (typically
    latitude) with a colourbar, since a legend of 40 entries is unreadable.
    """
    with _styled(dpi):
        fig, ax = plt.subplots(figsize=figsize)
        xs, ys, labels, colors = [], [], [], []
        many = len(series) > 6 and color_by is not None
        if many:
            vals = np.array([s.get("value") if s.get("value") is not None else np.nan
                             for s in series], dtype="float64")
            finite = vals[np.isfinite(vals)]
            vmin, vmax = (float(finite.min()), float(finite.max())) if finite.size \
                else (0.0, 1.0)
            if vmin == vmax:
                vmax = vmin + 1.0
            cmap = plt.get_cmap("viridis")
            norm = plt.Normalize(vmin, vmax)
            for s, v in zip(series, vals):
                c = cmap(norm(v)) if np.isfinite(v) else META_GREY
                ax.plot(s["x"], s["y"], color=c, alpha=0.75, linewidth=0.8)
            sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
            cb = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.05)
            cb.set_label(vocab.axis_title(color_by), fontsize=SIZES[1])
            cb.ax.tick_params(labelsize=SIZES[2])
        else:
            for i, s in enumerate(series):
                c = CATEGORICAL[i % len(CATEGORICAL)] if len(series) > 1 else FOCAL
                x = np.asarray(s["x"], dtype="float64")
                y = np.asarray(s["y"], dtype="float64")
                ax.plot(x, y, color=c, linewidth=1.6)
                unc = s.get("uncertainty")
                if unc is not None:
                    unc_a = np.asarray(unc, dtype="float64")
                    if np.isfinite(unc_a).any():
                        ax.fill_betweenx(y, x - unc_a, x + unc_a, alpha=0.22, color=c)
                xs.append(x)
                ys.append(y)
                labels.append(s.get("label", f"profile {i + 1}"))
                colors.append(c)
            if len(series) > 1:
                _series_key(ax, labels, colors)

        ax.set_xlabel(vocab.axis_title(x_var, x_units))
        ax.set_ylabel(vocab.axis_title(y_var, y_units))
        if logx:
            ax.set_xscale("log")
        if invert_y:
            ax.invert_yaxis()
        if title:
            ax.set_title(safe_mathtext(title), fontsize=SIZES[0])
        ax.margins(0.04)
        if caption:
            fig.text(0.0, -0.06, caption, fontsize=SIZES[1], color=META_GREY,
                     ha="left", va="top", wrap=True)
        fig.tight_layout()
    return fig


def composite_figure(comp: dict, show: str = "mean", spread: str = "std",
                     title: str = "", caption: str = "", logx: bool = False,
                     figsize: tuple[float, float] = (4.0, 4.6),
                     dpi: int | None = None) -> Figure:
    """Group-mean profiles with a shaded spread band.

    ``comp`` is :meth:`analysis.Composite.to_json` output.  ``spread`` is
    ``"std"`` (mean +/- 1 sigma) or ``"p10p90"`` (10th-90th percentile).
    """
    with _styled(dpi):
        fig, ax = plt.subplots(figsize=figsize)
        grid = np.array(comp["grid"], dtype="float64")
        xs, ys, labels, colors = [], [], [], []
        for i, (name, g) in enumerate(comp["groups"].items()):
            c = CATEGORICAL[i % len(CATEGORICAL)]
            mid = np.array([np.nan if v is None else v for v in g[show]],
                           dtype="float64")
            if spread == "p10p90":
                lo = np.array([np.nan if v is None else v for v in g["p10"]])
                hi = np.array([np.nan if v is None else v for v in g["p90"]])
            else:
                sd = np.array([np.nan if v is None else v for v in g["std"]])
                lo, hi = mid - sd, mid + sd
            ax.fill_betweenx(grid, lo, hi, color=c, alpha=0.22, linewidth=0)
            ax.plot(mid, grid, color=c, linewidth=2.0)
            xs.append(mid)
            ys.append(grid)
            labels.append(f"{name} (n={g['n']})")
            colors.append(c)
        _series_key(ax, labels, colors)
        ax.set_xlabel(comp.get("field_label") or comp["field"])
        ax.set_ylabel(comp.get("vertical_label") or comp["vertical"])
        if logx:
            ax.set_xscale("log")
        ax.set_title(safe_mathtext(title or f"{show.title()} profile by group"), fontsize=SIZES[0])
        band = "+/-1 sigma" if spread == "std" else "10th-90th percentile"
        mc = comp.get("min_count", 3)
        cap = caption or (f"Shading: {band}. {comp['n_profiles']} profiles "
                          f"interpolated to a common {grid[1] - grid[0]:.2g} km grid "
                          f"before averaging; levels with fewer than {mc} profiles "
                          f"are blank.")
        dropped = comp.get("dropped_groups") or {}
        if dropped:
            cap += (" Omitted for having fewer than "
                    f"{mc} profiles: "
                    + ", ".join(f"{k} (n={v})" for k, v in dropped.items()) + ".")
        fig.text(0.0, -0.05, cap, fontsize=SIZES[1], color=META_GREY, ha="left",
                 va="top", wrap=True)
        ax.margins(0.04)
        fig.tight_layout()
    return fig


def map_figure(points: Sequence[dict], color_by: str | None = None,
               title: str = "", caption: str = "", resolution: str = "110m",
               figsize: tuple[float, float] = (6.6, 3.6),
               dpi: int | None = None) -> Figure:
    """Occultation locations on an equirectangular map."""
    with _styled(dpi):
        fig, ax = plt.subplots(figsize=figsize)
        _draw_basemap(ax, resolution)
        lon = np.array([p.get("lon") for p in points], dtype="float64")
        lat = np.array([p.get("lat") for p in points], dtype="float64")
        if color_by:
            val = np.array([p.get(color_by) if p.get(color_by) is not None else np.nan
                            for p in points], dtype="float64")
            sc = ax.scatter(lon, lat, c=val, cmap="viridis", s=9, linewidths=0,
                            zorder=3)
            cb = fig.colorbar(sc, ax=ax, pad=0.015, fraction=0.025)
            cb.set_label(vocab.axis_title(color_by), fontsize=SIZES[1])
            cb.ax.tick_params(labelsize=SIZES[2])
        else:
            ax.scatter(lon, lat, s=9, color=FOCAL, linewidths=0, zorder=3)
        n = int(np.isfinite(lon).sum())
        ax.set_title(safe_mathtext(title or f"Occultation locations (n = {n})"), fontsize=SIZES[0])
        if caption:
            fig.text(0.0, -0.04, caption, fontsize=SIZES[1], color=META_GREY,
                     ha="left", va="top", wrap=True)
        fig.tight_layout()
    return fig


def coverage_figure(cov: dict, title: str = "", dpi: int | None = None) -> Figure:
    """Three-panel sampling summary: map density, latitude, local time."""
    with _styled(dpi):
        fig = plt.figure(figsize=(6.8, 5.2), layout="constrained")
        gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1.0], hspace=0.10,
                              wspace=0.10)
        ax0 = fig.add_subplot(gs[0, :])
        _draw_basemap(ax0)
        cells = cov.get("cells", [])
        if cells:
            lon = np.array([c["lon"] for c in cells])
            lat = np.array([c["lat"] for c in cells])
            n = np.array([c["n"] for c in cells], dtype="float64")
            b = cov.get("bin_deg", 5.0)
            sc = ax0.scatter(lon, lat, c=n, cmap="magma_r", s=(b * 2.2) ** 2 / 6,
                             marker="s", linewidths=0, zorder=3)
            cb = fig.colorbar(sc, ax=ax0, pad=0.015, fraction=0.025)
            cb.set_label(f"profiles per {b:g}x{b:g} deg cell", fontsize=SIZES[1])
            cb.ax.tick_params(labelsize=SIZES[2])
        ax0.set_title(safe_mathtext(title or "Where the profiles are"), fontsize=SIZES[0])

        ax1 = fig.add_subplot(gs[1, 0])
        lh = cov.get("lat_hist", [])
        if lh:
            ax1.barh([r["lat"] for r in lh], [r["n"] for r in lh], height=4.4,
                     color=FOCAL, linewidth=0)
        ax1.set_xlabel("Profiles")
        ax1.set_ylabel("Latitude [deg N]")
        ax1.set_title("Latitude sampling", fontsize=SIZES[0])

        ax2 = fig.add_subplot(gs[1, 1])
        th = cov.get("local_time_hist", [])
        if th:
            ax2.bar([r["hour"] for r in th], [r["n"] for r in th], width=0.9,
                    color=FOCAL, linewidth=0)
        ax2.set_xlabel("Local solar time [h]")
        ax2.set_ylabel("Profiles")
        ax2.set_xlim(0, 24)
        ax2.set_xticks(range(0, 25, 6))
        ax2.set_title("Diurnal sampling", fontsize=SIZES[0])
    return fig


def scatter_figure(x: Sequence[float], y: Sequence[float], x_var: str, y_var: str,
                   color: Sequence[float] | None = None, color_var: str = "",
                   title: str = "", caption: str = "", logy: bool = False,
                   figsize: tuple[float, float] = (4.2, 3.4),
                   dpi: int | None = None) -> Figure:
    """Generic relationship plot (e.g. tropopause height vs latitude)."""
    with _styled(dpi):
        fig, ax = plt.subplots(figsize=figsize)
        xa = np.asarray(x, dtype="float64")
        ya = np.asarray(y, dtype="float64")
        if color is not None:
            sc = ax.scatter(xa, ya, c=np.asarray(color, dtype="float64"),
                            cmap="viridis", s=14, linewidths=0)
            cb = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.05)
            cb.set_label(vocab.axis_title(color_var), fontsize=SIZES[1])
            cb.ax.tick_params(labelsize=SIZES[2])
        else:
            ax.scatter(xa, ya, s=14, color=FOCAL, linewidths=0)
        ax.set_xlabel(vocab.axis_title(x_var))
        ax.set_ylabel(vocab.axis_title(y_var))
        if logy:
            ax.set_yscale("log")
        if title:
            ax.set_title(safe_mathtext(title), fontsize=SIZES[0])
        ax.margins(0.05)
        if caption:
            fig.text(0.0, -0.06, caption, fontsize=SIZES[1], color=META_GREY,
                     ha="left", va="top", wrap=True)
        fig.tight_layout()
    return fig


def panels_figure(panels: Sequence[dict], suptitle: str = "", caption: str = "",
                  dpi: int | None = None,
                  panel_size: tuple[float, float] = (2.5, 3.9)) -> Figure:
    """A row of profile panels sharing one y-axis.

    Each panel dict is ``{"x": [...], "y": [...], "x_var": str, "units": str,
    "logx": bool}``.  Used for the "one profile, several quantities" view:
    temperature, humidity and refractivity side by side.
    """
    n = max(1, len(panels))
    with _styled(dpi):
        fig, axes = plt.subplots(1, n, sharey=True,
                                 figsize=(panel_size[0] * n, panel_size[1]))
        axes = np.atleast_1d(axes)
        for i, (ax, p) in enumerate(zip(axes, panels)):
            ax.plot(np.asarray(p["x"], dtype="float64"),
                    np.asarray(p["y"], dtype="float64"), color=FOCAL)
            ax.set_xlabel(vocab.axis_title(p["x_var"], p.get("units", "")))
            if p.get("logx"):
                ax.set_xscale("log")
                ax.xaxis.set_major_locator(
                    matplotlib.ticker.LogLocator(numticks=4))
            else:
                _thin_ticks(ax, "x", nbins=4)
            ax.set_title(f"({chr(97 + i)})", fontsize=SIZES[0], fontweight="bold",
                         loc="left")
            ax.margins(0.05)
            for ref in p.get("reference_lines", []):
                ax.axhline(ref["y"], color=ACCENT, linewidth=0.8, linestyle="--")
                ax.annotate(ref["label"], (0.02, ref["y"]),
                            xycoords=("axes fraction", "data"),
                            fontsize=SIZES[1], color=ACCENT, va="bottom")
        axes[0].set_ylabel(vocab.axis_title(panels[0].get("y_var", "MSL_alt")))
        if suptitle:
            fig.suptitle(safe_mathtext(suptitle), fontsize=SIZES[0], x=0.0, ha="left")
        if caption:
            fig.text(0.0, -0.04, caption, fontsize=SIZES[1], color=META_GREY,
                     ha="left", va="top", wrap=True)
        fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

MIME = {"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml",
        "eps": "application/postscript", "jpg": "image/jpeg"}


def render(fig: Figure, fmt: str = "png", dpi: int | None = None) -> bytes:
    fmt = fmt.lower()
    if fmt not in MIME:
        raise ValueError(f"Unsupported format {fmt!r}; choose from {sorted(MIME)}")
    buf = io.BytesIO()
    # The savefig.* and pdf/ps font settings are read when the file is
    # written, so the publication style must be active here too.  Saving
    # outside it clipped every caption (placed below the axes, recovered only
    # by the tight bounding box) and embedded Type 3 fonts in PDF/EPS.
    with _styled(dpi):
        fig.savefig(buf, format=fmt, dpi=dpi or SETTINGS.plot_dpi)
    plt.close(fig)
    return buf.getvalue()


def check_layout(fig: Figure) -> list[str]:
    """Report text that overlaps other text or spills outside the canvas.

    Used by the test suite as a regression guard on the exported figures.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    items = [(t, t.get_window_extent(r)) for t in fig.findobj(matplotlib.text.Text)
             if t.get_text().strip() and t.get_visible()]
    problems = []
    for i, (t1, b1) in enumerate(items):
        for t2, b2 in items[i + 1:]:
            if b1.overlaps(b2):
                problems.append(f"text overlap: {t1.get_text()!r} / {t2.get_text()!r}")
    return problems
