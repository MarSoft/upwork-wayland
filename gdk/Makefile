PKGS = gdk-pixbuf-2.0 x11 xcb
CFLAGS = $(shell pkg-config $(PKGS) --cflags)
LDFLAGS = $(shell pkg-config $(PKGS) --libs)

# Move Upwork's top-right notification windows down so they don't cover a top
# bar/panel. Set MOVE_NOTIFICATIONS=0 to disable, or change the default offset:
#   make NOTIF_Y_OFFSET=64
# At run time, UPWORK_NOTIF_Y_OFFSET=N overrides the offset without recompiling.
MOVE_NOTIFICATIONS ?= 1
NOTIF_Y_OFFSET ?= 40
ifeq ($(MOVE_NOTIFICATIONS),1)
FEATUREFLAGS = -DUPWORK_MOVE_NOTIFICATIONS -DUPWORK_NOTIF_Y_OFFSET_DEFAULT=$(NOTIF_Y_OFFSET)
endif

MYFLAGS = -fPIC -ldl -O2 -std=gnu17 $(FEATUREFLAGS)

all: gdk-screenshotter.so

clean:
	rm *.o *.so

%.so: %.o
	gcc -shared $(MYFLAGS) $(LDFLAGS) $< -o $@

%.o: %.c
	gcc -c $(MYFLAGS) $(CFLAGS) $< -o $@

test: gdk-screenshotter.c
	gcc -DTEST -g $(CFLAGS) $(LDFLAGS) $< -o $@
