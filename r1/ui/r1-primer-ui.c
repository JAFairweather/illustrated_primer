// r1-primer-ui: Primer, window 24. The reMarkable notebook as Nell's Primer: hold the side button and ask
// (lib/r1-primer/primer), and the question is written into the notebook open on the tablet in your hand; the
// Primer's answer is told aloud while the tablet draws it. Your questions show on the right, the story as it was
// told on the left, the newest at the bottom; tap a part of the story to hear it again. "New" clears the page.
// Drag or the wheel scrolls. While the tablet writes, what it draws fills the screen, with the words being told
// passing through a strip along the bottom; a tap goes back to the conversation, and "Picture" returns.
// The data: lib/r1-primer/feed, which reads only while this window is on screen and lit.
// Build: make (in the r1-gui-build image; tools/r1-primer-ui/Makefile).
#include "../r1ui/r1ui.h"

#define FEED "/usr/local/lib/r1-primer/feed"
enum { A_NEW = 1, A_SAY, A_FULL };
enum { INK = 0x3a2f1e, GOLD = 0xd9b45a, WHITE = 0xffffff };

typedef struct { char k, *text; } Msg;

static char *buf, *stage = "";
static Msg msgs[64];
static int nmsg, busy;
static PangoFontDescription *F_MSG, *F_GLYPH, *F_CAP;
static int vis = 1;
static cairo_surface_t *pic;   // what the tablet is drawing now, while the engine works
static char picid[64];
static int full;   // the picture fills the screen
static char said[1024];   // the words being told, and since when (ms)
static Uint64 said_at;

// What r1ui doesn't do: tell the feed when the window goes off or comes on screen, so it can rest.
static bool SDLCALL watch(void *u, SDL_Event *e)
{
	switch (e->type) {
	case SDL_EVENT_WINDOW_OCCLUDED: case SDL_EVENT_WINDOW_EXPOSED: case SDL_EVENT_WINDOW_HIDDEN:
	case SDL_EVENT_WINDOW_SHOWN: case SDL_EVENT_WINDOW_MINIMIZED: case SDL_EVENT_WINDOW_RESTORED: {
		int v = !(SDL_GetWindowFlags(win) & (SDL_WINDOW_OCCLUDED | SDL_WINDOW_HIDDEN | SDL_WINDOW_MINIMIZED));
		if (v != vis)
			vis = v, cmd("view %d", v);
		break;
	}
	}
	return true;
}

static char *field(char **p)
{
	char *f = strsep(p, "\t");
	return f ? f : "";
}

static void picture(const char *path, const char *id)
{
	if (!strcmp(id, picid))
		return;
	cairo_surface_t *s = cairo_image_surface_create_from_png(path);
	if (cairo_surface_status(s) != CAIRO_STATUS_SUCCESS) {
		cairo_surface_destroy(s);
		return;
	}
	if (pic)
		cairo_surface_destroy(pic);
	else
		full = 1;   // the first of a question's pictures takes the screen
	pic = s;
	snprintf(picid, sizeof picid, "%s", id);
}

void app_frame(char *f)
{
	static int got;
	if (!got++)
		SDL_AddEventWatch(watch, NULL);
	free(buf);
	buf = f;
	int was = nmsg, seen = 0;
	nmsg = busy = 0, stage = "";
	for (char *ln = strtok(f, "\n"); ln; ln = strtok(NULL, "\n")) {
		char *p = ln, *k = field(&p);
		if (!strcmp(k, "busy"))
			busy = atoi(field(&p)), stage = field(&p);
		else if (!strcmp(k, "view")) {
			char *path = field(&p);
			picture(path, field(&p)), seen = 1;
		} else if (strchr("qse", *k) && !k[1] && nmsg < 64) {
			Msg *m = &msgs[nmsg++];
			m->k = *k, m->text = field(&p);
			for (char *c = m->text; *c; c++)
				if (*c == '\x1f')
					*c = '\n';
		}
	}
	if (!seen && pic)   // the question is answered: back to the conversation
		cairo_surface_destroy(pic), pic = NULL, picid[0] = 0, full = 0;
	if (nmsg && msgs[nmsg - 1].k == 's' && strncmp(said, msgs[nmsg - 1].text, sizeof said - 1)) {
		snprintf(said, sizeof said, "%s", msgs[nmsg - 1].text);
		said_at = SDL_GetTicks();
	}
	if (nmsg != was || busy)   // something new: the conversation's end
		scroll = 0;
}

// The picture over the whole screen, and along the bottom, the words being told: from mid-screen they pass left at
// about the pace they are spoken, and stop with their end in view.
static void fullscreen(void)
{
	double strip = H * 0.17, ih = H - strip;
	rgb(WHITE);
	cairo_paint(cr);
	double pw = cairo_image_surface_get_width(pic), ph = cairo_image_surface_get_height(pic);
	double k = fmin(W / pw, ih / ph);
	cairo_save(cr);
	cairo_translate(cr, (W - pw * k) / 2, (ih - ph * k) / 2);
	cairo_scale(cr, k, k);
	cairo_set_source_surface(cr, pic, 0, 0);
	cairo_paint(cr);
	cairo_restore(cr);
	box(0, ih, W, strip, 0, INK, 0, 0);
	const char *t = *said ? said : stage;
	char one[1024];
	snprintf(one, sizeof one, "%s", t);
	for (char *c = one; *c; c++)
		if (*c == '\n')
			*c = ' ';
	int d = DRAW;
	DRAW = 0;
	double tw, th = text(one, F_CAP, 0, 0, 0, 0, PANGO_ELLIPSIZE_NONE, 0, PANGO_ALIGN_LEFT, &tw);
	DRAW = d;
	double x = MARGIN, y = ih + (strip - th) / 2;
	if (*said && tw > W - 2 * MARGIN) {
		double secs = fmax(2, strlen(one) / 14.0), t0 = (SDL_GetTicks() - said_at) / 1000.0;
		double from = W / 2, to = W - MARGIN - tw;
		x = from + (to - from) * fmin(1, t0 / secs);
	}
	cairo_save(cr);
	cairo_rectangle(cr, 0, ih, W, strip);
	cairo_clip(cr);
	text(one, F_CAP, *said ? CREAM : GOLD, x, y, 0, PANGO_ELLIPSIZE_NONE, 0, PANGO_ALIGN_LEFT, NULL);
	cairo_restore(cr);
	hit(0, 0, W, H, A_FULL, 0);
}

// The conversation from y down; its height. A question on the right, the story on the left.
static double chat(double y)
{
	double y0 = y, bw = W * 0.82, pad = P(12);
	if (!nmsg && !busy) {
		double d = P(64), cy = (H + P(64)) / 2 - P(120);
		box((W - d) / 2, cy, d, d, d * 0.26, GOLD, 0, 0);
		CENTER("\U000f05da", F_GLYPH, INK, (W - d) / 2, cy + (d - P(30)) / 2, d);
		cy += d + P(18);
		cy += text("Hold the side button and ask.", F_BOLD, TEXT, P(20), cy, W - P(40), PANGO_ELLIPSIZE_NONE, 0,
			   PANGO_ALIGN_CENTER, NULL) + P(10);
		text("Your question is written into the notebook open on the tablet, and the Primer tells you the answer "
		     "as it draws it.", F_SMALL, GREY, P(30), cy, W - P(60), PANGO_ELLIPSIZE_NONE, 0, PANGO_ALIGN_CENTER, NULL);
		return 0;
	}
	for (int i = 0; i < nmsg; i++) {
		Msg *m = &msgs[i];
		int q = m->k == 'q';
		double tw, th;
		int d = DRAW;
		DRAW = 0;
		th = text(m->text, F_MSG, 0, 0, 0, bw - 2 * pad, PANGO_ELLIPSIZE_NONE, 0, PANGO_ALIGN_LEFT, &tw);
		DRAW = d;
		if (m->k == 's')
			tw = fmax(tw, P(34));   // room for the speaker
		double w = tw + 2 * pad, h = th + 2 * P(9) + (m->k == 's' ? P(16) : 0);
		double x = q ? W - MARGIN - w : MARGIN;
		if (i && (msgs[i - 1].k == 'q') != q)
			y += P(6);   // a turn: a little more room
		unsigned fill = q ? GOLD : m->k == 'e' ? FAILBG : CARD;
		if (m->k == 's' && pressing(x, y, w, h))
			fill = lit(fill);
		box(x, y, w, h, P(18), fill, 0, 0);
		text(m->text, F_MSG, q ? INK : m->k == 'e' ? RED : TEXT, x + pad, y + P(9), bw - 2 * pad,
		     PANGO_ELLIPSIZE_NONE, 0, PANGO_ALIGN_LEFT, NULL);
		if (m->k == 's') {
			LINE1("\U000f057e", F_SUB, GREY, x + w - pad - P(14), y + h - P(22), 0, NULL);
			hit(x, y, w, h, A_SAY, i);
		}
		y += h + P(8);
	}
	if (busy) {   // at work: three dots, one lit at a time
		double w = P(74), h = P(40);
		box(MARGIN, y, w, h, P(18), CARD, 0, 0);
		int on = SDL_GetTicks() / 350 % 3;
		for (int k = 0; k < 3; k++)
			disc(MARGIN + P(15) + k * P(16), y + h / 2 - P(5), P(10), k == on ? GOLD : DIMG);
		y += h + P(8);
	}
	return y - y0;
}

void app_render(void)
{
	if (!F_MSG)
		F_MSG = font(15, PANGO_WEIGHT_NORMAL), F_GLYPH = font(30, PANGO_WEIGHT_NORMAL), F_CAP = font(26, PANGO_WEIGHT_BOLD);
	// Drawn and not hidden by the window's own flags: on screen, though the watch saw no event say so.
	if (!vis && !(SDL_GetWindowFlags(win) & (SDL_WINDOW_OCCLUDED | SDL_WINDOW_HIDDEN | SDL_WINDOW_MINIMIZED)))
		vis = 1, cmd("view 1");
	if (busy && pic && full) {
		fullscreen();
		return;
	}
	rgb(BG);
	cairo_paint(cr);

	// The conversation under the bar, kept to the bottom.
	double top = P(66), avail = H - top - P(8);
	int d = DRAW;
	DRAW = 0;
	double h = chat(0);
	DRAW = d;
	double over = fmax(0, h - avail);
	if (scroll < 0 || scroll > over)
		scroll = fmax(0, fmin(scroll, over)), vel = 0;
	cairo_save(cr);
	cairo_rectangle(cr, 0, top - P(4), W, H - top + P(4));
	cairo_clip(cr);
	chat(h ? top + avail - h + scroll : top);
	cairo_restore(cr);

	// The bar: the title, what it's doing, and New.
	double bw = P(68), bh = P(34), bx = W - P(10) - P(8) - bw;
	char sub[80];
	snprintf(sub, sizeof sub, "%s…", stage);
	headbar("", NULL, 0, 0);
	LINE1("Primer", F_BOLD, TEXT, P(28), P(14), bx - P(36), NULL);
	LINE1(busy && *stage ? sub : "Ask your notebook", F_SUB, busy ? GOLD : GREY, P(28), P(35), bx - P(36), NULL);
	if (!busy)
		button(bx, P(8) + (P(50) - bh) / 2, bw, bh, "New", CARD, TEXT, A_NEW, 0);
	else if (pic)
		button(bx - P(16), P(8) + (P(50) - bh) / 2, bw + P(16), bh, "Picture", GOLD, INK, A_FULL, 1);
}

void app_tap(int act, int arg)
{
	if (act == A_NEW)
		cmd("new"), scroll = 0;
	else if (act == A_SAY)
		cmd("say %d", arg);
	else if (act == A_FULL)
		full = arg;
}

void app_key(SDL_Keycode k, SDL_Keymod mod) {}

void app_text(const char *s) {}

// The dots, and the words passing along the strip.
int app_anim(void)
{
	return busy && pic && full ? 50 : busy ? 120 : 0;
}

int main(int argc, char **argv)
{
	return r1ui_run("r1-primer", getenv("R1_PRIMER_FEED") ? getenv("R1_PRIMER_FEED") : FEED, NULL);
}
