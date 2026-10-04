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

# icons used as CSS masks (the colour comes from background); Lucide "rotate-ccw", ISC licence
UNDO_SVG = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
            "stroke='black' stroke-width='2.4' stroke-linecap='square' stroke-linejoin='miter'%3E"
            "%3Cpath d='M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8'/%3E%3Cpath d='M3 3v5h5'/%3E%3C/svg%3E")


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
        '&display=swap" rel="stylesheet">'
        + """<script>
/* Logs (.log-box): follow the tail while the user is at the bottom; scrolling up pins the view
   and shows a "down" button; scrolling back to the bottom re-attaches. Gradio rewrites the whole
   value every tick, so the position is restored by hand. */
(() => {
  const NEAR = 12;
  const atBottom = el => el.scrollHeight - el.scrollTop - el.clientHeight < NEAR;
  function attach(box, ta) {
    ta.dataset.logBound = "1";
    const st = { stick: true, pos: 0, len: -1, user: 0 };
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "log-down"; btn.title = "Вниз"; btn.textContent = "↓";
    box.appendChild(btn);
    const sync = () => btn.classList.toggle("show", !st.stick);
    btn.addEventListener("click", () => { st.stick = true; ta.scrollTop = ta.scrollHeight; sync(); });
    const mark = () => { st.user = Date.now(); };
    ["wheel", "touchstart", "keydown", "pointerdown"].forEach(e => ta.addEventListener(e, mark, { passive: true }));
    ta.addEventListener("scroll", () => {
      if (Date.now() - st.user > 1500) return;  // programmatic scroll (value rewrite), not the user
      st.stick = atBottom(ta); st.pos = ta.scrollTop; sync();
    });
    ta._logTick = () => {
      if (ta.value.length !== st.len) {
        st.len = ta.value.length;
        if (st.stick) ta.scrollTop = ta.scrollHeight; else ta.scrollTop = st.pos;
      } else if (st.stick && !atBottom(ta)) ta.scrollTop = ta.scrollHeight;
    };
  }
  setInterval(() => {
    document.querySelectorAll(".log-box").forEach(box => {
      const ta = box.querySelector("textarea");
      if (!ta) return;
      if (!ta.dataset.logBound) attach(box, ta);
      ta._logTick();
    });
  }, 200);
})();
/* HUD audio player (.rp: play button, seek bar, time, hidden <audio>), event delegation so it survives
   gr.render re-renders. One plays at a time. */
(() => {
  const fmt = t => { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); };
  const sync = a => {
    const rp = a.closest(".rp"); if (!rp) return;
    const d = a.duration || 0;
    rp.querySelector(".rp-bar i").style.width = (d ? a.currentTime / d * 100 : 0) + "%";
    rp.querySelector(".rp-time").textContent = fmt(a.currentTime) + " / " + fmt(d);
    rp.classList.toggle("playing", !a.paused && !a.ended);
  };
  ["timeupdate", "loadedmetadata", "play", "pause", "ended"].forEach(ev =>
    document.addEventListener(ev, e => { if (e.target.closest && e.target.closest(".rp")) sync(e.target); }, true));
  document.addEventListener("click", e => {
    const rp = e.target.closest && e.target.closest(".rp"); if (!rp) return;
    const a = rp.querySelector("audio");
    if (e.target.closest(".rp-play")) {
      document.querySelectorAll(".rp audio").forEach(o => { if (o !== a) o.pause(); });
      a.paused ? a.play() : a.pause();
    } else if (e.target.closest(".rp-rm")) {
      a.pause();
      const hidden = rp.closest(".raw-row") && rp.closest(".raw-row").querySelector("button.raw-rm-hidden");
      if (hidden) hidden.click();
    } else if (e.target.closest(".rp-bar") && a.duration) {
      const r = rp.querySelector(".rp-bar").getBoundingClientRect();
      a.currentTime = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * a.duration;
    }
  });
})();
/* phrases: the card whose ▶ was pressed stays highlighted (its audio is in the player below) */
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("button.phr-play"); if (!b) return;
  document.querySelectorAll(".phr-row.current").forEach(r => r.classList.remove("current"));
  const row = b.closest(".phr-row"); if (row) row.classList.add("current");
});
/* Gradio's dropdown re-filters by its own text on any non-navigation key, so a bare Shift / Win
   (e.g. Win+Shift+S for a screenshot) shrinks an open list to the selected item. Non-filterable
   (readonly) dropdowns only need the navigation keys; filterable ones lose just the modifiers. */
(() => {
  const MODS = new Set(["Shift", "Control", "Alt", "Meta", "OS", "AltGraph", "CapsLock"]);
  const NAV = new Set(["ArrowUp", "ArrowDown", "Home", "End", "Enter", "Escape", "Tab"]);
  const eat = e => {
    const t = e.target;
    if (!(t.matches && t.matches("input[role=combobox]"))) return;
    if (MODS.has(e.key) || (t.readOnly && !NAV.has(e.key))) e.stopImmediatePropagation();
  };
  window.addEventListener("keydown", eat, true);
  window.addEventListener("keyup", eat, true);
})();
</script>""")

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
.hud-title {{ font-family:'Silkscreen', 'JetBrains Mono', monospace;  /* Silkscreen has no Cyrillic: Latin-only logo */ color:var(--ac);
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
/* «Новый проект» / «Удаление проекта» are hidden radio items, opened by their own buttons */
fieldset.hud-sections label:has(input[value="Новый проект"]),
fieldset.hud-sections label:has(input[value="Удаление проекта"]) {{ display:none !important; }}
button.hud-new-btn {{ margin-top:12px; border:1px dashed var(--acd) !important; background:transparent !important;
                     color:var(--ac) !important; text-transform:none !important; justify-content:flex-start !important;
                     padding:8px 10px !important; font-size:13px !important; letter-spacing:0 !important; }}
button.hud-new-btn:hover {{ border-style:solid !important; background:rgba(53,224,200,.06) !important; }}

button.hud-del-btn {{ margin-top:6px; color:var(--muted) !important; border-color:#3a2a2e !important; }}
button.hud-del-btn:hover {{ color:var(--bad) !important; border-color:var(--bad) !important;
                          background:rgba(255,90,90,.06) !important; }}

/* delete project page */
.del-sub {{ color:var(--bad) !important; border-bottom-color:rgba(255,90,90,.4) !important; }}
.del-card {{ border:1px solid rgba(255,90,90,.45); padding:14px 16px; max-width:560px; }}
.del-name {{ font-size:18px; font-weight:600; color:{TEXT}; margin-bottom:10px; }}
.del-head {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }}
.del-row {{ display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px dashed #2a2430;
           font-size:13px; }}
.del-row b {{ font-weight:600; }}
.del-total {{ border-bottom:0; padding-top:8px; font-size:14px; }}
.del-total b {{ color:var(--bad); }}

/* audio: uploaded recordings as cards */
.raw-upload {{ min-height:0 !important; }}
.raw-total {{ font-size:12px; margin-bottom:4px; }}
.raw-row {{ border:1px solid var(--acd) !important; padding:10px 12px 10px 14px !important; align-items:center !important;
           gap:14px !important; background:{PANEL} !important; margin-bottom:6px; }}
.raw-row:hover {{ border-color:var(--ac) !important; }}
.raw-row {{ flex-wrap:nowrap !important; }}
.raw-card-wrap {{ flex:1 1 0 !important; min-width:0 !important; padding:0 !important; border:0 !important; overflow:hidden;
                 background:transparent !important; }}
.html-container:has(.raw-card) {{ padding:0 !important; }}
.raw-card {{ display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; min-width:0; }}
.raw-card .raw-name {{ flex:0 1 240px; min-width:120px; }}
.raw-card .rp {{ flex:1 1 260px; }}

/* HUD audio player: square buttons, icons centred by grid (no pixel offsets), square teal focus ring */
.rp {{ display:flex; align-items:center; gap:12px; min-width:0; }}
.rp audio {{ display:none; }}
.rp-play, .rp-rm {{ flex:none; box-sizing:border-box; width:32px; height:32px; padding:0; margin:0; display:grid;
                   place-items:center; background:transparent; border-radius:0; cursor:pointer; outline:none;
                   box-shadow:none; }}
/* keyboard focus: a fill, not an outer ring — the card clips anything drawn outside the button */
.rp-play:focus-visible, .rp-rm:focus-visible {{ background:rgba(53,224,200,.2); border-color:var(--ac); }}
.rp-play {{ border:1px solid var(--ac); }}
.rp-play:hover {{ background:rgba(53,224,200,.12); }}
.rp-play::before {{ content:""; width:0; height:0; margin-left:2px;  /* a triangle looks centred 2 px to the right */
                   border-left:10px solid var(--ac); border-top:6px solid transparent; border-bottom:6px solid transparent; }}
.rp.playing .rp-play::before {{ box-sizing:content-box; width:4px; height:12px; margin-left:0; border:0;
                               border-left:3px solid var(--ac); border-right:3px solid var(--ac); }}
.rp-rm {{ border:1px solid #3a2a2e; }}
.rp-rm::before, .rp-rm::after {{ content:""; grid-area:1 / 1; width:12px; height:1.5px; background:var(--muted); }}
.rp-rm::before {{ transform:rotate(45deg); }}
.rp-rm::after {{ transform:rotate(-45deg); }}
.rp-rm:hover {{ border-color:var(--bad); background:rgba(255,90,90,.08); }}
.rp-rm:hover::before, .rp-rm:hover::after {{ background:var(--bad); }}
.rp-bar {{ flex:1; height:6px; border:1px solid var(--acd); cursor:pointer; min-width:40px; }}
/* a narrow card drops the time first, so the buttons never get clipped */
.raw-card-wrap {{ container-type:inline-size; }}
@container (max-width: 340px) {{ .rp-time {{ display:none; }} }}
.rp-bar:hover {{ border-color:var(--ac); }}
.rp-bar i {{ display:block; height:100%; width:0; background:var(--ac); }}
.rp-time {{ flex:none; min-width:84px; text-align:right; font-size:12px; color:var(--muted);
           font-variant-numeric:tabular-nums; }}
.raw-name {{ display:flex; flex-direction:column; gap:2px; overflow:hidden; }}
.raw-name b {{ font-weight:600; color:{TEXT}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.raw-name .muted {{ font-size:12px; }}
/* the real delete is a hidden Gradio button; the ✕ in the player line clicks it (theme.HEAD) */
.raw-rm-hidden {{ display:none !important; }}
.audio-msg {{ min-height:56px; }}
.hud-section .row.slice-row {{ align-items:center !important; }}
.hud-section .row.slice-row > button {{ align-self:center !important; margin-bottom:0 !important; }}

/* phrases: one card per phrase (▶ · name / duration / flags + editable text · ✕ or ↺) */
.phr-list {{ max-height:600px; overflow-y:auto !important; gap:6px !important; padding-right:4px !important;
            flex-wrap:nowrap !important; }}
.hud-section .row.phr-row {{ flex-wrap:nowrap !important; align-items:center !important; gap:12px !important;
            border:1px solid var(--acd) !important; background:{PANEL} !important; padding:8px 10px !important;
            margin:0 !important; flex:none !important; }}
.hud-section .row.phr-row:hover {{ border-color:var(--ac) !important; }}
.hud-section .row.phr-row.flagged {{ box-shadow:inset 3px 0 0 var(--flag) !important; }}
.hud-section .row.phr-row.current {{ border-color:var(--ac) !important; background:rgba(53,224,200,.06) !important; }}
/* a dropped phrase is dimmed, but its ↺ stays bright: that is the one thing to do with it */
.phr-row.dropped .phr-body, .hud-section .row.phr-row.dropped > button.phr-play {{ opacity:.45; }}
.phr-row.dropped textarea {{ text-decoration:line-through; }}
.phr-body {{ gap:2px !important; min-width:0 !important; padding:0 !important; border:0 !important;
            background:transparent !important; }}
.html-container:has(.phr-meta) {{ padding:0 !important; }}
.phr-meta {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; font-size:12px; padding-left:9px; }}
.phr-meta b {{ font-weight:600; color:var(--muted); }}
.phr-chip {{ border:1px solid var(--acd); padding:0 6px; font-size:11px; color:var(--muted); }}
.phr-chip.flag {{ color:var(--flag); border-color:rgba(255,207,74,.5); }}
.phr-text {{ padding:0 !important; border:0 !important; background:transparent !important; }}
.phr-text textarea {{ background:transparent !important; border:1px solid transparent !important; box-shadow:none !important;
                     padding:4px 8px !important; font-size:14px !important; color:{TEXT} !important; resize:none;
                     /* grow with the text (Gradio sizes it once, to one line): long phrases wrap, not clip */
                     field-sizing:content; height:auto !important; min-height:0 !important; max-height:8em; }}
.phr-row:hover .phr-text textarea {{ border-color:var(--acd) !important; }}
.phr-text textarea:focus {{ border-color:var(--ac) !important; background:{BG} !important; }}
.hud-section .row.phr-row > button.phr-btn {{ flex:none !important; align-self:center !important; margin:0 !important;
       box-sizing:border-box !important; width:32px !important; min-width:32px !important; max-width:32px !important;
       height:32px !important; min-height:32px !important; max-height:32px !important; padding:0 !important;
       position:relative !important; font-size:0 !important; color:transparent !important; background:transparent !important;
       border-radius:0 !important; box-shadow:none !important; outline:none !important; letter-spacing:0 !important; }}
.hud-section .row.phr-row > button.phr-play {{ border:1px solid var(--ac) !important; }}
.hud-section .row.phr-row > button.phr-play:hover {{ background:rgba(53,224,200,.12) !important; }}
/* icons are absolutely centred: Gradio keeps the (invisible) label text in the button, which would
   otherwise take a grid / flex slot and push the icon off-centre */
button.phr-btn::before, button.phr-btn::after {{ content:""; position:absolute; inset:0; margin:auto; }}
button.phr-play::before {{ width:0; height:0; transform:translateX(2px);  /* a triangle looks centred 2 px to the right */
                          border-left:10px solid var(--ac); border-top:6px solid transparent; border-bottom:6px solid transparent; }}
button.phr-play::after {{ display:none; }}
.hud-section .row.phr-row > button.phr-rm {{ border:1px solid #3a2a2e !important; }}
button.phr-rm::before, button.phr-rm::after {{ width:12px; height:1.5px; background:var(--muted); }}
button.phr-rm::before {{ transform:rotate(45deg); }}
button.phr-rm::after {{ transform:rotate(-45deg); }}
.hud-section .row.phr-row > button.phr-rm:hover {{ border-color:var(--bad) !important; background:rgba(255,90,90,.08) !important; }}
button.phr-rm:hover::before, button.phr-rm:hover::after {{ background:var(--bad); }}
/* ↺ «вернуть»: an anticlockwise arrow drawn as an SVG mask (a CSS-border arrow can't put the head on the arc) */
.hud-section .row.phr-row > button.phr-back {{ border:1px solid var(--ac) !important; }}
button.phr-back::before {{ width:16px; height:16px; background:var(--ac);
                          -webkit-mask:url("{UNDO_SVG}") center / contain no-repeat;
                          mask:url("{UNDO_SVG}") center / contain no-repeat; }}
button.phr-back::after {{ display:none; }}
.hud-section .row.phr-row > button.phr-back:hover {{ background:rgba(53,224,200,.12) !important; }}
.hud-section .row.phr-row > button.phr-btn:focus-visible {{ background:rgba(53,224,200,.2) !important; }}

/* new project: base models as cards */
.base-cards .wrap {{ display:grid !important; gap:8px !important;
               grid-template-columns:repeat(3, minmax(0, 1fr)) !important; }}  /* 3 male voices per language: a row per gender */
@media (max-width: 900px) {{ .base-cards .wrap {{ grid-template-columns:1fr !important; }} }}
.base-cards label {{ border:1px solid var(--acd) !important; padding:12px 14px !important; background:transparent !important;
               box-shadow:none !important; margin:0 !important; white-space:nowrap; overflow:hidden; }}
.base-cards label:hover {{ border-color:var(--ac) !important; }}
.base-cards label.selected {{ border-color:var(--ac) !important; color:var(--ac) !important;
               background:rgba(53,224,200,.08) !important; }}

/* main area: plain text (status lines, notes, sub-heads) starts at the same edge as the framed blocks
   and buttons — Gradio pads every HTML block by 12 px, which left text visibly indented */
.hud-section .html-container {{ padding-left:0 !important; padding-right:0 !important; }}
.chart-empty {{ border:1px dashed var(--acd); padding:26px 16px; text-align:center; color:var(--muted);
               font-size:13px; }}
/* a row whose children are all hidden (e.g. the charts before the first epoch) keeps no element children,
   only comments — `:empty` misses it, yet it would still add a gap */
.hud-section .row:not(:has(*)) {{ display:none !important; }}
/* training: buttons → status → charts / empty card → log, 20 px apart */
.html-container:has(.train-status) {{ padding-top:0 !important; }}
.html-container:has(.chart-empty) {{ padding-top:0 !important; padding-bottom:10px !important; }}
.chart-note:not(:has(.chart-empty)) {{ display:none !important; }}  /* charts shown: the empty note takes no gap */
.hud-section .row.charts-row {{ margin-bottom:10px !important; }}

/* main area */
.hud-main {{ padding:0 !important; gap:0 !important; background:{BG}; }}
.hud-section {{ padding:12px 14px !important; border:0 !important; background:{BG} !important; gap:10px !important; }}
.hud-section > .styler, .hud-section .form {{ background:transparent !important; }}

/* steps bar */
.steps {{ display:flex; flex-wrap:wrap; gap:4px; padding:10px 14px; border-bottom:1px solid var(--acd); }}
.st {{ padding:4px 9px; border:1px solid var(--acd); color:var(--muted); cursor:pointer; user-select:none;
      font-family:'JetBrains Mono', monospace; font-weight:600; text-transform:uppercase; font-size:11px; letter-spacing:1px; }}
.st:hover {{ border-color:var(--ac); }}
.st.done {{ color:var(--ok); border-color:#59e36b55; }}
.st.off {{ opacity:.4; cursor:default !important; }}
.st.off:hover {{ border-color:var(--acd); }}
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
.train-status {{ font-family:'JetBrains Mono', monospace; font-weight:600; color:var(--ac); letter-spacing:1px; }}
.sub-head {{ font-family:'JetBrains Mono', monospace; font-weight:600; text-transform:uppercase; color:var(--ac); letter-spacing:2px; font-size:12px;
            text-transform:uppercase; border-bottom:1px solid var(--acd); padding:10px 0 4px; margin-top:6px; }}
.listen-head {{ color:{TEXT}; font-size:13px; }}
.disk-line {{ font-family:'JetBrains Mono', monospace; color:{TEXT}; font-size:13px; }}
.section-msg.muted {{ color:var(--muted); font-size:12px; }}
.listen-row {{ flex-wrap:wrap !important; gap:8px !important; }}
.listen-row > div {{ flex:1 1 150px !important; }}
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
.setup-reboot b {{ font-family:'JetBrains Mono', monospace; font-weight:600; text-transform:uppercase; letter-spacing:2px; font-size:15px; }}
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
.hud-section .row > button {{ align-self:flex-end !important; min-height:40px; max-height:42px;
                             white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                             margin-bottom:10px; }}  /* fields sit inside a block with 10 px padding */

/* scrollbars in the HUD palette */
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:{BG}; }}
::-webkit-scrollbar-thumb {{ background:{ACD}; border:1px solid {BG}; }}
::-webkit-scrollbar-thumb:hover {{ background:var(--ac); }}
::-webkit-scrollbar-button {{ display:none; height:0; width:0; }}
::-webkit-scrollbar-corner {{ background:{BG}; }}
@supports not selector(::-webkit-scrollbar) {{ * {{ scrollbar-color:{ACD} {BG}; scrollbar-width:thin; }} }}

/* logs: "jump to the end" button over the bottom-right corner (shown after scrolling up) */
.log-box {{ position:relative; }}
.log-down {{ position:absolute; right:22px; bottom:18px; width:30px; height:30px; display:none; z-index:6;
            background:{PANEL}; color:var(--ac); border:1px solid var(--ac); font-size:16px; line-height:1;
            box-shadow:0 0 10px rgba(53,224,200,.25); }}
.log-down.show {{ display:block; }}
.log-down:hover {{ background:rgba(53,224,200,.15); }}

/* checkpoints: a row click picks the checkpoint */
.ckpt-table td {{ cursor:pointer; }}
.ckpt-table tr:hover td {{ background:rgba(53,224,200,.06) !important; }}

/* fields side by side: labels on top, inputs on one line even when one label wraps to two lines
   (number: label > input; textbox: label > .input-container > input) */
.hud-section .row .block:has(> label.container input) {{ display:flex !important; flex-direction:column !important; }}
.hud-section .row .block:has(> label.container input) > label.container {{ display:flex !important;
    flex-direction:column !important; flex:1 1 auto !important; }}
.hud-section .row .block > label.container > input,
.hud-section .row .block > label.container > .input-container {{ margin-top:auto !important; }}
/* one height for every single-line field: text / number inputs match the 40 px dropdown frame */
.hud-section label.container input[type=text]:not([role=combobox]),
.hud-section label.container input[type=number] {{ box-sizing:border-box !important; height:40px !important; }}

/* number fields: no browser spin arrows (grey, off-style); typing and the ↑/↓ keys still work */
input[type=number]::-webkit-inner-spin-button, input[type=number]::-webkit-outer-spin-button {{
    -webkit-appearance:none; appearance:none; margin:0; }}
input[type=number] {{ -moz-appearance:textfield; appearance:textfield; }}

/* clickable things look clickable */
button, .st, .hud-nav fieldset label, .label-wrap, input[type=checkbox], label:has(> input[type=checkbox]) {{ cursor:pointer !important; }}
button:disabled {{ cursor:not-allowed !important; opacity:.5; }}
"""
