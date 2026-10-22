# COSMIC-2 Explorer: Branding and Media Kit

This directory contains master high-resolution graphical assets for COSMIC-2 Explorer, intended for scientific posters, conference slide decks, journal publications, and web presentations.

---

## 1. Asset Overview

| Filename | Resolution | Format | Recommended Usage |
|---|---|---|---|
| `cosmic2_logo_full.png` | 1024 x 1024 | PNG (RGBA) | Master constellation emblem with typography |
| `cosmic2_icon_full.png` | 1024 x 1024 | PNG (RGBA) | Clean minimal vector icon |
| `cosmic2_emblem_circle.png` | 1024 x 1024 | PNG (Alpha Mask) | Circular cutout for badge emblems |
| `cosmic2_emblem_square.png` | 1024 x 1024 | PNG (Alpha Mask) | App icon with rounded corners |
| `cosmic2_logo_master.jpg` | 1024 x 1024 | JPEG | High-contrast master print graphic |
| `cosmic2_icon_master.jpg` | 1024 x 1024 | JPEG | Single-satellite minimal symbol |
| `cosmic2.ico` | 16 to 256 px | Windows ICO | Multi-resolution desktop and app icon |

---

## 2. Official Color Palette

* **Deep Space Navy**: `#0B132B` / `rgb(11, 19, 43)`
* **Radio Occultation Cyan**: `#00F0FF` / `rgb(0, 240, 255)`
* **Ionospheric Teal**: `#1C2541` / `rgb(28, 37, 65)`
* **Orbital Gold / Solar Yellow**: `#FFD166` / `rgb(255, 209, 102)`
* **Atmospheric White**: `#F8F9FA` / `rgb(248, 249, 250)`

---

## 3. LaTeX Usage for Academic Papers and Posters

### Including in Beamer Presentations
```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=0.25\textwidth]{images/cosmic2_logo_full.png}
  \caption{COSMIC-2 Explorer Analysis Environment}
\end{figure}
```

### Conference Poster Header (e.g. AGU, EGU, COSPAR, URSI)
```latex
% In your poster preamble:
\usepackage{graphicx}

% In the title banner / header:
\begin{minipage}{0.12\textwidth}
  \includegraphics[width=\linewidth]{images/cosmic2_emblem_circle.png}
\end{minipage}
\hfill
\begin{minipage}{0.85\textwidth}
  \textbf{\LARGE High-Resolution GNSS Radio Occultation Profiling with COSMIC-2 Explorer}\\
  \large Keshav Aggarwal\\
  \small Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO, Thiruvananthapuram, India
\end{minipage}
```

---

## 4. Academic Attribution and Citation

When utilizing these logos or scientific software outputs in publications or posters, please credit:

* **Lead Researcher and Author**: Keshav Aggarwal
* **Affiliation**: Student visitor at the Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India (Former PMRF Scholar at DAASE, IIT Indore).

```bibtex
@software{Aggarwal_COSMIC2_Explorer_2026,
  author = {Aggarwal, Keshav},
  title = {{COSMIC-2 Explorer: Atmospheric and Ionospheric GNSS Radio Occultation Scientific Analysis and Visualization Platform}},
  year = {2026},
  institution = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  address = {Thiruvananthapuram, Kerala, India},
  url = {https://github.com/jovian-explorer/COSMIC2-Explorer}
}
```
