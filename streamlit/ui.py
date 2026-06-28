"""
ui.py — visual theme + reusable components for the RFAP dashboard
=================================================================
Centralizes the dark "trading-desk" look so every tab is consistent:
injected CSS, KPI cards, badges, section headers, and Plotly styling.
Imported by app.py.
"""
import streamlit as st

# Palette
BG      = "#0e1117"
SURFACE = "#161b22"
LINE    = "#21262d"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"
GREEN   = "#16c784"
RED     = "#ea3943"
BLUE    = "#2f81f7"
AMBER   = "#f0a020"
PLOTLY_FONT = dict(family="Inter, Segoe UI, sans-serif", color=TEXT)


def inject_theme():
    st.markdown(f"""
    <style>
      .stApp {{ background: {BG}; }}
      .block-container {{ padding-top: 1.2rem; max-width: 1400px; }}
      h1, h2, h3, h4 {{ color: {TEXT}; font-family: Inter, 'Segoe UI', sans-serif; }}
      /* hero banner */
      .rfap-hero {{
        background: linear-gradient(120deg, #11151c 0%, #161b22 55%, #0d2b4a 100%);
        border: 1px solid {LINE}; border-radius: 16px;
        padding: 20px 26px; margin-bottom: 18px;
      }}
      .rfap-hero h1 {{ margin: 0; font-size: 1.6rem; letter-spacing: .2px; }}
      .rfap-hero p  {{ margin: 6px 0 0; color: {MUTED}; font-size: .92rem; }}
      /* KPI cards */
      .kpi {{
        background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px;
        padding: 16px 18px; box-shadow: 0 1px 0 rgba(255,255,255,.02);
        min-height: 104px;
      }}
      .kpi .label {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase;
                     letter-spacing: .6px; }}
      .kpi .value {{ color: {TEXT}; font-size: 1.7rem; font-weight: 700;
                     font-variant-numeric: tabular-nums; margin-top: 2px; }}
      .kpi .delta {{ font-size: .85rem; font-weight: 600; margin-top: 4px; }}
      .kpi .sub   {{ color: {MUTED}; font-size: .78rem; margin-top: 2px; }}
      .up   {{ color: {GREEN}; }} .down {{ color: {RED}; }} .flat {{ color: {MUTED}; }}
      /* badges */
      .badge {{ display:inline-block; padding: 2px 10px; border-radius: 999px;
                font-size: .74rem; font-weight: 600; }}
      .badge-pos {{ background: rgba(22,199,132,.15); color: {GREEN}; }}
      .badge-neg {{ background: rgba(234,57,67,.15); color: {RED}; }}
      .badge-neu {{ background: rgba(139,148,158,.15); color: {MUTED}; }}
      .badge-warn{{ background: rgba(240,160,32,.15); color: {AMBER}; }}
      /* news / reason cards */
      .card {{ background: {SURFACE}; border: 1px solid {LINE};
               border-left: 3px solid {BLUE}; border-radius: 10px;
               padding: 12px 14px; margin-bottom: 10px; }}
      .card.neg {{ border-left-color: {RED}; }}
      .card.pos {{ border-left-color: {GREEN}; }}
      .card .h  {{ color: {TEXT}; font-weight: 600; font-size: .95rem; }}
      .card .m  {{ color: {MUTED}; font-size: .8rem; margin-top: 4px; }}
      .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
      .stTabs [data-baseweb="tab"] {{ color: {MUTED}; }}
      .stTabs [aria-selected="true"] {{ color: {TEXT}; }}
    </style>
    """, unsafe_allow_html=True)


def hero(title: str, subtitle: str):
    st.markdown(f"""
      <div class="rfap-hero">
        <h1>{title}</h1><p>{subtitle}</p>
      </div>""", unsafe_allow_html=True)


def kpi_card(label, value, delta=None, delta_is_pct=False, positive=None, sub=None):
    """Return HTML for one KPI card. `positive` None = neutral grey."""
    delta_html = ""
    if delta is not None:
        cls = "flat" if positive is None else ("up" if positive else "down")
        arrow = "" if positive is None else ("▲ " if positive else "▼ ")
        suffix = "%" if delta_is_pct else ""
        delta_html = f'<div class="delta {cls}">{arrow}{delta}{suffix}</div>'
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi"><div class="label">{label}</div>'
            f'<div class="value">{value}</div>{delta_html}{sub_html}</div>')


def kpi_row(cards: list):
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        col.markdown(kpi_card(**c), unsafe_allow_html=True)


def badge(text: str, kind: str = "neu") -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


def style_fig(fig, height=360, legend=True):
    """Apply the dark theme to a Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=PLOTLY_FONT, height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=legend,
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
        xaxis=dict(gridcolor=LINE, zeroline=False),
        yaxis=dict(gridcolor=LINE, zeroline=False),
    )
    return fig
