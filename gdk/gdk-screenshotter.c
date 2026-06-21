#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <sys/wait.h>
#include <sys/uio.h>
#include <unistd.h>
#include <dlfcn.h>

#include <gdk-pixbuf-2.0/gdk-pixbuf/gdk-pixbuf.h>

#include <X11/Xlib.h>

#include <xcb/xcb.h>
#include <xcb/xcbext.h>

#define TEMPFILE "/tmp/upwork.png"

int grim() {
    // override environment
    int pid = fork();
    if(pid == 0) {
        // child
        printf("in child\n");
        char *wld = getenv("WAYLAND_DISPLAY_REAL");
        printf("wl disp: %s\n", wld);
        if(wld) {
            setenv("WAYLAND_DISPLAY", wld, 1);
        } else {
            printf("WARNING: no WAYLAND_DISPLAY_REAL\n");
        }
        execlp("grim", "-c", TEMPFILE, NULL);
    } else {
        printf("in parent: %d\n", pid);
        int retval = -1;
        waitpid(pid, &retval, 0);
        return retval;
    }
}

extern GdkPixbuf* gdk_pixbuf_get_from_window(void *window, gint src_x, gint src_y, gint width, gint height) {
    printf("Before executing grim\n");
    int res = grim();
    if(res != 0) {
        printf("grim call failed: %d\n", res);
        return NULL;
    }
    printf("Grim success\n");
    GError *err = NULL;
    GdkPixbuf *pixbuf = gdk_pixbuf_new_from_file_at_scale(TEMPFILE, width-src_x, height-src_y, FALSE, &err);
    // clean up grabage
    //unlink(TEMPFILE);
    // For now we do not clean it up since our py part takes timestamp from it
    if(err || !pixbuf) {
        printf("pixbuf failure: %s\n", err->message);
        g_error_free(err);
        return NULL;
    }
    printf("Pixbuf success\n");
    return pixbuf;
}

int wanna_break_dimensions = 0;

gboolean (*real_gdk_pixbuf_save_to_callback)(GdkPixbuf*, GdkPixbufSaveFunc, gpointer, const char*, GError**, ...);
extern gboolean gdk_pixbuf_save_to_callback(GdkPixbuf* pb, GdkPixbufSaveFunc fn, gpointer dat, const char* typ, GError** err, ...) {
    if(!real_gdk_pixbuf_save_to_callback) real_gdk_pixbuf_save_to_callback = dlsym(RTLD_NEXT, "gdk_pixbuf_save_to_callback");

    printf("gdk_pixbuf_save_to_callback args: ");
    va_list list;
    va_start(list, err);
    while(1) {
        char *arg = va_arg(list, char*);
        if(!arg) {
            break;
        }
        printf("%s ", (char*)arg);
    }
    va_end(list);
    printf("\n");

    wanna_break_dimensions = 1;

    gboolean res = real_gdk_pixbuf_save_to_callback(pb, fn, dat, typ, err, NULL); // FIXME
    printf("gdk_pixbuf_save_to_callback(%p, %p, %p, %s, %p, ...) => %d\n", pb, fn, dat, typ, err, res);
    return res;
}

Status (*real_XGetWindowAttributes)();
extern Status XGetWindowAttributes(Display *display, Window w, XWindowAttributes *attrs) {
    if(!real_XGetWindowAttributes) {
        real_XGetWindowAttributes = dlsym(RTLD_NEXT, "XGetWindowAttributes");
    }

    printf("XGetWindowAttrs for 0x%lX\n", w);
    Status res = real_XGetWindowAttributes(display, w, attrs);
    if(!res) {
        printf("Returned error! 0x%X\n", res);
        attrs->x = 0;
        attrs->y = 0;
        attrs->width = 622;
        attrs->height = 450;
        return 1;
    }
    printf("Coords: %dx%d,%dx%d\n", attrs->x, attrs->y, attrs->width, attrs->height);
    if(wanna_break_dimensions) {
        printf("Will break dimensions this time! :evil: Size is zero now! Ha ha ha!\n");
        // For Upwork 5.8.0.33:
        // When running on Xorg, Upwork first takes snapshot using its Native code.
        // But then it tries to take snapshot again using Electron methods.
        // If the latter succeeds then it is used — they name it "enhancing snapshot".
        // Native code uses gdk_pixbuf_get_from_window() which we override.
        // Electron uses something else - I didn't investigate it enough.
        // But first Electron gets screen dimensions (i.e. root window size).
        // If we spoil these values by setting both width and height to be <= 0
        // then Upwork's JS code will return the snapshot it already has,
        // i.e. the one it took with the native code.
        wanna_break_dimensions = 0;
        attrs->width = 0;
        attrs->height = 0;
    }
    return res;
}

int get_active_window_name(char *buf, int bufsize) {
    FILE *fp = popen("swaymsg -t get_tree | jq -r '.. | (.nodes? // empty)[] | select(.focused) | .name'", "r");
    if(!fp) {
        printf("Could not popen\n");
        return 0;
    }
    if(!fgets(buf, bufsize, fp)) {
        printf("Could not read popen\n");
        pclose(fp);
        return 0;
    }
    pclose(fp);
    return strlen(buf)+1;
}
int get_active_window_pid() {
    FILE *fp = popen("swaymsg -t get_tree | jq -r '.. | (.nodes? // empty)[] | select(.focused) | .pid'", "r");
    if(!fp) {
        printf("Could not popen\n");
        return 0;
    }
    char buf[128];
    if(!fgets(buf, sizeof(buf), fp)) {
        printf("Could not read popen\n");
        pclose(fp);
        return 0;
    }
    return atoi(buf);
}

int (*real_XGetWindowProperty)();
extern int XGetWindowProperty(Display *display, Window w, Atom property, long offset, long length, Bool delete, Atom req_type, Atom *actual_type, int *actual_fmt, unsigned long *nitems, unsigned long *bytes_after, unsigned char **prop) {
    // property:
    // x+35 = _NET_ACTIVE_WINDOW // nitems should be 1
    // x+36 = _NET_WM_PID // nitems should be 1
    // x+37 = _NET_WM_NAME
    // x+38 = _NAME

    if(!real_XGetWindowProperty) {
        real_XGetWindowProperty = dlsym(RTLD_NEXT, "XGetWindowProperty");
    }

    char *propname = XGetAtomName(display, property);
    printf("Requested property: %s\n", propname);
    if(strcmp(propname, "_NET_WM_PID") == 0) {
        *actual_type = 0;
        *actual_fmt = 32;
        *nitems = 1;
        *bytes_after = 0;
        int *val = malloc(sizeof(int));
        *val = get_active_window_pid();
        printf("Will return pid: %d\n", *val);
        *prop = (char*)val;
    }
    if(!strstr(propname, "NAME")) {
        return real_XGetWindowProperty(display, w, property, offset, length, delete, req_type, actual_type, actual_fmt, nitems, bytes_after, prop);
    }
    XFree(propname);

    *actual_type = 0; // seemingly unused by upw
    *actual_fmt = 8; // list of bytes
    *bytes_after = 0;

    char buf[2048];
    int len = get_active_window_name(buf, sizeof(buf));
    if(!len) {
        *nitems = 0;
        return -1;
    }
    *nitems = len;
    *prop = malloc(len);
    memcpy(*prop, buf, len);
    return Success;
}


// Shared verbose-logging gate (UPWORK_NOTIF_DEBUG=1). Used by both the
// input-stats instrumentation (ISLOG) and the notification tracing (XLOG).
static int shim_debug(void) {
    static int v = -1;
    if (v < 0) { const char *e = getenv("UPWORK_NOTIF_DEBUG"); v = e && *e && *e != '0'; }
    return v;
}

// ---------------------------------------------------------------------------
// Notification window tweaks via xcb_send_request().
//
// Window operations come through libxcb's raw xcb_send_request() (not Xlib), so
// we intercept there: reposition notification windows (shift down by an offset)
// and optionally adjust their _NET_WM_WINDOW_TYPE. Behavioral background lives in
// NOTES.local.md (uncommitted), not here.
//
// Options (see Makefile / env):
//   -DUPWORK_MOVE_NOTIFICATIONS        enable repositioning (default ON)
//   -DUPWORK_NOTIF_Y_OFFSET_DEFAULT=N  default downward shift in px (default 40)
//   UPWORK_NOTIF_Y_OFFSET=N            override the offset at run time
//   UPWORK_FIX_NOTIF_FOCUS=1           enable the focus fix (default off)
//   UPWORK_NOTIF_DEBUG=1               verbose per-request tracing
//
// xcb_send_request(conn, flags, vector, req): the caller's request bytes start at
// vector[0] (xcb reserves vector[-2]/[-1]); valid entries are vector[0..count-1].
// Byte 0 of the first entry is the X11 major opcode (req->opcode is unreliable for
// hand-built requests, so we read the wire).
// ---------------------------------------------------------------------------
#ifdef UPWORK_MOVE_NOTIFICATIONS

#ifndef UPWORK_NOTIF_Y_OFFSET_DEFAULT
#define UPWORK_NOTIF_Y_OFFSET_DEFAULT 40
#endif

static double log_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
// XLOG: verbose, only when UPWORK_NOTIF_DEBUG is set (shim_debug()).  XLOGA:
// always logged (used for the rare reposition action -- one line per moved notif).
#define XLOG(...)  do { if (shim_debug()) XLOGA(__VA_ARGS__); } while(0)
#define XLOGA(...) do { fprintf(stderr, "XCBLOG %.1f: ", log_ms()); \
                       fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); fflush(stderr); } while(0)

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static int16_t  rds16(const uint8_t *p) { return (int16_t)rd16(p); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)(p[0] | (p[1]<<8) | (p[2]<<16) | ((uint32_t)p[3]<<24)); }
static void wr16(uint8_t *p, uint16_t v) { p[0]=v&0xff; p[1]=(v>>8)&0xff; }
static void wr32(uint8_t *p, uint32_t v) { p[0]=v&0xff; p[1]=(v>>8)&0xff; p[2]=(v>>16)&0xff; p[3]=(v>>24)&0xff; }

// --- Notification repositioning -------------------------------------------
// Notification windows pin themselves to the top-right of the FULL screen
// (ConfigureWindow x≈screen_w-width, y≈10), covering a top bar. We shift their Y
// down by a fixed offset in the ConfigureWindow wire request. _NET_WORKAREA is
// not honored by the compositor/app for these, so we do it directly.
//
// Discriminate purely by geometry: a "notification" Configure lands in the
// top-right corner (right edge near the screen's right edge). Width isn't carried
// in ConfigureWindow, so we cache each window's width at CreateWindow time to
// compute its right edge. The main window is sway-managed and never corner-pinned,
// so the corner test excludes it.
#define WID_HASH 257
#define NOTIF_RIGHT_SLACK 64        // slack for the window's small right margin
#define NOTIF_RECOMPUTE_MS 100      // post-create window for the one-shot Y correction

// --- Focus-steal fix: EWMH atom resolution (see the ChangeProperty case) ---
// X11 atom IDs are server-assigned, not constants, so we resolve them by name.
// We do this via Xlib XInternAtom on our OWN short-lived Display connection --
// NOT Upwork's xcb connection -- to avoid reentrancy/deadlock (we're called from
// inside xcb_send_request; blocking for a reply on that same socket is unsafe).
// Atoms are global to the X server, so IDs resolved on our Display are valid for
// Upwork's connection too. Resolved once, lazily; 0 means "not resolved yet".
static uint32_t atom_wm_type, atom_wm_type_normal, atom_wm_type_notification;
static void resolve_focus_atoms(void) {
    static int tried = 0;
    if (tried) return;
    tried = 1;
    Display *d = XOpenDisplay(NULL);
    if (!d) return;
    atom_wm_type              = XInternAtom(d, "_NET_WM_WINDOW_TYPE", True);
    atom_wm_type_normal       = XInternAtom(d, "_NET_WM_WINDOW_TYPE_NORMAL", True);
    atom_wm_type_notification = XInternAtom(d, "_NET_WM_WINDOW_TYPE_NOTIFICATION", False);
    XCloseDisplay(d);
}

// Opt-in: rewrite Upwork's notification windows' _NET_WM_WINDOW_TYPE from NORMAL
// to NOTIFICATION so sway/wlroots doesn't grant them keyboard focus on map (they
// are override-redirect; wlroots' override_redirect_wants_focus() returns true
// for NORMAL but false for NOTIFICATION). Off by default.
static int focus_fix_enabled(void) {
    static int v = -1;
    if (v < 0) {
        const char *e = getenv("UPWORK_FIX_NOTIF_FOCUS");
        v = e && *e && *e != '0';
    }
    return v;
}

// Per-window state. Besides the width (needed to compute the right edge), we
// track when the window was created, the last *intended* (pre-offset) Y we
// accepted, and whether we have already corrected the one bad stacking
// recompute. Upwork places a stacked notification correctly, then ~14ms later
// recomputes its Y from a sibling's (shifted) position read back via
// GetWindowAttributes -- producing an overlap. Rather than drop that request
// (which would desync xcb's sequence counter), we overwrite its Y with the
// last good value so the window stays put. We do this once, only within
// NOTIF_RECOMPUTE_MS of creation and after the first placement. Later moves
// (the close-triggered animation, seconds later) pass through and update last_y.
struct wid_w {
    uint32_t wid, w;
    double   created_ms;   // CreateWindow time
    int      placed;       // seen the first corner placement?
    int      last_y;       // last intended (pre-offset) Y we accepted
    int      corrected;    // already overwrote the one bad recompute?
};
static struct wid_w wid_width[WID_HASH];   // tiny direct-mapped cache by wid
static struct wid_w *wid_slot(uint32_t wid) { return &wid_width[wid % WID_HASH]; }
static void wid_remember_width(uint32_t wid, uint32_t w) {
    *wid_slot(wid) = (struct wid_w){ .wid = wid, .w = w, .created_ms = log_ms() };
}

static int notif_y_offset(void) {
    static int cached = -1;
    if (cached < 0) {
        const char *e = getenv("UPWORK_NOTIF_Y_OFFSET");
        cached = e ? atoi(e) : UPWORK_NOTIF_Y_OFFSET_DEFAULT;
        if (cached < 0) cached = 0;
    }
    return cached;
}

// Screen width, captured once from the xcb connection's setup.
static uint16_t screen_width(xcb_connection_t *c) {
    static uint16_t w = 0;
    if (!w && c) {
        const xcb_setup_t *s = xcb_get_setup(c);
        if (s) {
            xcb_screen_iterator_t it = xcb_setup_roots_iterator(s);
            if (it.data) w = it.data->width_in_pixels;
        }
    }
    return w;
}

// Locate the request payload. Per xcb: the `vector` pointer passed to
// xcb_send_request points at the CALLER's data (xcb reserves vector[-2],
// vector[-1] for itself). So request bytes start at vector[0]; valid indices
// are [0 .. count-1]. The first nonempty entry begins with the X11 request
// header (byte 0 = major opcode). Bounded by count so we never over-read.
static const uint8_t *xcb_req_payload(struct iovec *vector,
                                      const xcb_protocol_request_t *req,
                                      size_t *out_len) {
    *out_len = 0;
    if (!vector || !req) return NULL;
    for (size_t i = 0; i < req->count; i++) {
        if (vector[i].iov_len > 0 && vector[i].iov_base) {
            *out_len = vector[i].iov_len;
            return (const uint8_t *)vector[i].iov_base;
        }
    }
    return NULL;
}

unsigned int (*real_xcb_send_request)(xcb_connection_t*, int, struct iovec*,
                                      const xcb_protocol_request_t*);
extern unsigned int xcb_send_request(xcb_connection_t *c, int flags,
                                     struct iovec *vector,
                                     const xcb_protocol_request_t *req) {
    if (!real_xcb_send_request)
        real_xcb_send_request = dlsym(RTLD_NEXT, "xcb_send_request");

    // Identify the request by its X11 wire opcode (payload byte 0).
    {
        size_t len = 0;
        const uint8_t *p = xcb_req_payload(vector, req, &len);
        uint8_t op = (p && len >= 1) ? p[0] : 0;
        switch (op) {
        case 1:  // CreateWindow: opcode, depth, len(2), wid(4), parent(4),
                 // x(2) y(2) w(2) h(2) border(2) class(2) visual(4) mask(4) ...
            if (p && len >= 28) {
                uint32_t wid = rd32(p+4), w = rd16(p+16);
                wid_remember_width(wid, w);
                XLOG("CreateWindow wid=0x%X parent=0x%X pos=%d,%d size=%ux%u valuemask=0x%X",
                     wid, rd32(p+8), rds16(p+12), rds16(p+14),
                     (unsigned)w, rd16(p+18), rd32(p+24));
            }
            break;
        case 12: // ConfigureWindow: opcode, unused, len(2), window(4),
                 // value-mask(2), unused(2), value-list...
            if (p && len >= 12) {
                uint32_t wid = rd32(p+4);
                uint16_t mask = rd16(p+8);
                // value-list entries are 4 bytes each, in ascending mask-bit order.
                // X=0x1, Y=0x2, W=0x4, H=0x8, BW=0x10, sibling=0x20, stack=0x40
                uint8_t *vl = (uint8_t*)(p + 12);   // mutable: caller's send buffer
                int x=0, y=0, haveX=0, haveY=0, yoff=-1, off=0;
                if (mask & 0x1) { x = rds16(vl+off); haveX=1; off+=4; }
                if (mask & 0x2) { y = rds16(vl+off); haveY=1; yoff=off; off+=4; }

                // Reposition iff this Configure pins the window to the screen's
                // right edge (x + width >= screen_w - slack). This catches both
                // the 360px and 444px notifications at any height (so stacked
                // notifications all shift), while excluding the mid-screen main
                // window and the off-screen intermediate animation frames -- both
                // of which sit well left of the right edge.
                struct wid_w *st = wid_slot(wid);
                uint32_t ww = (st->wid == wid) ? st->w : 0;
                uint16_t sw = screen_width(c);
                int is_notif = haveX && haveY && ww && sw &&
                               (x + (int)ww >= (int)sw - NOTIF_RIGHT_SLACK);
                if (is_notif && (size_t)(12 + yoff + 2) <= len) {
                    int iy = y;   // intended (pre-offset) Y to use

                    // Detect the bad stacking recompute: the first reposition
                    // that arrives shortly after creation, after we've already
                    // placed the window, asking to move it. Upwork derived it
                    // from a sibling's shifted position -> overlap. Pin it to the
                    // last good Y instead (once).
                    int soon = (log_ms() - st->created_ms) <= NOTIF_RECOMPUTE_MS;
                    if (st->placed && !st->corrected && soon && y != st->last_y) {
                        iy = st->last_y;
                        st->corrected = 1;
                        XLOG("ConfigureWindow window=0x%X NOTIF recompute y=%d -> pinned %d",
                             wid, y, iy);
                    } else {
                        st->placed = 1;
                        st->last_y = y;
                    }

                    int ny = iy + notif_y_offset();
                    wr16(vl + yoff, (uint16_t)(int16_t)ny);  // patch Y in place
                    XLOGA("notification 0x%X y=%d -> %d", wid, y, ny);
                }
            }
            break;
        case 18: // ChangeProperty: opcode, mode(1), len(2), window(4),
                 // property-atom(4), type-atom(4)... The atom DATA lives in a
                 // separate iovec (vector[1]), not contiguous with this header.
            //
            // FOCUS-STEAL FIX (opt-in: UPWORK_FIX_NOTIF_FOCUS): Upwork sets
            // _NET_WM_WINDOW_TYPE = _NORMAL on its override-redirect notification
            // windows. wlroots' override_redirect_wants_focus() returns true for
            // NORMAL (not in its no-focus needle list), so sway grants the
            // notification keyboard focus on map -> steals focus. Rewriting the
            // type to _NOTIFICATION (which IS in that list) makes sway leave focus
            // alone. We patch the atom in the caller's vector[1] buffer pre-send.
            if (focus_fix_enabled() && p && len >= 12) {
                resolve_focus_atoms();
                if (atom_wm_type && rd32(p+8) == atom_wm_type &&
                    req->count > 1 && vector[1].iov_len >= 4 && vector[1].iov_base) {
                    uint8_t *d = (uint8_t*)vector[1].iov_base;
                    if (atom_wm_type_normal && rd32(d) == atom_wm_type_normal &&
                        atom_wm_type_notification) {
                        wr32(d, atom_wm_type_notification);
                        XLOG("rewrote _NET_WM_WINDOW_TYPE NORMAL->NOTIFICATION win=0x%X",
                             rd32(p+4));
                    }
                }
            }
            break;
        default:
            break;
        }
    }

    return real_xcb_send_request(c, flags, vector, req);
}

#endif // UPWORK_MOVE_NOTIFICATIONS

#ifdef TEST
int main() {
    GdkPixbuf *res = gdk_pixbuf_get_from_window(NULL, 0, 0, 1024, 1024);
    printf("res: %p\n", res);
    gboolean success = gdk_pixbuf_save(res, "/tmp/upwork-out.jpg", "jpeg", NULL, NULL);
    printf("Pixbuf save: %d\n", success);
}
#endif
