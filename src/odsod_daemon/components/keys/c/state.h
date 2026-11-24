#ifndef ODSOD_DAEMON_KEYS_STATE_H
#define ODSOD_DAEMON_KEYS_STATE_H

/*
 * The pure keys state machine. No I/O, no clock reads. Each input carries
 * its own monotonic time in milliseconds; timers are inputs too.
 */

#include <linux/input.h>

#define KS_TAP_MS 350
#define KS_SPACE_HOLD_MS 150
#define KS_ALT_MS 350
#define KS_PASTE_WAIT_MS 1500
#define KS_ESCAPE_MS 3000
#define KS_MAX_OUTPUTS 128
#define KS_MAX_QUEUE 16

enum ks_input_kind {
	KS_IN_KEY,
	KS_IN_BTN,
	KS_IN_REL,
	KS_IN_SOCK_CONNECT,
	KS_IN_SOCK_DISCONNECT,
	KS_IN_SOCK_PASTE,
	KS_IN_TICK,
};

enum ks_output_kind {
	KS_OUT_KEY,
	KS_OUT_SOCK_START,
	KS_OUT_SOCK_STOP,
	KS_OUT_SOCK_CANCEL,
	KS_OUT_SOCK_PASTED,
	KS_OUT_SOCK_PASTE_FAILED,
	KS_OUT_GRAB_RELEASE,
};

struct ks_input {
	long t_ms;
	enum ks_input_kind kind;
	int code;
	int value;
};

struct ks_output {
	enum ks_output_kind kind;
	long t_ms;
	int code;
	int value;
	long msg_ms;
	const char *reason;
};

struct ks_outputs {
	struct ks_output items[KS_MAX_OUTPUTS];
	int count;
};

enum ks_ctrl_state { KS_CTRL_IDLE, KS_CTRL_PENDING };
enum ks_space_state { KS_SPACE_IDLE, KS_SPACE_PENDING, KS_SPACE_HELD };
enum ks_alt_state {
	KS_ALT_IDLE,
	KS_ALT_PENDING,
	KS_ALT_DICTATE,
	KS_ALT_SWALLOW,
	KS_ALT_CHORD,
};

struct ks_queued {
	int code;
	int value;
};

struct ks_ctrl {
	enum ks_ctrl_state state;
	long pressed_ms;
	int interrupted;
};

struct ks_state {
	int client;
	int exit;

	unsigned char keys_down[KEY_MAX + 1];
	unsigned char out_down[KEY_MAX + 1];

	struct ks_ctrl capslock, leftctrl;

	struct {
		enum ks_space_state state;
		long pressed_ms;
		int queued_count;
		struct ks_queued queue[KS_MAX_QUEUE];
	} space;

	struct {
		enum ks_alt_state state;
		long pressed_ms;
	} alt;
	long alt_deadline;

	long chord_deadline;

	int paste_pending;
	long paste_deadline;
};

void ks_init(struct ks_state *state);
void ks_handle(struct ks_state *state, const struct ks_input *in,
	       struct ks_outputs *out);
int ks_deadline(const struct ks_state *state, long *t_ms);
void ks_release_all(struct ks_state *state, long t_ms, struct ks_outputs *out);
void ks_device_lost(struct ks_state *state, long t_ms, struct ks_outputs *out);

#endif
