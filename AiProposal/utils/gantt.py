import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import plotly.graph_objects as go
import base64
from io import BytesIO

# ==========================================
# Main function to create hierarchical Gantt chart
# ==========================================
def create_hierarchical_gantt(data, return_base64=True):
    """
    Create a hierarchical Gantt chart from nested phase/task data.
    
    Parameters:
    -----------
    data : list
        Nested list of phase dictionaries, each containing tasks
    return_base64 : bool
        If True, returns base64 encoded string of the PNG image
    
    Returns:
    --------
    str or plotly.graph_objects.Figure
        If return_base64 is True, returns base64 encoded string
        Otherwise returns the figure object
    """
    
    # ==========================================
    # Function to get week number from day number
    # ==========================================
    def get_week_number(day_num):
        # Week number starting from 0 (Day 1-7 = Week 0)
        return (day_num - 1) // 7

    # ==========================================
    # Flatten nested data for DataFrame with week numbers
    # ==========================================
    def flatten_data(nested_data):
        flattened = []
        
        for phase in nested_data:
            # Add the phase itself
            start_week = get_week_number(phase["Start_Day"])
            finish_week = get_week_number(phase["Finish_Day"])
            
            phase_entry = {
                "Name": phase["Name"],
                "DisplayName": f"<b>{phase['Name']}</b>",  # Bold for phases
                "Start_Day": phase["Start_Day"],
                "Finish_Day": phase["Finish_Day"],
                "Start_Week": start_week,
                "Finish_Week": finish_week,
                "Type": phase["Type"],
                "Progress": phase["Progress"],
                "isMain": phase.get("isMain", False),
                "Indent": 0,
                "Duration": finish_week - start_week + 1,
                "SortOrder": 0  # Phases first
            }
            flattened.append(phase_entry)
            
            # Add all tasks under this phase
            for task in phase.get("tasks", []):
                start_week = get_week_number(task["Start_Day"])
                finish_week = get_week_number(task["Finish_Day"])
                
                task_entry = {
                    "Name": f"    {task['Name']}",  # Indentation with spaces
                    "DisplayName": f"    {task['Name']}",  # No bold for tasks
                    "Start_Day": task["Start_Day"],
                    "Finish_Day": task["Finish_Day"],
                    "Start_Week": start_week,
                    "Finish_Week": finish_week,
                    "Type": task["Type"],
                    "Progress": task["Progress"],
                    "isMain": False,
                    "Indent": 1,
                    "Duration": finish_week - start_week + 1,
                    "SortOrder": 1  # Tasks after phases
                }
                flattened.append(task_entry)
        
        return flattened

    # Create flattened DataFrame
    flattened_data = flatten_data(data)
    df = pd.DataFrame(flattened_data)

    # ==========================================
    # Preserve exact hierarchical order (top to bottom)
    # ==========================================
    hierarchy_order = []
    for phase in data:
        hierarchy_order.append(f"<b>{phase['Name']}</b>")
        for task in phase.get("tasks", []):
            hierarchy_order.append(f"    {task['Name']}")

    # DO NOT reverse - keep as is for top-to-bottom display
    category_order = hierarchy_order

    # ==========================================
    # JMAN Colors
    # ==========================================
    color_map = {
        "Phase": "#001F6B",  # Dark Navy
        "Task": "#4A5FA8",   # Medium Blue
    }

    # ==========================================
    # Create Gantt chart using plotly.graph_objects
    # ==========================================
    # Create figure
    fig = go.Figure()

    # Add traces for each type (Phases first, then Tasks)
    for task_type in ['Phase', 'Task']:
        type_data = df[df['Type'] == task_type]
        
        # Sort by the original order in the dataframe
        type_data = type_data.sort_index()
        
        fig.add_trace(go.Bar(
            y=type_data['DisplayName'],
            x=type_data['Duration'],
            base=type_data['Start_Week'],
            orientation='h',
            name=task_type,
            marker_color=color_map[task_type],
            width=0.85 if task_type == 'Phase' else 0.45,
            text=None,
            textposition='none',
            hovertemplate=(
                "<b>%{y}</b><br>" +
                "Start: Day %{customdata[2]}<br>" +
                "Finish: Day %{customdata[3]}<br>" +
                "Duration: %{x} week(s)<br>" +
                "<extra></extra>"
            ),
            customdata=type_data[['Start_Week', 'Finish_Week', 'Start_Day', 'Finish_Day']],
            showlegend=True,
        ))

    # ==========================================
    # Maintain hierarchy order - NO reversal
    # ==========================================
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=category_order,  # Keep as is, not reversed
        title="",
        autorange="reversed",
        showgrid=True,
        gridcolor="#E0E0E0",
        gridwidth=1,
        tickfont=dict(size=16),  # <--- INCREASED FONT SIZE FOR Y-AXIS LABELS (NAMES)
    )

    # ==========================================
    # Customize x-axis with week labels
    # ==========================================
    max_week = df['Finish_Week'].max() + 1

    # Create tick values from 0 to max_week (inclusive for End)
    tick_values = list(range(max_week + 1))

    # Create week labels with day ranges
    week_labels = ["Start"]
    for i in range(1, max_week):
        start_day = (i * 7) + 1
        end_day = (i + 1) * 7
        week_labels.append(f"Week {i}")
    week_labels.append("End")

    fig.update_xaxes(
        tickvals=tick_values,
        ticktext=week_labels,
        showgrid=True,
        gridcolor="#E0E0E0",
        gridwidth=1,
        title="Timeline (Weeks)",
        range=[-0.5, max_week + 0.5],
        tickfont=dict(size=15),  # <--- INCREASED FONT SIZE FOR X-AXIS TICK LABELS
        title_font=dict(size=18),  # <--- INCREASED FONT SIZE FOR X-AXIS TITLE
    )

    # ==========================================
    # Add vertical lines at each week boundary
    # ==========================================
    # Add vertical lines for each week position (including Start and End)
    for week_pos in tick_values:
        fig.add_vline(
            x=week_pos,
            line_width=1,
            line_color="#D3D3D3",
            line_dash="solid",
            opacity=0.5,
        )

    # ==========================================
    # Add horizontal lines for each row
    # ==========================================
    # Get all y-axis positions (rows)
    y_positions = list(range(len(category_order)))

    # Add horizontal lines between each row
    for y_pos in y_positions:
        # Add a line at each row boundary (between rows)
        fig.add_hline(
            y=y_pos + 0.5,
            line_width=0.5,
            line_color="#D3D3D3",
            line_dash="solid",
            opacity=0.3,
        )

    # ==========================================
    # Layout
    # ==========================================
    fig.update_layout(
        title={
            "text": "Project Plan - Phase / Task Hierarchy (Day Numbers)",
            "x": 0.5,
            "font": {
                "size": 28,  # <--- INCREASED TITLE FONT SIZE
                "color": "#001F6B",
            },
        },
        height=900,  # <--- INCREASED HEIGHT FOR BETTER VISIBILITY
        width=1800,  # <--- INCREASED WIDTH FOR BETTER VISIBILITY
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend_title="",
        legend=dict(
            font=dict(size=16),  # <--- INCREASED LEGEND FONT SIZE
        ),
        font={
            "family": "Arial",
            "size": 14,  # <--- INCREASED GLOBAL FONT SIZE
            "color": "#001F6B",
        },
        margin=dict(
            l=280,  # <--- INCREASED LEFT MARGIN FOR LONGER NAMES
            r=50,
            t=80,
            b=50,
        ),
        barmode='overlay',
        bargap=0.2,
    )

    # ==========================================
    # Return base64 or figure (No file operations)
    # ==========================================
    if return_base64:
        # Convert to base64 (in-memory only)
        img_bytes = fig.to_image(format="png", width=2000, height=1200, scale=2)
        base64_str = base64.b64encode(img_bytes).decode('utf-8')
        return base64_str
    
    return fig

# ==========================================
# Example usage with the provided data
# ==========================================
if __name__ == "__main__":
    # Your original data
    data = [
        # ---------------------------------
        # PHASE 1
        # ---------------------------------
        {
            "Name": "Phase 1 - Planning",
            "Start_Day": 1,      # Day 1
            "Finish_Day": 21,    # Day 21
            "Type": "Phase",
            "Progress": 100,
            "isMain": True,
            "tasks": [
                {
                    "Name": "Task 1 - Requirements",
                    "Start_Day": 1,
                    "Finish_Day": 7,
                    "Type": "Task",
                    "Progress": 100,
                },
                {
                    "Name": "Task 2 - Analysis",
                    "Start_Day": 4,
                    "Finish_Day": 14,
                    "Type": "Task",
                    "Progress": 80,
                },
                {
                    "Name": "Task 3 - Approval",
                    "Start_Day": 15,
                    "Finish_Day": 21,
                    "Type": "Task",
                    "Progress": 60,
                }
            ]
        },
        
        # ---------------------------------
        # PHASE 2
        # ---------------------------------
        {
            "Name": "Phase 2 - Development",
            "Start_Day": 22,
            "Finish_Day": 45,
            "Type": "Phase",
            "Progress": 50,
            "isMain": True,
            "tasks": [
                {
                    "Name": "Task 1 - Backend",
                    "Start_Day": 22,
                    "Finish_Day": 30,
                    "Type": "Task",
                    "Progress": 70,
                },
                {
                    "Name": "Task 2 - Frontend",
                    "Start_Day": 31,
                    "Finish_Day": 40,
                    "Type": "Task",
                    "Progress": 40,
                },
                {
                    "Name": "Task 3 - Integration",
                    "Start_Day": 38,
                    "Finish_Day": 45,
                    "Type": "Task",
                    "Progress": 20,
                }
            ]
        },
        
        # ---------------------------------
        # PHASE 3
        # ---------------------------------
        {
            "Name": "Phase 3 - Testing & Release",
            "Start_Day": 46,
            "Finish_Day": 60,
            "Type": "Phase",
            "Progress": 10,
            "isMain": True,
            "tasks": [
                {
                    "Name": "Task 1 - QA Testing",
                    "Start_Day": 46,
                    "Finish_Day": 52,
                    "Type": "Task",
                    "Progress": 10,
                },
                {
                    "Name": "Task 2 - UAT",
                    "Start_Day": 53,
                    "Finish_Day": 56,
                    "Type": "Task",
                    "Progress": 0,
                },
                {
                    "Name": "Task 3 - Deployment",
                    "Start_Day": 57,
                    "Finish_Day": 60,
                    "Type": "Task",
                    "Progress": 0,
                }
            ]
        }
    ]

    # Call the function to get base64 encoded image (in-memory only)
    base64_image = create_hierarchical_gantt(
        data=data,
        return_base64=True
    )
    
    # Print the base64 string (this can be used in HTML img tags, APIs, etc.)
    print("Base64 Encoded Image:")
    print(base64_image[:100] + "..." if len(base64_image) > 100 else base64_image)
    print(f"\n✅ Image generated successfully! (Base64 length: {len(base64_image)} characters)")