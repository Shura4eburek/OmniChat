package org.mamoru.omnichat.client.ui;

/** Pure layout math for OmnichatScreen, in scaled GUI pixels. */
public record HudLayout(Rect panel, Rect header, Rect tabs, Rect body, Rect footer,
                        Rect grid, Rect detail, int columns) {
    public static final int MAX_W = 420, MAX_H = 260, MARGIN = 8;
    public static final int HEADER_H = 26, TABS_H = 14, FOOTER_H = 14, PAD = 6;
    public static final int TILE = 30, TILE_GAP = 4;

    public record Rect(int x, int y, int w, int h) {
        public int right() {
            return x + w;
        }

        public int bottom() {
            return y + h;
        }

        public boolean contains(Rect o) {
            return o.x >= x && o.y >= y && o.right() <= right() && o.bottom() <= bottom();
        }
    }

    public static HudLayout compute(int screenW, int screenH) {
        int w = Math.min(screenW - 2 * MARGIN, MAX_W);
        int h = Math.min(screenH - 2 * MARGIN, MAX_H);
        Rect panel = new Rect((screenW - w) / 2, (screenH - h) / 2, w, h);
        int ix = panel.x() + PAD, iw = w - 2 * PAD;
        Rect header = new Rect(ix, panel.y() + PAD, iw, HEADER_H);
        Rect tabs = new Rect(ix, header.bottom() + 2, iw, TABS_H);
        Rect footer = new Rect(ix, panel.bottom() - PAD - FOOTER_H, iw, FOOTER_H);
        int bodyY = tabs.bottom() + 4;
        Rect body = new Rect(ix, bodyY, iw, footer.y() - 2 - bodyY);

        // Grid takes ~42% of the width (at least 2 tiles), the detail card the rest
        int gridW = Math.max(2 * TILE + TILE_GAP, (int) (iw * 0.42));
        int columns = Math.max(2, (gridW + TILE_GAP) / (TILE + TILE_GAP));
        gridW = columns * TILE + (columns - 1) * TILE_GAP;
        Rect grid = new Rect(ix, body.y(), gridW, body.h());
        Rect detail = new Rect(grid.right() + PAD + 1, body.y(), body.right() - grid.right() - PAD - 1, body.h());
        return new HudLayout(panel, header, tabs, body, footer, grid, detail, columns);
    }

    /** Largest GUI scale Minecraft offers for this window (its 320x240 minimum). */
    public static int maxGuiScale(int windowW, int windowH) {
        int s = 1;
        while (windowW / (s + 1) >= 320 && windowH / (s + 1) >= 240) s++;
        return s;
    }
}
