#include "state.h"

#include <string.h>

/*
 * The keys state machine. Today's remaps come from keys/odsod-keys.c in the
 * machine repo. The Left Alt machine, the pointer handling, the escape chord
 * and the paste wait come from ADR-0007.
 *
 * No I/O and no clock reads: each input carries its monotonic time in ms.
 */

static void out_key(struct ks_state *state, struct ks_outputs *out, long t_ms,
		    int code, int value)
{
	if (out->count >= KS_MAX_OUTPUTS)
		return;
	struct ks_output *item = &out->items[out->count++];
	item->kind = KS_OUT_KEY;
	item->t_ms = t_ms;
	item->code = code;
	item->value = value;
	item->msg_ms = 0;
	item->reason = NULL;

	if (code < 0 || code > KEY_MAX)
		return;
	state->out_down[code] = value == 0 ? 0 : 1;
}

static void out_sock(struct ks_outputs *out, enum ks_output_kind kind,
		     long t_ms, long msg_ms, const char *reason)
{
	if (out->count >= KS_MAX_OUTPUTS)
		return;
	struct ks_output *item = &out->items[out->count++];
	item->kind = kind;
	item->t_ms = t_ms;
	item->code = 0;
	item->value = 0;
	item->msg_ms = msg_ms;
	item->reason = reason;
}

static void emit_meta_chord(struct ks_state *state, struct ks_outputs *out,
			    long t_ms, int code, int value)
{
	if (value == 1) {
		out_key(state, out, t_ms, KEY_LEFTMETA, 1);
		out_key(state, out, t_ms, code, 1);
	} else if (value == 0) {
		out_key(state, out, t_ms, code, 0);
		out_key(state, out, t_ms, KEY_LEFTMETA, 0);
	} else if (value == 2) {
		out_key(state, out, t_ms, code, 2);
	}
}

static int is_modifier(int code)
{
	switch (code) {
	case KEY_CAPSLOCK:
	case KEY_LEFTCTRL:
	case KEY_RIGHTCTRL:
	case KEY_LEFTSHIFT:
	case KEY_RIGHTSHIFT:
	case KEY_LEFTALT:
	case KEY_RIGHTALT:
	case KEY_LEFTMETA:
	case KEY_RIGHTMETA:
		return 1;
	default:
		return 0;
	}
}

static int other_key_held(const struct ks_state *state, int except)
{
	for (int code = 0; code <= KEY_MAX; code++) {
		if (code == except)
			continue;
		if (state->keys_down[code])
			return 1;
	}
	return 0;
}

static int modifier_held(const struct ks_state *state)
{
	for (int code = 0; code <= KEY_MAX; code++) {
		if (state->keys_down[code] && is_modifier(code))
			return 1;
	}
	return 0;
}

static void queue_event(struct ks_state *state, int code, int value)
{
	if (state->space.queued_count >= KS_MAX_QUEUE)
		return;
	struct ks_queued *item =
		&state->space.queue[state->space.queued_count++];
	item->code = code;
	item->value = value;
}

static int was_queued(const struct ks_state *state, int code)
{
	for (int i = 0; i < state->space.queued_count; i++) {
		if (state->space.queue[i].code == code)
			return 1;
	}
	return 0;
}

static void flush_as_tap(struct ks_state *state, struct ks_outputs *out,
			 long t_ms)
{
	out_key(state, out, t_ms, KEY_SPACE, 1);
	out_key(state, out, t_ms, KEY_SPACE, 0);
	for (int i = 0; i < state->space.queued_count; i++)
		out_key(state, out, t_ms, state->space.queue[i].code,
			state->space.queue[i].value);
	state->space.queued_count = 0;
}

static void flush_as_meta(struct ks_state *state, struct ks_outputs *out,
			  long t_ms)
{
	for (int i = 0; i < state->space.queued_count; i++)
		emit_meta_chord(state, out, t_ms, state->space.queue[i].code,
				state->space.queue[i].value);
	state->space.queued_count = 0;
}

static int handle_ctrl_overload(struct ks_state *state,
				struct ks_outputs *out, long t_ms,
				struct ks_ctrl *ctrl, int value)
{
	if (value == 1) {
		ctrl->state = KS_CTRL_PENDING;
		ctrl->pressed_ms = t_ms;
		ctrl->interrupted = 0;
		out_key(state, out, t_ms, KEY_LEFTCTRL, 1);
		return 1;
	}
	if (value == 0) {
		out_key(state, out, t_ms, KEY_LEFTCTRL, 0);
		if (ctrl->state == KS_CTRL_PENDING && !ctrl->interrupted &&
		    t_ms - ctrl->pressed_ms < KS_TAP_MS) {
			out_key(state, out, t_ms, KEY_ESC, 1);
			out_key(state, out, t_ms, KEY_ESC, 0);
		}
		ctrl->state = KS_CTRL_IDLE;
		return 1;
	}
	if (value == 2) {
		out_key(state, out, t_ms, KEY_LEFTCTRL, 2);
		return 1;
	}
	return 0;
}

static int handle_space(struct ks_state *state, struct ks_outputs *out,
			long t_ms, int code, int value)
{
	if (code == KEY_SPACE) {
		if (value == 1) {
			state->space.state = KS_SPACE_PENDING;
			state->space.pressed_ms = t_ms;
			state->space.queued_count = 0;
			return 1;
		}
		if (value == 0) {
			if (state->space.state == KS_SPACE_PENDING) {
				if (t_ms - state->space.pressed_ms < KS_TAP_MS)
					flush_as_tap(state, out, t_ms);
				else
					state->space.queued_count = 0;
			}
			state->space.state = KS_SPACE_IDLE;
			return 1;
		}
		if (value == 2)
			return 1;
	}

	if (state->space.state == KS_SPACE_PENDING) {
		long elapsed = t_ms - state->space.pressed_ms;
		if (value == 1) {
			if (elapsed >= KS_SPACE_HOLD_MS) {
				state->space.state = KS_SPACE_HELD;
				flush_as_meta(state, out, t_ms);
				emit_meta_chord(state, out, t_ms, code, 1);
				return 1;
			}
			queue_event(state, code, value);
			return 1;
		}
		if (value == 0) {
			if (was_queued(state, code)) {
				state->space.state = KS_SPACE_HELD;
				flush_as_meta(state, out, t_ms);
				emit_meta_chord(state, out, t_ms, code, 0);
				return 1;
			}
			return 0;
		}
	}

	if (state->space.state == KS_SPACE_HELD) {
		emit_meta_chord(state, out, t_ms, code, value);
		return 1;
	}
	return 0;
}

/* Today's remap chain: Esc, Caps Lock, Left Ctrl and the Space layer. */
static void process_key(struct ks_state *state, struct ks_outputs *out,
			long t_ms, int code, int value)
{
	if (code == KEY_ESC) {
		out_key(state, out, t_ms, KEY_CAPSLOCK, value);
		return;
	}
	if (code == KEY_CAPSLOCK &&
	    handle_ctrl_overload(state, out, t_ms, &state->capslock, value))
		return;
	if (code == KEY_LEFTCTRL &&
	    handle_ctrl_overload(state, out, t_ms, &state->leftctrl, value))
		return;
	if (handle_space(state, out, t_ms, code, value))
		return;
	if (value == 1) {
		if (state->capslock.state == KS_CTRL_PENDING)
			state->capslock.interrupted = 1;
		if (state->leftctrl.state == KS_CTRL_PENDING)
			state->leftctrl.interrupted = 1;
	}
	out_key(state, out, t_ms, code, value);
}

static void send_paste(struct ks_state *state, struct ks_outputs *out,
		       long t_ms)
{
	out_key(state, out, t_ms, KEY_LEFTSHIFT, 1);
	out_key(state, out, t_ms, KEY_INSERT, 1);
	out_key(state, out, t_ms, KEY_INSERT, 0);
	out_key(state, out, t_ms, KEY_LEFTSHIFT, 0);
	out_sock(out, KS_OUT_SOCK_PASTED, t_ms, 0, NULL);
}

static void maybe_paste(struct ks_state *state, long t_ms,
			struct ks_outputs *out)
{
	if (!state->paste_pending)
		return;
	if (!state->client) {
		state->paste_pending = 0;
		state->paste_deadline = -1;
		return;
	}
	if (modifier_held(state))
		return;
	state->paste_pending = 0;
	state->paste_deadline = -1;
	send_paste(state, out, t_ms);
}

static void arm_chord(struct ks_state *state, long t_ms)
{
	if (!state->keys_down[KEY_LEFTSHIFT] ||
	    !state->keys_down[KEY_RIGHTSHIFT] || !state->keys_down[KEY_ESC]) {
		state->chord_deadline = -1;
		return;
	}
	if (state->chord_deadline < 0)
		state->chord_deadline = t_ms + KS_ESCAPE_MS;
}

static void release_all(struct ks_state *state, long t_ms,
			struct ks_outputs *out)
{
	for (int code = 0; code <= KEY_MAX; code++) {
		if (state->out_down[code])
			out_key(state, out, t_ms, code, 0);
	}
	out_sock(out, KS_OUT_GRAB_RELEASE, t_ms, 0, NULL);
	state->space.queued_count = 0;
}

static void fire_chord(struct ks_state *state, long t_ms,
		       struct ks_outputs *out)
{
	release_all(state, t_ms, out);
	state->exit = 1;
	state->alt_deadline = -1;
	state->chord_deadline = -1;
	state->paste_pending = 0;
	state->paste_deadline = -1;
}

static void advance(struct ks_state *state, long t_ms, struct ks_outputs *out)
{
	for (;;) {
		enum { FIRE_NONE, FIRE_ALT, FIRE_CHORD, FIRE_PASTE } fire =
			FIRE_NONE;
		long best = 0;

		if (state->chord_deadline >= 0 &&
		    state->chord_deadline <= t_ms) {
			best = state->chord_deadline;
			fire = FIRE_CHORD;
		}
		if (state->alt.state == KS_ALT_PENDING &&
		    state->alt_deadline >= 0 &&
		    state->alt_deadline <= t_ms &&
		    (fire == FIRE_NONE || state->alt_deadline < best)) {
			best = state->alt_deadline;
			fire = FIRE_ALT;
		}
		if (state->paste_pending && state->paste_deadline >= 0 &&
		    state->paste_deadline <= t_ms &&
		    (fire == FIRE_NONE || state->paste_deadline < best)) {
			best = state->paste_deadline;
			fire = FIRE_PASTE;
		}

		if (fire == FIRE_NONE)
			return;
		if (fire == FIRE_CHORD) {
			fire_chord(state, best, out);
			return;
		}
		if (fire == FIRE_ALT) {
			if (state->client) {
				out_sock(out, KS_OUT_SOCK_START, best,
					 state->alt.pressed_ms, NULL);
				state->alt.state = KS_ALT_DICTATE;
			}
			state->alt_deadline = -1;
			continue;
		}
		state->paste_pending = 0;
		state->paste_deadline = -1;
		out_sock(out, KS_OUT_SOCK_PASTE_FAILED, best, 0,
			 "modifier-held");
	}
}

static void handle_left_alt(struct ks_state *state, struct ks_outputs *out,
			    long t_ms, int value)
{
	if (value == 1) {
		if (state->alt.state != KS_ALT_IDLE)
			return;
		if (other_key_held(state, KEY_LEFTALT)) {
			process_key(state, out, t_ms, KEY_LEFTALT, 1);
			state->alt.state = KS_ALT_CHORD;
		} else {
			state->alt.state = KS_ALT_PENDING;
			state->alt.pressed_ms = t_ms;
			state->alt_deadline = t_ms + KS_ALT_MS;
		}
		return;
	}
	if (value == 2) {
		if (state->alt.state == KS_ALT_CHORD)
			process_key(state, out, t_ms, KEY_LEFTALT, 2);
		return;
	}
	if (value != 0)
		return;

	switch (state->alt.state) {
	case KS_ALT_PENDING:
		process_key(state, out, t_ms, KEY_LEFTALT, 1);
		process_key(state, out, t_ms, KEY_LEFTALT, 0);
		break;
	case KS_ALT_DICTATE:
		out_sock(out, KS_OUT_SOCK_STOP, t_ms, t_ms, NULL);
		break;
	case KS_ALT_CHORD:
		process_key(state, out, t_ms, KEY_LEFTALT, 0);
		break;
	case KS_ALT_SWALLOW:
	case KS_ALT_IDLE:
		break;
	}
	state->alt.state = KS_ALT_IDLE;
	state->alt_deadline = -1;
}

static void resolve_alt_for_pointer(struct ks_state *state, long t_ms,
				    struct ks_outputs *out)
{
	if (state->alt.state == KS_ALT_PENDING) {
		process_key(state, out, t_ms, KEY_LEFTALT, 1);
		state->alt.state = KS_ALT_CHORD;
		state->alt_deadline = -1;
	} else if (state->alt.state == KS_ALT_DICTATE) {
		out_sock(out, KS_OUT_SOCK_CANCEL, t_ms, t_ms, NULL);
		process_key(state, out, t_ms, KEY_LEFTALT, 1);
		state->alt.state = KS_ALT_CHORD;
	}
}

static void handle_key(struct ks_state *state, const struct ks_input *in,
		       struct ks_outputs *out)
{
	long t_ms = in->t_ms;
	int code = in->code;
	int value = in->value;

	if (code < 0 || code > KEY_MAX)
		return;
	if (value == 0)
		state->keys_down[code] = 0;
	else
		state->keys_down[code] = 1;
	arm_chord(state, t_ms);

	if (code == KEY_LEFTALT) {
		if (value == 1) {
			if (state->capslock.state == KS_CTRL_PENDING)
				state->capslock.interrupted = 1;
			if (state->leftctrl.state == KS_CTRL_PENDING)
				state->leftctrl.interrupted = 1;
		}
		handle_left_alt(state, out, t_ms, value);
		return;
	}

	/* A press resolves a held-back Alt. A release alone does not. */
	if (value == 1) {
		if (state->alt.state == KS_ALT_PENDING) {
			process_key(state, out, t_ms, KEY_LEFTALT, 1);
			state->alt.state = KS_ALT_CHORD;
			state->alt_deadline = -1;
		} else if (state->alt.state == KS_ALT_DICTATE) {
			out_sock(out, KS_OUT_SOCK_CANCEL, t_ms, t_ms, NULL);
			process_key(state, out, t_ms, KEY_LEFTALT, 1);
			state->alt.state = KS_ALT_CHORD;
		}
	}
	process_key(state, out, t_ms, code, value);
}

static void handle_pointer(struct ks_state *state, const struct ks_input *in,
			   struct ks_outputs *out)
{
	if ((in->kind == KS_IN_BTN && in->value == 1) ||
	    (in->kind == KS_IN_REL && in->value != 0 &&
	     (in->code == REL_WHEEL || in->code == REL_HWHEEL ||
	      in->code == REL_WHEEL_HI_RES ||
	      in->code == REL_HWHEEL_HI_RES)))
		resolve_alt_for_pointer(state, in->t_ms, out);
}

static void handle_connect(struct ks_state *state)
{
	if (state->client && state->alt.state == KS_ALT_DICTATE)
		state->alt.state = KS_ALT_SWALLOW;
	state->client = 1;
}

static void handle_disconnect(struct ks_state *state)
{
	state->client = 0;
	if (state->alt.state == KS_ALT_DICTATE)
		state->alt.state = KS_ALT_SWALLOW;
	state->paste_pending = 0;
	state->paste_deadline = -1;
}

static void handle_paste(struct ks_state *state, long t_ms,
			 struct ks_outputs *out)
{
	if (!state->client || state->paste_pending)
		return;
	state->paste_pending = 1;
	state->paste_deadline = t_ms + KS_PASTE_WAIT_MS;
	maybe_paste(state, t_ms, out);
}

void ks_init(struct ks_state *state)
{
	memset(state, 0, sizeof(*state));
	state->alt_deadline = -1;
	state->chord_deadline = -1;
	state->paste_deadline = -1;
}

void ks_handle(struct ks_state *state, const struct ks_input *in,
	       struct ks_outputs *out)
{
	out->count = 0;
	if (state->exit)
		return;
	advance(state, in->t_ms, out);
	if (state->exit)
		return;

	switch (in->kind) {
	case KS_IN_KEY:
		handle_key(state, in, out);
		if (in->value == 0)
			maybe_paste(state, in->t_ms, out);
		break;
	case KS_IN_BTN:
	case KS_IN_REL:
		handle_pointer(state, in, out);
		break;
	case KS_IN_SOCK_CONNECT:
		handle_connect(state);
		break;
	case KS_IN_SOCK_DISCONNECT:
		handle_disconnect(state);
		break;
	case KS_IN_SOCK_PASTE:
		handle_paste(state, in->t_ms, out);
		break;
	case KS_IN_TICK:
		break;
	}
}

int ks_deadline(const struct ks_state *state, long *t_ms)
{
	long best = -1;
	if (state->alt.state == KS_ALT_PENDING && state->alt_deadline >= 0)
		best = state->alt_deadline;
	if (state->chord_deadline >= 0 &&
	    (best < 0 || state->chord_deadline < best))
		best = state->chord_deadline;
	if (state->paste_pending && state->paste_deadline >= 0 &&
	    (best < 0 || state->paste_deadline < best))
		best = state->paste_deadline;
	if (best < 0)
		return 0;
	*t_ms = best;
	return 1;
}

void ks_release_all(struct ks_state *state, long t_ms, struct ks_outputs *out)
{
	out->count = 0;
	release_all(state, t_ms, out);
}

/*
 * A keyboard that disappeared cannot report its releases, so nothing may
 * stay down and no pending tap may fire from fake input.
 */
void ks_device_lost(struct ks_state *state, long t_ms, struct ks_outputs *out)
{
	out->count = 0;
	for (int code = 0; code <= KEY_MAX; code++) {
		if (state->out_down[code])
			out_key(state, out, t_ms, code, 0);
	}
	if (state->alt.state == KS_ALT_DICTATE)
		out_sock(out, KS_OUT_SOCK_STOP, t_ms, t_ms, NULL);
	memset(state->keys_down, 0, sizeof(state->keys_down));
	state->capslock.state = KS_CTRL_IDLE;
	state->leftctrl.state = KS_CTRL_IDLE;
	state->space.state = KS_SPACE_IDLE;
	state->space.queued_count = 0;
	state->alt.state = KS_ALT_IDLE;
	state->alt_deadline = -1;
	state->chord_deadline = -1;
	/* No key is held now, so a paste that waited for a modifier runs. */
	maybe_paste(state, t_ms, out);
}
