import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import os

# =====================================================
# COLOR PALETTE
# =====================================================
C = {
    "DARK_NAVY":    "#001F6B",
    "MEDIUM_NAVY":  "#002A7F",
    "MEDIUM_BLUE":  "#4A5FA8",
    "LIGHT_BLUE":   "#5D6CB3",
    "LAVENDER":     "#B8B7D9",
    "PERIWINKLE":   "#C6C5E5",
    "LIGHT_GRAY":   "#F2F2F2",
    "MEDIUM_GRAY":  "#BDBDBD",
    "DARK_GRAY":    "#808080",
    "WHITE":        "#FFFFFF",
    "PINK":         "#F36B86",
    "TEXT_DARK":    "#1D1C1C",
    "GRID":         "#E0E0E0",
}

# =====================================================
# DATA
# =====================================================
full_project_data = [
    {"phase": "PHASE 3A: DISCOVERY & DESIGN",    "task": "",                                    "start": "2026-06-01", "end": "2026-06-21", "type": "phase"},
    {"phase": "",                                 "task": "Requirement Workshops",               "start": "2026-06-01", "end": "2026-06-14", "type": "task"},
    {"phase": "",                                 "task": "Data Source Assessment",              "start": "2026-06-01", "end": "2026-06-21", "type": "task"},
    {"phase": "",                                 "task": "L2A & CAC Data Model Design",         "start": "2026-06-08", "end": "2026-06-21", "type": "task"},
    {"phase": "",                                 "task": "Power BI Mock-up Development",        "start": "2026-06-08", "end": "2026-06-21", "type": "task"},
    {"phase": "",                                 "task": "Data Gap Assessment",                 "start": "2026-06-15", "end": "2026-06-21", "type": "task"},
    {"phase": "",                                 "task": "QuickBooks Integration Design",       "start": "2026-06-15", "end": "2026-06-21", "type": "task"},
    {"phase": "PHASE 3B: BUILD & IMPLEMENTATION","task": "",                                    "start": "2026-06-22", "end": "2026-09-13", "type": "phase"},
    {"phase": "",                                 "task": "Finalize Data Model",                 "start": "2026-06-22", "end": "2026-07-05", "type": "task"},
    {"phase": "",                                 "task": "Define Transformation Logic",         "start": "2026-06-22", "end": "2026-07-12", "type": "task"},
    {"phase": "",                                 "task": "Fabric Batch Workflow Design",        "start": "2026-06-29", "end": "2026-07-19", "type": "task"},
    {"phase": "",                                 "task": "Integration Validation (Salesforce)", "start": "2026-06-29", "end": "2026-07-26", "type": "task"},
    {"phase": "",                                 "task": "Integration Validation (QuickBooks)", "start": "2026-06-29", "end": "2026-07-26", "type": "task"},
    {"phase": "",                                 "task": "Dashboard Specification Refinement",  "start": "2026-07-06", "end": "2026-08-02", "type": "task"},
    {"phase": "",                                 "task": "Implementation Plan Development",     "start": "2026-07-06", "end": "2026-08-16", "type": "task"},
    {"phase": "",                                 "task": "Governance & Scalability Recommendations", "start": "2026-08-03", "end": "2026-09-13", "type": "task"},
]

discovery_data = [
    {"phase": "PHASE 3A: DISCOVERY & DESIGN", "task": "",                              "start": "2026-06-01", "end": "2026-06-21", "type": "phase"},
    {"phase": "",                              "task": "Requirement Workshops",         "start": "2026-06-01", "end": "2026-06-14", "type": "task"},
    {"phase": "",                              "task": "Data Source Assessment",        "start": "2026-06-01", "end": "2026-06-21", "type": "task"},
    {"phase": "",                              "task": "L2A & CAC Data Model Design",   "start": "2026-06-08", "end": "2026-06-21", "type": "task"},
    {"phase": "",                              "task": "Power BI Mock-up Development",  "start": "2026-06-08", "end": "2026-06-21", "type": "task"},
    {"phase": "",                              "task": "Data Gap Assessment",           "start": "2026-06-15", "end": "2026-06-21", "type": "task"},
    {"phase": "",                              "task": "QuickBooks Integration Design", "start": "2026-06-15", "end": "2026-06-21", "type": "task"},
]

# =====================================================
# GENERATE BOTH CHARTS
# =====================================================

def generate_timeline(project_data, title_text, output_path, milestones):

    df = pd.DataFrame(project_data)
    df["start"] = pd.to_datetime(df["start"])
    df["end"]   = pd.to_datetime(df["end"])

    project_start = df["start"].min()
    df["start_day"] = (df["start"] - project_start).dt.days
    df["end_day"]   = (df["end"]   - project_start).dt.days + 1   # inclusive

    total_days = df["end_day"].max()
    n_weeks    = int(np.ceil(total_days / 7))

    n_rows = len(df)

    # ── layout constants ──────────────────────────────────────────
    ROW_H        = 0.70   # height of each task row (data units)
    TASK_COL_W   = 5.5    # width (inches) of left task column
    WEEK_W       = 1.30   # width (inches) per week column
    TOP_HEADER   = 1.20   # inches for title above chart
    HEADER_ROWS  = 2      # rows used for week-header band (in data units each = ROW_H)

    chart_w  = TASK_COL_W + n_weeks * WEEK_W
    chart_h  = TOP_HEADER + (n_rows + HEADER_ROWS) * ROW_H * 0.72 + 0.6   # 0.6 for legend

    fig, ax = plt.subplots(figsize=(chart_w, chart_h))
    fig.patch.set_facecolor(C["WHITE"])
    ax.set_facecolor(C["WHITE"])
    ax.axis("off")

    # ── coordinate system ─────────────────────────────────────────
    # We work in a unified axis where:
    #   x: 0 = left edge of task column, TASK_COL_W = start of timeline, TASK_COL_W+n_weeks*WEEK_W = right edge
    #   y: top-down (0 = topmost header band, increasing downward)

    # Convert to axis fraction helpers
    total_w = TASK_COL_W + n_weeks * WEEK_W   # total width in inches
    total_h = chart_h                           # total height in inches

    # Use axis units = inches for simplicity via transform tricks
    # We'll set ax limits in "inch-like" units
    ax.set_xlim(0, total_w)
    ax.set_ylim(total_h, 0)   # y=0 at top

    # ── y positions ───────────────────────────────────────────────
    TITLE_Y      = 0.15            # center of title text
    HEADER_Y_TOP = TOP_HEADER      # top of "TIMELINES" band
    SUBHDR_H     = 0.42            # height of each sub-header row
    BAND1_H      = 0.42            # "TIMELINES" label row height
    ROW_TOP_0    = HEADER_Y_TOP + BAND1_H + SUBHDR_H   # top of first data row

    def row_center(i):
        return ROW_TOP_0 + i * ROW_H + ROW_H / 2

    # x helpers
    TL_X0 = TASK_COL_W            # x where timeline starts

    def week_center(w):
        return TL_X0 + w * WEEK_W + WEEK_W / 2

    def day_to_x(d):
        return TL_X0 + d / 7 * WEEK_W

    # ── TITLE ─────────────────────────────────────────────────────
    ax.text(
        total_w / 2, TITLE_Y,
        title_text,
        ha="center", va="center",
        fontsize=15, fontweight="bold",
        color=C["DARK_NAVY"], fontfamily="Arial",
        transform=ax.transData
    )

    # ── SEPARATOR LINE between task col and timeline ──────────────
    ax.plot([TL_X0, TL_X0], [TOP_HEADER, ROW_TOP_0 + n_rows * ROW_H],
            color=C["MEDIUM_GRAY"], linewidth=1.0, zorder=5)

    # ── TIMELINE HEADER BAND ──────────────────────────────────────
    # "TIMELINES" super-header
    ax.add_patch(mpatches.FancyBboxPatch(
        (TL_X0, HEADER_Y_TOP), n_weeks * WEEK_W, BAND1_H,
        boxstyle="square,pad=0", linewidth=0,
        facecolor=C["DARK_NAVY"], zorder=4
    ))
    ax.text(
        TL_X0 + n_weeks * WEEK_W / 2,
        HEADER_Y_TOP + BAND1_H / 2,
        "TIMELINES",
        ha="center", va="center",
        fontsize=10, fontweight="bold",
        color=C["WHITE"], fontfamily="Arial", zorder=5
    )

    # Week sub-headers
    for w in range(n_weeks):
        x0 = TL_X0 + w * WEEK_W
        y0 = HEADER_Y_TOP + BAND1_H
        ax.add_patch(plt.Rectangle(
            (x0, y0), WEEK_W, SUBHDR_H,
            facecolor=C["MEDIUM_NAVY"],
            edgecolor=C["WHITE"], linewidth=0.6,
            zorder=4
        ))
        ax.text(
            x0 + WEEK_W / 2, y0 + SUBHDR_H / 2,
            f"Week {w}",
            ha="center", va="center",
            fontsize=8, fontweight="bold",
            color=C["WHITE"], fontfamily="Arial", zorder=5
        )

    # ── TASK COLUMN HEADER ────────────────────────────────────────
    ax.add_patch(plt.Rectangle(
        (0, HEADER_Y_TOP), TASK_COL_W, BAND1_H,
        facecolor=C["DARK_NAVY"], edgecolor="none", zorder=4
    ))
    ax.text(
        TASK_COL_W / 2, HEADER_Y_TOP + BAND1_H / 2,
        "DELIVERABLES / ACTIVITIES",
        ha="center", va="center",
        fontsize=10, fontweight="bold",
        color=C["WHITE"], fontfamily="Arial", zorder=5
    )
    ax.add_patch(plt.Rectangle(
        (0, HEADER_Y_TOP + BAND1_H), TASK_COL_W, SUBHDR_H,
        facecolor=C["MEDIUM_NAVY"], edgecolor="none", zorder=4
    ))

    # ── GRID LINES ────────────────────────────────────────────────
    grid_top    = ROW_TOP_0
    grid_bottom = ROW_TOP_0 + n_rows * ROW_H

    # vertical week separators
    for w in range(n_weeks + 1):
        x = TL_X0 + w * WEEK_W
        ax.plot([x, x], [grid_top, grid_bottom],
                color=C["GRID"], linewidth=0.5, zorder=1)

    # horizontal row separators
    for i in range(n_rows + 1):
        y = ROW_TOP_0 + i * ROW_H
        ax.plot([0, total_w], [y, y],
                color=C["GRID"], linewidth=0.4, zorder=1)

    # alternating row fill
    for i, (_, row) in enumerate(df.iterrows()):
        y0 = ROW_TOP_0 + i * ROW_H
        if row["type"] == "phase":
            ax.add_patch(plt.Rectangle(
                (0, y0), total_w, ROW_H,
                facecolor=C["DARK_NAVY"], alpha=0.06,
                edgecolor="none", zorder=0
            ))
        else:
            if i % 2 == 0:
                ax.add_patch(plt.Rectangle(
                    (0, y0), total_w, ROW_H,
                    facecolor=C["LIGHT_GRAY"], alpha=0.5,
                    edgecolor="none", zorder=0
                ))

    # ── TASK LABELS ───────────────────────────────────────────────
    for i, (_, row) in enumerate(df.iterrows()):
        yc = row_center(i)
        if row["type"] == "phase":
            ax.text(
                0.18, yc,
                row["phase"],
                ha="left", va="center",
                fontsize=8.5, fontweight="bold",
                color=C["DARK_NAVY"], fontfamily="Arial", zorder=6
            )
        else:
            ax.text(
                0.55, yc,
                row["task"],
                ha="left", va="center",
                fontsize=7.5, color=C["TEXT_DARK"],
                fontfamily="Arial", zorder=6
            )

    # ── GANTT BARS ────────────────────────────────────────────────
    BAR_PHASE_H = ROW_H * 0.52
    BAR_TASK_H  = ROW_H * 0.42

    for i, (_, row) in enumerate(df.iterrows()):
        yc    = row_center(i)
        x_s   = day_to_x(row["start_day"])
        x_e   = day_to_x(row["end_day"])
        bar_w = max(x_e - x_s, 0.05)

        if row["type"] == "phase":
            bh = BAR_PHASE_H
            fc = C["DARK_NAVY"]
            ec = C["MEDIUM_BLUE"]
            lw = 0.8
        else:
            bh = BAR_TASK_H
            fc = C["LAVENDER"]
            ec = C["PERIWINKLE"]
            lw = 0.7

        ax.add_patch(plt.Rectangle(
            (x_s, yc - bh / 2), bar_w, bh,
            facecolor=fc, edgecolor=ec,
            linewidth=lw, zorder=3
        ))

        # left accent stripe for tasks
        if row["type"] == "task":
            ax.add_patch(plt.Rectangle(
                (x_s, yc - bh / 2), min(0.07, bar_w), bh,
                facecolor=C["PINK"], edgecolor="none",
                alpha=0.75, zorder=4
            ))

    # ── MILESTONE DIAMONDS ────────────────────────────────────────
    for m in milestones:
        mx    = day_to_x(m["day"])
        my    = HEADER_Y_TOP + BAND1_H / 2   # sit on header band
        ds    = 0.17   # diamond half-size
        diamond = plt.Polygon(
            [(mx, my - ds), (mx + ds, my), (mx, my + ds), (mx - ds, my)],
            facecolor=C["PINK"], edgecolor=C["DARK_NAVY"],
            linewidth=0.8, zorder=7
        )
        ax.add_patch(diamond)

        # dashed drop line
        ax.plot([mx, mx], [HEADER_Y_TOP + BAND1_H, ROW_TOP_0 + n_rows * ROW_H],
                color=C["PINK"], linewidth=0.6, linestyle="--", alpha=0.45, zorder=2)

        # label above
        ax.text(
            mx, HEADER_Y_TOP + BAND1_H / 2 - ds - 0.04,
            m["label"],
            ha="center", va="bottom",
            fontsize=6.5, fontweight="bold",
            color=C["DARK_NAVY"], fontfamily="Arial", zorder=8
        )

    # ── LEGEND ────────────────────────────────────────────────────
    legend_y = ROW_TOP_0 + n_rows * ROW_H + 0.22
    legend_items = [
        (C["DARK_NAVY"], 0.9,  "Phase"),
        (C["LAVENDER"],  0.9,  "Task"),
        (C["PINK"],      1.0,  "Milestone"),
    ]
    box_w, box_h = 0.28, 0.18
    gap = 1.6
    start_x = total_w / 2 - gap
    for k, (fc, alpha, label) in enumerate(legend_items):
        lx = start_x + k * gap
        ax.add_patch(plt.Rectangle(
            (lx, legend_y), box_w, box_h,
            facecolor=fc, alpha=alpha, edgecolor=C["MEDIUM_GRAY"],
            linewidth=0.5, zorder=6
        ))
        ax.text(
            lx + box_w + 0.12, legend_y + box_h / 2,
            label,
            ha="left", va="center",
            fontsize=8, color=C["TEXT_DARK"],
            fontfamily="Arial", zorder=6
        )

    # ── OUTER BORDER ──────────────────────────────────────────────
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.add_patch(plt.Rectangle(
        (0, TOP_HEADER), total_w, ROW_TOP_0 + n_rows * ROW_H - TOP_HEADER,
        facecolor="none", edgecolor=C["MEDIUM_GRAY"],
        linewidth=1.0, zorder=10
    ))

    plt.tight_layout(pad=0.4)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight",
                facecolor="white", pad_inches=0.25)
    plt.close()
    print(f"  Saved → {output_path}")


# ── run both ──────────────────────────────────────────────────────
print("Generating timelines...")

generate_timeline(
    discovery_data,
    "PURE FINANCIAL ADVISORS LLC — Discovery & Design Phase",
    "./discovery_phase_timeline.png",
    milestones=[
        {"day": 20, "label": "Discovery Complete"},
    ]
)

generate_timeline(
    full_project_data,
    "PURE FINANCIAL ADVISORS LLC — Project Timeline Roadmap",
    "./full_project_timeline.png",
    milestones=[
        {"day": 20,  "label": "Discovery Complete"},
        {"day": 48,  "label": "Design Review"},
        {"day": 83,  "label": "Implementation Ready"},
        {"day": 104, "label": "Go-Live"},
    ]
)

print("Done!")