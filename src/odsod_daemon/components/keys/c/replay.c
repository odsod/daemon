#include "state.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Test driver: feeds the in lines of a sequence file to the state machine and
 * prints its outputs as out lines. Timers fire on the next input, so a
 * sequence that waits for a timer puts another input after it.
 */

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
	{"BTN_LEFT", BTN_LEFT},
	{"BTN_RIGHT", BTN_RIGHT},
	{"REL_WHEEL", REL_WHEEL},
	{"REL_HWHEEL", REL_HWHEEL},
	{NULL, 0},
};

static int code_of(const char *name)
{
	for (int i = 0; key_names[i].name != NULL; i++) {
		if (strcmp(key_names[i].name, name) == 0)
			return key_names[i].code;
	}
	return -1;
}

static const char *name_of(int code)
{
	for (int i = 0; key_names[i].name != NULL; i++) {
		if (key_names[i].code == code)
			return key_names[i].name;
	}
	return "KEY_UNKNOWN";
}

static int value_of(const char *name)
{
	if (strcmp(name, "down") == 0)
		return 1;
	if (strcmp(name, "up") == 0)
		return 0;
	if (strcmp(name, "repeat") == 0)
		return 2;
	return -1;
}

static const char *value_name(int value)
{
	switch (value) {
	case 1:
		return "down";
	case 0:
		return "up";
	case 2:
		return "repeat";
	default:
		return "unknown";
	}
}

static void print_output(const struct ks_output *item)
{
	switch (item->kind) {
	case KS_OUT_KEY:
		printf("%ld out key %s %s\n", item->t_ms, name_of(item->code),
		       value_name(item->value));
		break;
	case KS_OUT_SOCK_START:
		printf("%ld out sock start %ld\n", item->t_ms, item->msg_ms);
		break;
	case KS_OUT_SOCK_STOP:
		printf("%ld out sock stop %ld\n", item->t_ms, item->msg_ms);
		break;
	case KS_OUT_SOCK_CANCEL:
		printf("%ld out sock cancel %ld\n", item->t_ms, item->msg_ms);
		break;
	case KS_OUT_SOCK_PASTED:
		printf("%ld out sock pasted\n", item->t_ms);
		break;
	case KS_OUT_SOCK_PASTE_FAILED:
		printf("%ld out sock paste-failed %s\n", item->t_ms,
		       item->reason == NULL ? "unknown" : item->reason);
		break;
	case KS_OUT_GRAB_RELEASE:
		printf("%ld out grab release\n", item->t_ms);
		break;
	}
}

static int fail(const char *path, long line_no, const char *text)
{
	fprintf(stderr, "%s:%ld: %s\n", path, line_no, text);
	return 2;
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s <file.seq>\n", argv[0]);
		return 2;
	}
	const char *path = argv[1];
	FILE *file = fopen(path, "r");
	if (file == NULL) {
		perror(path);
		return 2;
	}

	struct ks_state state;
	ks_init(&state);

	char *line = NULL;
	size_t cap = 0;
	long line_no = 0;
	int status = 0;
	while (getline(&line, &cap, file) != -1) {
		line_no++;
		char *newline = strchr(line, '\n');
		if (newline != NULL)
			*newline = '\0';
		char *comment = strchr(line, '#');
		if (comment != NULL)
			*comment = '\0';

		long ms = 0;
		char where[8] = {0};
		char kind[8] = {0};
		char arg1[64] = {0};
		char arg2[64] = {0};
		int fields = sscanf(line, "%ld %7s %7s %63s %63s", &ms, where,
				    kind, arg1, arg2);
		if (fields < 2)
			continue;
		if (ms < 0) {
			status = fail(path, line_no, "negative time");
			break;
		}
		if (strcmp(where, "out") == 0)
			continue;
		if (strcmp(where, "in") != 0) {
			status = fail(path, line_no, "expected in or out");
			break;
		}

		struct ks_input in = {.t_ms = ms, .kind = KS_IN_TICK,
				      .code = 0, .value = 0};
		if (strcmp(kind, "key") == 0 || strcmp(kind, "btn") == 0) {
			if (fields != 5) {
				status = fail(path, line_no, "bad key line");
				break;
			}
			in.code = code_of(arg1);
			in.value = value_of(arg2);
			if (in.code < 0 || in.value < 0) {
				status = fail(path, line_no, "bad code or value");
				break;
			}
			in.kind = strcmp(kind, "key") == 0 ? KS_IN_KEY
							   : KS_IN_BTN;
		} else if (strcmp(kind, "rel") == 0) {
			if (fields != 5) {
				status = fail(path, line_no, "bad rel line");
				break;
			}
			in.kind = KS_IN_REL;
			in.code = code_of(arg1);
			in.value = atoi(arg2);
			if (in.code < 0) {
				status = fail(path, line_no, "bad rel code");
				break;
			}
		} else if (strcmp(kind, "sock") == 0) {
			if (fields != 4) {
				status = fail(path, line_no, "bad sock line");
				break;
			}
			if (strcmp(arg1, "connect") == 0)
				in.kind = KS_IN_SOCK_CONNECT;
			else if (strcmp(arg1, "disconnect") == 0)
				in.kind = KS_IN_SOCK_DISCONNECT;
			else if (strcmp(arg1, "paste") == 0)
				in.kind = KS_IN_SOCK_PASTE;
			else {
				status = fail(path, line_no, "bad sock message");
				break;
			}
		} else {
			status = fail(path, line_no, "bad input kind");
			break;
		}

		struct ks_outputs out;
		ks_handle(&state, &in, &out);
		for (int i = 0; i < out.count; i++)
			print_output(&out.items[i]);
	}

	free(line);
	fclose(file);
	if (status != 0)
		return status;
	fflush(stdout);
	return 0;
}
