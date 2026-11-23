#include "state.h"

#include <string.h>

/*
 * Today's remaps, ported from keys/odsod-keys.c in the machine repo:
 *
 * - Esc gives Caps Lock.
 * - Caps Lock and Left Ctrl give Ctrl, or Esc on a tap within 350 ms.
 * - Space gives a Space tap, or a Meta layer when another key follows.
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

void ks_init(struct ks_state *state)
{
	memset(state, 0, sizeof(*state));
}

void ks_handle(struct ks_state *state, const struct ks_input *in,
	       struct ks_outputs *out)
{
	out->count = 0;
	if (in->kind != KS_IN_KEY)
		return;
	process_key(state, out, in->t_ms, in->code, in->value);
}
