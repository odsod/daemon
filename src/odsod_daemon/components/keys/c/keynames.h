#ifndef ODSOD_DAEMON_KEYS_KEYNAMES_H
#define ODSOD_DAEMON_KEYS_KEYNAMES_H

/* Linux key and pointer names for sequence files and the record mode. */

#include <linux/input.h>
#include <stddef.h>
#include <string.h>

struct key_name {
	const char *name;
	int code;
};

static const struct key_name key_names[] = {
	{"KEY_ESC", KEY_ESC},
	{"KEY_CAPSLOCK", KEY_CAPSLOCK},
	{"KEY_LEFTCTRL", KEY_LEFTCTRL},
	{"KEY_RIGHTCTRL", KEY_RIGHTCTRL},
	{"KEY_LEFTSHIFT", KEY_LEFTSHIFT},
	{"KEY_RIGHTSHIFT", KEY_RIGHTSHIFT},
	{"KEY_LEFTALT", KEY_LEFTALT},
	{"KEY_RIGHTALT", KEY_RIGHTALT},
	{"KEY_LEFTMETA", KEY_LEFTMETA},
	{"KEY_RIGHTMETA", KEY_RIGHTMETA},
	{"KEY_SPACE", KEY_SPACE},
	{"KEY_TAB", KEY_TAB},
	{"KEY_INSERT", KEY_INSERT},
	{"KEY_1", KEY_1},
	{"KEY_A", KEY_A},
	{"KEY_B", KEY_B},
	{"KEY_C", KEY_C},
	{"KEY_D", KEY_D},
	{"KEY_E", KEY_E},
	{"KEY_F", KEY_F},
	{"KEY_Q", KEY_Q},
	{"KEY_W", KEY_W},
	{"BTN_LEFT", BTN_LEFT},
	{"BTN_RIGHT", BTN_RIGHT},
	{"REL_WHEEL", REL_WHEEL},
	{"REL_HWHEEL", REL_HWHEEL},
	{NULL, 0},
};

static inline int key_code_of(const char *name)
{
	for (int i = 0; key_names[i].name != NULL; i++) {
		if (strcmp(key_names[i].name, name) == 0)
			return key_names[i].code;
	}
	return -1;
}

static inline const char *key_name_of(int code)
{
	for (int i = 0; key_names[i].name != NULL; i++) {
		if (key_names[i].code == code)
			return key_names[i].name;
	}
	return NULL;
}

#endif
