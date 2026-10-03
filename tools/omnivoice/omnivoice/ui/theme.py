"""OmniChat HUD look: near-black background, teal 1 px frames, corner brackets, square corners."""
import gradio as gr

AC = "#35E0C8"          # teal accent
ACD = "rgba(53,224,200,.4)"  # dim accent (borders)
BG = "#0B0A0E"
PANEL = "#0F0D13"
TEXT = "#D9D4DC"
MUTED = "#8A8390"
FLAG = "#FFCF4A"
OK = "#59E36B"
BAD = "#FF5A5A"


def _both(**kw) -> dict:
    """Same value for light and dark mode, so the UI is dark whatever the browser prefers."""
    out = {}
    for k, v in kw.items():
        out[k] = v
        out[k + "_dark"] = v
    return out


THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.teal,
    neutral_hue=gr.themes.colors.zinc,
    font=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    radius_size=gr.themes.sizes.radius_none,
).set(
    **_both(
        body_background_fill=BG,
        body_text_color=TEXT,
        body_text_color_subdued=MUTED,
        background_fill_primary=PANEL,
        background_fill_secondary=BG,
        border_color_primary=ACD,
        border_color_accent=AC,
        block_background_fill=PANEL,
        block_border_color=ACD,
        block_border_width="1px",
        block_label_background_fill=BG,
        block_label_text_color=AC,
        block_label_border_color=ACD,
        block_title_text_color=AC,
        block_info_text_color=MUTED,
        panel_background_fill=PANEL,
        panel_border_color=ACD,
        input_background_fill=BG,
        input_background_fill_focus=BG,
        input_border_color=ACD,
        input_border_color_focus=AC,
        input_placeholder_color=MUTED,
        button_primary_background_fill="transparent",
        button_primary_background_fill_hover="rgba(53,224,200,.12)",
        button_primary_border_color=AC,
        button_primary_border_color_hover=AC,
        button_primary_text_color=AC,
        button_primary_text_color_hover=AC,
        button_secondary_background_fill="transparent",
        button_secondary_background_fill_hover="rgba(53,224,200,.08)",
        button_secondary_border_color=ACD,
        button_secondary_border_color_hover=AC,
        button_secondary_text_color=TEXT,
        button_secondary_text_color_hover=AC,
        button_cancel_background_fill="transparent",
        button_cancel_border_color=BAD,
        button_cancel_text_color=BAD,
        checkbox_background_color=BG,
        checkbox_background_color_selected=AC,
        checkbox_border_color=ACD,
        checkbox_border_color_selected=AC,
        checkbox_label_background_fill="transparent",
        checkbox_label_background_fill_selected="rgba(53,224,200,.08)",
        checkbox_label_border_color="transparent",
        checkbox_label_border_color_selected=AC,
        checkbox_label_text_color=MUTED,
        checkbox_label_text_color_selected=AC,
        table_border_color="#2A2430",
        table_even_background_fill=PANEL,
        table_odd_background_fill=BG,
        table_text_color=TEXT,
        table_row_focus="rgba(53,224,200,.10)",
        color_accent_soft="rgba(53,224,200,.10)",
        link_text_color=AC,
        link_text_color_hover=AC,
        link_text_color_visited=AC,
        loader_color=AC,
        slider_color=AC,
        code_background_fill=BG,
        error_background_fill=BG,
        error_border_color=BAD,
        error_text_color=BAD,
        block_shadow="none",
        button_primary_shadow="none",
        button_secondary_shadow="none",
        input_shadow="none",
        input_border_width="1px",
    ),
    color_accent=AC,
    button_border_width="1px",
    shadow_drop="none",
    shadow_drop_lg="none",
)

HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Silkscreen&family=JetBrains+Mono:wght@400;600'
        '&display=swap" rel="stylesheet">')

CSS = f"""
:root {{ --ac:{AC}; --acd:{ACD}; --flag:{FLAG}; --ok:{OK}; --bad:{BAD}; --muted:{MUTED}; }}
footer {{ display:none !important; }}
.form {{ background:transparent !important; border:0 !important; gap:10px !important; }}
.gradio-container {{ width:100% !important; max-width: 1400px !important; margin-left:auto !important; margin-right:auto !important; }}
.hud-panel {{ width:100%; }}
/* table headers stay on one line */
.hud-section table th {{ white-space:nowrap; }}

/* the whole app sits in one HUD frame with corner brackets */
.hud-panel {{ border:1px solid var(--ac) !important; position:relative; overflow:visible !important;
             background:{BG} !important; padding:0 !important; gap:0 !important; }}
.hud-panel::before, .hud-panel::after {{ content:""; position:absolute; width:10px; height:10px;
             border:2px solid var(--ac); pointer-events:none; z-index:5; }}
.hud-panel::before {{ top:-3px; left:-3px; border-right:0; border-bottom:0; }}
.hud-panel::after {{ bottom:-3px; right:-3px; border-left:0; border-top:0; }}

/* header */
.hud-top {{ display:flex; align-items:center; gap:14px; padding:10px 14px !important;
           border-bottom:1px solid var(--acd) !important; background:{BG}; }}
.hud-title {{ font-family:'Silkscreen', 'JetBrains Mono', monospace; color:var(--ac);
             letter-spacing:6px; font-size:18px; }}
.hud-badge {{ color:var(--muted); font-size:12px; }}
.muted {{ color:var(--muted); }}

/* gradio pads every HTML block; the header and steps bar draw their own full-width rules */
.html-container:has(.hud-top), .html-container:has(.steps) {{ padding:0 !important; }}
.hud-top {{ padding-left:18px !important; padding-right:18px !important; }}

/* sidebar: stretch to the full height so its divider runs down to the frame */
.hud-panel > .row {{ align-items:stretch !important; gap:0 !important; }}
.hud-nav {{ align-self:stretch !important; }}
.hud-nav {{ border-right:1px solid var(--acd) !important; padding:10px !important; background:{BG};
           min-width:200px; }}
.hud-nav .block {{ background:transparent !important; border:0 !important; }}
.hud-nav fieldset > div {{ display:flex; flex-direction:column; gap:2px; }}
.hud-nav fieldset label {{ border:0 !important; border-left:2px solid transparent !important;
           padding:6px 8px !important; color:var(--muted) !important; background:transparent !important;
           box-shadow:none !important; width:100%; }}
.hud-nav fieldset label.selected {{ color:var(--ac) !important; border-left-color:var(--ac) !important;
           background:rgba(53,224,200,.06) !important; }}
.hud-nav fieldset label input {{ display:none; }}
.hud-nav fieldset label:not(.selected):hover {{ color:{TEXT} !important; background:rgba(53,224,200,.04) !important; }}
.hud-new {{ border:1px dashed var(--acd) !important; padding:6px !important; margin-top:8px; }}

/* main area */
.hud-main {{ padding:0 !important; gap:0 !important; background:{BG}; }}
.hud-section {{ padding:12px 14px !important; border:0 !important; background:{BG} !important; gap:10px !important; }}
.hud-section > .styler, .hud-section .form {{ background:transparent !important; }}

/* steps bar */
.steps {{ display:flex; flex-wrap:wrap; gap:4px; padding:10px 14px; border-bottom:1px solid var(--acd); }}
.st {{ padding:4px 9px; border:1px solid var(--acd); color:var(--muted); cursor:pointer; user-select:none;
      font-family:'Silkscreen', 'JetBrains Mono', monospace; font-size:11px; letter-spacing:1px; }}
.st:hover {{ border-color:var(--ac); }}
.st.done {{ color:var(--ok); border-color:#59e36b55; }}
.st.on {{ color:var(--ac); border-color:var(--ac); background:rgba(53,224,200,.08); }}

/* phrases */
.stat {{ display:flex; flex-wrap:wrap; gap:16px; font-size:13px; }}
.stat b {{ color:var(--ac); font-weight:600; }}
.flag {{ color:var(--flag) !important; }}
.bad {{ color:var(--bad); text-decoration:line-through; }}

/* buttons: caps like the mod */
button.lg, button.md, button.sm {{ letter-spacing:1px; text-transform:uppercase; }}

/* check report */
.report p {{ margin:4px 0; }}
.report .err {{ color:var(--bad); }}
.report .warn {{ color:var(--flag); }}
.report .ok {{ color:var(--ok); }}
.report table.issues {{ border-collapse:collapse; margin-top:6px; }}
.report table.issues td {{ border-bottom:1px dashed #2a2430; padding:3px 10px 3px 0; }}

/* train */
.train-status {{ font-family:'Silkscreen', 'JetBrains Mono', monospace; color:var(--ac); letter-spacing:1px; }}
.portrait img {{ image-rendering: pixelated; }}
.section-msg {{ min-height:1.2em; }}
.section-msg.err, .section-msg .err {{ color:var(--bad); }}

/* setup: dependency checklist, progress bar, reboot notice */
.st.warn {{ color:var(--flag); border-color:var(--flag); }}
.checklist {{ display:flex; flex-direction:column; border:1px solid var(--acd); }}
.ck-row {{ display:grid; grid-template-columns:22px minmax(150px, 220px) 1fr; gap:10px; align-items:baseline;
          padding:6px 10px; border-bottom:1px dashed #2a2430; font-size:13px; }}
.ck-row:last-child {{ border-bottom:0; }}
.ck-row.muted {{ display:block; color:var(--muted); }}
.ck-mark {{ font-weight:600; }}
.ck-row.ok .ck-mark, .ck-row.ok .ck-name {{ color:var(--ok); }}
.ck-row.miss .ck-mark, .ck-row.miss .ck-name {{ color:var(--bad); }}
.ck-row.opt .ck-mark, .ck-row.opt .ck-name {{ color:var(--muted); }}
.ck-detail {{ color:var(--muted); overflow-wrap:anywhere; }}
.ck-chip {{ margin-left:8px; padding:0 6px; border:1px solid var(--acd); color:var(--muted); font-size:10px;
           letter-spacing:1px; text-transform:uppercase; }}
.setup-progress {{ display:flex; flex-direction:column; gap:6px; }}
.setup-bar {{ height:10px; border:1px solid var(--acd); background:{BG}; }}
.setup-bar i {{ display:block; height:100%; background:var(--ac); transition:width .4s; }}
.setup-step {{ font-size:12px; color:var(--muted); min-height:1.2em; }}
.setup-reboot {{ border:1px solid var(--flag); color:var(--flag); padding:10px 14px; background:rgba(255,207,74,.06); }}
.setup-reboot b {{ font-family:'Silkscreen', 'JetBrains Mono', monospace; letter-spacing:2px; font-size:15px; }}
.setup-reboot p {{ margin:6px 0 0; color:{TEXT}; }}
.train-status.ok {{ color:var(--ok); }}

/* dropdowns: pointer cursor, framed popup, teal hover */
input[role=combobox] {{ cursor:pointer; }}
.wrap:has(> .wrap-inner input[role=combobox]) {{ cursor:pointer; }}
ul.option-list {{ background:{PANEL} !important; border:1px solid var(--ac) !important; padding:2px 0 !important;
                 box-shadow:0 6px 18px rgba(0,0,0,.6) !important; }}
ul.option-list li.item {{ background:transparent !important; color:{TEXT}; padding:6px 10px !important; }}
ul.option-list li.item:hover, ul.option-list li.item.active {{ background:rgba(53,224,200,.12) !important; color:var(--ac); }}
ul.option-list li.item.selected {{ color:var(--ac); }}

/* lone checkboxes sit on the page, not in a filled box */
.block:has(label.checkbox-container) {{ background:transparent !important; border:0 !important; }}

/* a button next to a field lines up with the field, not the whole row height */
.hud-section .row:has(> button) {{ align-items:flex-end !important; }}
.hud-section .row > button {{ align-self:flex-end !important; min-height:40px; max-height:42px; }}

/* clickable things look clickable */
button, .st, .hud-nav fieldset label, .label-wrap, input[type=checkbox], label:has(> input[type=checkbox]) {{ cursor:pointer !important; }}
button:disabled {{ cursor:not-allowed !important; opacity:.5; }}
"""
