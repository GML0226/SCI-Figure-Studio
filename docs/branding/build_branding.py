"""Regenerate SCI Figure Studio vector branding and PNG previews."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle

OUT = Path(__file__).resolve().parent
NAVY, BLUE, TEAL = "#142139", "#7185FF", "#54D9CF"
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "path"})


def mark(ax):
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.set_aspect("equal"); ax.axis("off")
    ax.add_patch(FancyBboxPatch((.02, .02), .96, .96,
                 boxstyle="round,pad=0,rounding_size=.21", color=NAVY))
    ax.plot([.22, .22, .80], [.80, .22, .22], color="#647493", lw=2)
    for x, height, color in [(.30, .25, "#7F94FF"), (.47, .39, "#91AAF7"), (.64, .55, TEAL)]:
        ax.add_patch(FancyBboxPatch((x, .23), .115, height,
                     boxstyle="round,pad=0,rounding_size=.025", color=color, linewidth=0))
    for x, y in [(.61, .81), (.82, .81), (.82, .57)]:
        ax.add_patch(Rectangle((x-.025, y-.025), .05, .05,
                     facecolor=NAVY, edgecolor="#E7EEFF", lw=1.2))
    ax.plot([.64, .79, .79], [.81, .81, .60], color="#E7EEFF", lw=1, zorder=0)


def save(fig, name, transparent=False):
    fig.savefig(OUT/f"{name}.svg", transparent=transparent)
    fig.savefig(OUT/f"{name}.png", dpi=200, transparent=transparent)
    plt.close(fig)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(2, 2)); mark(fig.add_axes([0, 0, 1, 1]))
    save(fig, "mark", True)

    fig = plt.figure(figsize=(7.6, 1.6), facecolor="white")
    mark(fig.add_axes([.015, .07, .19, .86]))
    fig.text(.25, .55, "SCI", fontsize=29, fontweight="bold", color="#4963DD", va="center")
    fig.text(.395, .55, "Figure Studio", fontsize=29, color=NAVY, va="center")
    fig.text(.253, .25, "PRECISION EDITING FOR SCIENTIFIC FIGURES", fontsize=8.5,
             color="#6B7890")
    save(fig, "logo")

    fig = plt.figure(figsize=(12, 3.2), facecolor=NAVY)
    bg = fig.add_axes([0, 0, 1, 1]); bg.set(xlim=(0, 12), ylim=(0, 3.2)); bg.axis("off")
    bg.add_patch(Circle((11.9, 3.7), 2.3, facecolor="#1A2A47", edgecolor="none"))
    bg.add_patch(Circle((12.1, 3.7), 1.8, facecolor="none", edgecolor="#304266", lw=.9))
    bg.add_patch(Circle((11.7, -.9), 1.7, facecolor="none", edgecolor="#304266", lw=.9))
    bg.plot([.0, 12], [.055, .055], color="#54D9CF", lw=2)
    mark(fig.add_axes([.045, .29, .125, .47]))
    fig.text(.215, .80, "RESEARCH TOOLS  /  v1.0", color="#A6B7D8", fontsize=10)
    fig.text(.21, .56, "SCI", color=TEAL, fontsize=40, fontweight="bold")
    fig.text(.323, .56, "Figure Studio", color="#F7F9FF", fontsize=40)
    fig.text(.215, .39, "Precision editing for scientific figures.", color="#C6D2E9", fontsize=14)
    fig.text(.215, .18, "IMPORT     /     EDIT     /     EXPORT", color="#A7B8D7", fontsize=10)
    for x, y, c in [(10.35, 1.48, BLUE), (10.96, 1.78, TEAL), (11.45, 1.43, "#C8D4EE")]:
        bg.add_patch(Circle((x, y), .055, facecolor=c, edgecolor="none"))
    bg.plot([10.35, 10.96, 11.45], [1.48, 1.78, 1.43], color="#7086AD", lw=1.3)
    save(fig, "hero")

    fig = plt.figure(figsize=(12, 1.55), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 12), ylim=(0, 1.55)); ax.axis("off")
    for i, (title, detail) in enumerate([
        ("IMPORT", "Python  /  Tables  /  Projects"),
        ("EDIT", "Text  /  Legend  /  Layout"),
        ("EXPORT", "SVG  /  PDF  /  PNG  /  TIFF")]):
        x = i*4+.06
        ax.add_patch(FancyBboxPatch((x, .08), 3.86, 1.38,
            boxstyle="round,pad=0,rounding_size=.13", facecolor="#F5F7FC", edgecolor="#E3E8F2", lw=.8))
        ax.add_patch(Circle((x+.43, .99), .19, facecolor=NAVY, edgecolor="none"))
        ax.text(x+.43, .99, str(i+1), ha="center", va="center", color="white", fontsize=11)
        ax.text(x+.78, .99, title, color=NAVY, fontsize=14, fontweight="bold", va="center")
        ax.text(x+.26, .43, detail, color="#60718D", fontsize=11)
    save(fig, "workflow")

    badges = [
        ("version", 91, "v1.0", "#4963DD"),
        ("windows", 189, "Windows 10/11 · x64", "#425576"),
        ("portable", 176, "Portable · ~42 MiB", "#087F78"),
    ]
    for name, width, label, color in badges:
        (OUT/f"badge-{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="28" viewBox="0 0 {width} 28" role="img" aria-label="{label}">'
            f'<rect width="{width}" height="28" rx="7" fill="{color}"/>'
            f'<circle cx="14" cy="14" r="3" fill="#FFF" opacity=".8"/>'
            f'<text x="{width/2+6}" y="18.5" text-anchor="middle" fill="#FFF" font-family="Arial,sans-serif" font-size="12">{label}</text></svg>',
            encoding="utf-8")


    (OUT/"button-download.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="238" height="42" viewBox="0 0 238 42" role="img" aria-label="Download for Windows">'
        '<rect width="238" height="42" rx="9" fill="#4963DD"/>'
        '<path d="M24 11v12m-5-5 5 5 5-5M16 27v4h16v-4" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<text x="46" y="26" fill="white" font-family="Arial,sans-serif" font-size="14" font-weight="bold">Download for Windows</text></svg>',
        encoding="utf-8")


if __name__ == "__main__":
    build()
