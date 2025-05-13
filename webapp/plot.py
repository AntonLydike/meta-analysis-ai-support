import matplotlib.pyplot as plt
import io
import numpy as np

def render_heatmap(data, models, thresholds, title, cmap='Blues'):
    fig, ax = plt.subplots(figsize=(len(models), len(thresholds)))
    data_array = np.array(data)

    ax.imshow(data_array, cmap=cmap, vmin=0, vmax=1)

    ax.set_yticks(np.arange(len(thresholds)))
    ax.set_xticks(np.arange(len(models)))
    ax.set_yticklabels([f">{t}" for t in thresholds])
    ax.set_xticklabels(models)

    for j in range(len(models)):
        for i in range(len(thresholds)):
            val = data_array[i, j]
            text_color = "white" if val > 0.7 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", color=text_color)

    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    ax.set_title(title)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="svg")
    plt.close(fig)
    return buf.getvalue().decode("utf-8")
