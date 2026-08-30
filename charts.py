import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def spending_chart(totals: dict[str, float], out_path, title: str) -> None:
    items = sorted((kv for kv in totals.items() if kv[1] > 0), key=lambda kv: kv[1], reverse=True)
    if not items:
        raise ValueError("nothing to plot")
    if len(items) > 8:
        head = items[:7]
        others_value = sum(v for _, v in items[7:])
        items = head + [("Others", others_value)]

    labels = [k for k, _ in items]
    values = [v for _, v in items]
    colors = plt.get_cmap("tab20")(range(len(items)))

    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        pctdistance=0.79,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        textprops={"fontsize": 11},
    )
    ax.text(0, 0.08, title, ha="center", va="center", fontsize=15, fontweight="bold")
    ax.set(aspect="equal")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
