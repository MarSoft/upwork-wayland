CFLAGS = $(shell pkg-config gdk-pixbuf-2.0 x11 --cflags)
LDFLAGS = $(shell pkg-config gdk-pixbuf-2.0 x11 --libs)
MYFLAGS = -fPIC -ldl -O2

all: gdk-screenshotter.so

clean:
	rm *.o *.so

%.so: %.o
	gcc -shared $(MYFLAGS) $(LDFLAGS) $< -o $@

%.o: %.c
	gcc -c $(MYFLAGS) $(CFLAGS) $< -o $@

test: gdk-screenshotter.c
	gcc -DTEST -g $(CFLAGS) $(LDFLAGS) $< -o $@
