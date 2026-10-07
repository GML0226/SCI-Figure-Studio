"""Import this source with the editor; all labels and artists remain editable."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42


def build_figure():
    fig, ax = plt.subplots(figsize=(89 / 25.4, 65 / 25.4))
    x = np.arange(3)
    ax.bar(x - .18, [54, 67, 76], .36, label="Baseline", color="#96C3F5", edgecolor="#303030")
    ax.bar(x + .18, [69, 78, 83], .36, label="Proposed", color="#DE3F23", edgecolor="#303030", hatch="xx")
    ax.set_xticks(x, ["Data A", "Data B", "Data C"])
    ax.set_ylabel("Accuracy (%)", fontsize=8)
    ax.set_title("Editable scientific figure", fontsize=9)
    ax.legend(title="Methods", fontsize=7, title_fontsize=8)
    fig.subplots_adjust(left=.18, right=.97, bottom=.18, top=.86)
    return fig


if __name__ == "__main__":
    figure = build_figure()
    plt.show()
