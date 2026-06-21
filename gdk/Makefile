PKGS = gdk-pixbuf-2.0 x11 xscrnsaver
CFLAGS = $(shell pkg-config $(PKGS) --cflags)
LDFLAGS = $(shell pkg-config $(PKGS) --libs)
MYFLAGS = -fPIC -ldl -O2 -std=gnu17

all: gdk-screenshotter.so

clean:
	rm *.o *.so

%.so: %.o
	gcc -shared $(MYFLAGS) $(LDFLAGS) $< -o $@

%.o: %.c
	gcc -c $(MYFLAGS) $(CFLAGS) $< -o $@

test: gdk-screenshotter.c
	gcc -DTEST -g $(CFLAGS) $(LDFLAGS) $< -o $@
