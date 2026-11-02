CFLAGS ?= -O2 -Wall -Wextra -Wno-unused-parameter
r1-primer-ui: r1-primer-ui.c ../r1ui/r1ui.h
	$(CC) $(CFLAGS) -o $@ $< $$(pkg-config --cflags --libs sdl3 pangocairo) -lm
