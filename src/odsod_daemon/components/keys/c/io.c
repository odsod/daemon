#define _GNU_SOURCE
#include "keynames.h"
#include "state.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/uinput.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define INPUT_DIR "/dev/input"
#define RUNTIME_DIR "/run/odsod-daemon-keys"
#define SOCKET_PATH RUNTIME_DIR "/dictation.sock"
#define MAX_DEVICES 64
#define MAX_POLLFD (MAX_DEVICES + 4)
#define CLIENT_BUFFER 512
#define UINPUT_NAME "odsod-daemon-keys virtual keyboard"
#define UINPUT_VENDOR 0x4f44
#define UINPUT_PRODUCT 0x4b59
#define HOTPLUG_SETTLE_MS 100

struct device {
	int fd;
	int keyboard;
	char path[PATH_MAX];
};

static struct device devices[MAX_DEVICES];
static int device_count;
static int uinput_fd = -1;
static int listen_fd = -1;
static uid_t owner_uid;

struct client {
	int fd;
	char buffer[CLIENT_BUFFER];
	size_t used;
};

static struct client client = {.fd = -1, .used = 0};

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t report_latency = 0;

static long latency_count;
static long long latency_sum_ns;
static long long latency_max_ns;

static void on_signal(int sig)
{
	if (sig == SIGUSR1)
		report_latency = 1;
	else
		running = 0;
}

static long mono_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long)ts.tv_sec * 1000 + (long)(ts.tv_nsec / 1000000);
}

static long long mono_ns(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long long)ts.tv_sec * 1000000000LL + (long long)ts.tv_nsec;
}

static long wall_offset_ms(void)
{
	struct timespec real;
	struct timespec mono;
	clock_gettime(CLOCK_REALTIME, &real);
	clock_gettime(CLOCK_MONOTONIC, &mono);
	long real_ms = (long)real.tv_sec * 1000 + (long)(real.tv_nsec / 1000000);
	long mono_ms_now = (long)mono.tv_sec * 1000 + (long)(mono.tv_nsec / 1000000);
	return real_ms - mono_ms_now;
}

static long event_ms(const struct input_event *ev)
{
	return (long)ev->input_event_sec * 1000 +
	       (long)(ev->input_event_usec / 1000);
}

static int write_all(int fd, const void *buffer, size_t length)
{
	const char *cursor = buffer;
	while (length > 0) {
		ssize_t written = write(fd, cursor, length);
		if (written < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		cursor += written;
		length -= (size_t)written;
	}
	return 0;
}

static int write_event(int fd, int type, int code, int value)
{
	struct input_event ev;
	memset(&ev, 0, sizeof(ev));
	ev.type = (unsigned short)type;
	ev.code = (unsigned short)code;
	ev.value = value;
	return write_all(fd, &ev, sizeof(ev));
}

static int bit_set(const unsigned long *bits, int bit)
{
	size_t index = (size_t)bit / (8 * sizeof(unsigned long));
	unsigned long mask = 1UL << ((size_t)bit % (8 * sizeof(unsigned long)));
	return (bits[index] & mask) != 0;
}

static int is_keyboard(int fd)
{
	unsigned long evbits[EV_MAX / 8 / sizeof(long) + 1] = {0};
	unsigned long keybits[KEY_MAX / 8 / sizeof(long) + 1] = {0};

	if (ioctl(fd, EVIOCGBIT(0, sizeof(evbits)), evbits) < 0)
		return 0;
	if (!bit_set(evbits, EV_KEY))
		return 0;
	if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keybits)), keybits) < 0)
		return 0;

	int letters = 0;
	for (int code = KEY_Q; code <= KEY_P; code++) {
		if (bit_set(keybits, code))
			letters++;
	}
	return letters >= 5;
}

static int is_pointer(int fd)
{
	unsigned long keybits[KEY_MAX / 8 / sizeof(long) + 1] = {0};
	unsigned long relbits[REL_MAX / 8 / sizeof(long) + 1] = {0};

	if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keybits)), keybits) < 0)
		return 0;
	if (bit_set(keybits, BTN_LEFT))
		return 1;
	if (ioctl(fd, EVIOCGBIT(EV_REL, sizeof(relbits)), relbits) < 0)
		return 0;
	return bit_set(relbits, REL_WHEEL);
}

static int is_virtual(int fd)
{
	struct input_id id;
	if (ioctl(fd, EVIOCGID, &id) < 0)
		return 0;
	if (id.bustype == BUS_VIRTUAL)
		return 1;

	char name[256] = {0};
	if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0 &&
	    strstr(name, "odsod-daemon-keys") != NULL)
		return 1;
	return 0;
}

static int setup_uinput(void)
{
	int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) {
		perror("open /dev/uinput");
		return -1;
	}
	if (ioctl(fd, UI_SET_EVBIT, EV_KEY) < 0 ||
	    ioctl(fd, UI_SET_EVBIT, EV_SYN) < 0 ||
	    ioctl(fd, UI_SET_EVBIT, EV_REP) < 0)
		goto fail;
	for (int code = 0; code <= KEY_MAX; code++)
		(void)ioctl(fd, UI_SET_KEYBIT, code);

	struct uinput_setup setup;
	memset(&setup, 0, sizeof(setup));
	setup.id.bustype = BUS_VIRTUAL;
	setup.id.vendor = UINPUT_VENDOR;
	setup.id.product = UINPUT_PRODUCT;
	snprintf(setup.name, UINPUT_MAX_NAME_SIZE, "%s", UINPUT_NAME);
	if (ioctl(fd, UI_DEV_SETUP, &setup) < 0 ||
	    ioctl(fd, UI_DEV_CREATE) < 0)
		goto fail;
	return fd;

fail:
	perror("uinput setup");
	close(fd);
	return -1;
}

static void open_device(const char *path, int grab)
{
	if (device_count >= MAX_DEVICES)
		return;
	int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0)
		return;
	if (is_virtual(fd)) {
		close(fd);
		return;
	}

	int keyboard = is_keyboard(fd);
	int pointer = !keyboard && is_pointer(fd);
	if (!keyboard && !pointer) {
		close(fd);
		return;
	}

	int clock_id = CLOCK_MONOTONIC;
	(void)ioctl(fd, EVIOCSCLOCKID, &clock_id);
	if (keyboard && grab && ioctl(fd, EVIOCGRAB, 1) < 0) {
		close(fd);
		return;
	}

	struct device *dev = &devices[device_count++];
	dev->fd = fd;
	dev->keyboard = keyboard;
	snprintf(dev->path, sizeof(dev->path), "%s", path);

	char name[256] = "unknown";
	(void)ioctl(fd, EVIOCGNAME(sizeof(name)), name);
	fprintf(stderr, "[odsod-daemon-keys] %s: %s (%s)\n",
		keyboard ? (grab ? "grabbed" : "recording") : "pointer", path,
		name);
}

static void scan_devices(int grab)
{
	DIR *dir = opendir(INPUT_DIR);
	if (dir == NULL)
		return;
	struct dirent *entry;
	while ((entry = readdir(dir)) != NULL) {
		if (strncmp(entry->d_name, "event", 5) != 0)
			continue;
		char path[PATH_MAX];
		snprintf(path, sizeof(path), "%s/%s", INPUT_DIR, entry->d_name);
		int known = 0;
		for (int i = 0; i < device_count; i++) {
			if (strcmp(devices[i].path, path) == 0) {
				known = 1;
				break;
			}
		}
		if (!known)
			open_device(path, grab);
	}
	closedir(dir);
}

static int device_index_of(int fd)
{
	for (int i = 0; i < device_count; i++) {
		if (devices[i].fd == fd)
			return i;
	}
	return -1;
}

static void drop_device(int index)
{
	if (index < 0 || index >= device_count)
		return;
	(void)ioctl(devices[index].fd, EVIOCGRAB, 0);
	close(devices[index].fd);
	devices[index] = devices[--device_count];
}

static void release_devices(void)
{
	for (int i = 0; i < device_count; i++) {
		(void)ioctl(devices[i].fd, EVIOCGRAB, 0);
		close(devices[i].fd);
	}
	device_count = 0;
}

static void format_time(long wall_ms, char *out, size_t length)
{
	time_t seconds = (time_t)(wall_ms / 1000);
	int millis = (int)(wall_ms % 1000);
	if (millis < 0)
		millis += 1000;
	struct tm tm;
	char base[32];
	if (gmtime_r(&seconds, &tm) == NULL ||
	    strftime(base, sizeof(base), "%Y-%m-%dT%H:%M:%S", &tm) == 0) {
		snprintf(out, length, "1970-01-01T00:00:00.000Z");
		return;
	}
	snprintf(out, length, "%s.%03dZ", base, millis);
}

static int send_line(int fd, const char *line)
{
	size_t length = strlen(line);
	ssize_t written =
		send(fd, line, length, MSG_NOSIGNAL | MSG_DONTWAIT);
	return written == (ssize_t)length ? 0 : -1;
}

static int format_message(const struct ks_output *item, long wall_offset,
			  char *buffer, size_t length)
{
	char stamp[64];
	switch (item->kind) {
	case KS_OUT_SOCK_START:
		format_time(item->msg_ms + wall_offset, stamp, sizeof(stamp));
		snprintf(buffer, length, "start %s\n", stamp);
		return 1;
	case KS_OUT_SOCK_STOP:
		format_time(item->msg_ms + wall_offset, stamp, sizeof(stamp));
		snprintf(buffer, length, "stop %s\n", stamp);
		return 1;
	case KS_OUT_SOCK_CANCEL:
		format_time(item->msg_ms + wall_offset, stamp, sizeof(stamp));
		snprintf(buffer, length, "cancel %s\n", stamp);
		return 1;
	case KS_OUT_SOCK_PASTED:
		snprintf(buffer, length, "pasted\n");
		return 1;
	case KS_OUT_SOCK_PASTE_FAILED:
		snprintf(buffer, length, "paste-failed %s\n",
			 item->reason == NULL ? "unknown" : item->reason);
		return 1;
	case KS_OUT_KEY:
	case KS_OUT_GRAB_RELEASE:
		return 0;
	}
	return 0;
}

static void apply_outputs(struct ks_state *state, struct ks_outputs *out,
			  long wall_offset);

static void drop_client(struct ks_state *state, long wall_offset)
{
	if (client.fd < 0)
		return;
	close(client.fd);
	client.fd = -1;
	client.used = 0;
	struct ks_input in = {.t_ms = mono_ms(),
			      .kind = KS_IN_SOCK_DISCONNECT,
			      .code = 0,
			      .value = 0};
	struct ks_outputs out;
	ks_handle(state, &in, &out);
	apply_outputs(state, &out, wall_offset);
}

static void apply_outputs(struct ks_state *state, struct ks_outputs *out,
			  long wall_offset)
{
	int drop = 0;
	for (int i = 0; i < out->count; i++) {
		const struct ks_output *item = &out->items[i];
		if (item->kind == KS_OUT_KEY) {
			if (uinput_fd >= 0 &&
			    write_event(uinput_fd, EV_KEY, item->code,
					item->value) == 0)
				(void)write_event(uinput_fd, EV_SYN, SYN_REPORT, 0);
			continue;
		}
		if (item->kind == KS_OUT_GRAB_RELEASE)
			continue;
		char message[128];
		if (!format_message(item, wall_offset, message, sizeof(message)))
			continue;
		if (client.fd >= 0 && send_line(client.fd, message) < 0)
			drop = 1;
	}
	if (drop)
		drop_client(state, wall_offset);
}

static void feed_input(struct ks_state *state, const struct ks_input *in,
		       long wall_offset)
{
	struct ks_outputs out;
	ks_handle(state, in, &out);
	apply_outputs(state, &out, wall_offset);
}

static void feed_event(struct ks_state *state, const struct input_event *ev,
		       int keyboard, long wall_offset)
{
	if (ev->type == EV_SYN)
		return;
	if (ev->type == EV_KEY) {
		struct ks_input in = {.t_ms = event_ms(ev),
				      .kind = keyboard ? KS_IN_KEY : KS_IN_BTN,
				      .code = ev->code,
				      .value = ev->value};
		feed_input(state, &in, wall_offset);
		return;
	}
	if (ev->type == EV_REL && !keyboard) {
		struct ks_input in = {.t_ms = event_ms(ev),
				      .kind = KS_IN_REL,
				      .code = ev->code,
				      .value = ev->value};
		feed_input(state, &in, wall_offset);
		return;
	}
	if (keyboard && uinput_fd >= 0) {
		(void)write_event(uinput_fd, ev->type, ev->code, ev->value);
		(void)write_event(uinput_fd, EV_SYN, SYN_REPORT, 0);
	}
}

static int setup_socket(void)
{
	if (mkdir(RUNTIME_DIR, 0755) < 0 && errno != EEXIST) {
		fprintf(stderr, "[odsod-daemon-keys] %s: %s\n", RUNTIME_DIR,
			strerror(errno));
		return -1;
	}
	struct stat st;
	if (stat(RUNTIME_DIR, &st) == 0)
		owner_uid = st.st_uid;
	else
		owner_uid = getuid();

	unlink(SOCKET_PATH);
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (fd < 0) {
		perror("socket");
		return -1;
	}
	struct sockaddr_un addr;
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", SOCKET_PATH);
	if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		perror("bind dictation socket");
		close(fd);
		return -1;
	}
	(void)chmod(SOCKET_PATH, 0600);
	(void)chown(SOCKET_PATH, owner_uid, (gid_t)-1);
	if (listen(fd, 4) < 0) {
		perror("listen dictation socket");
		close(fd);
		unlink(SOCKET_PATH);
		return -1;
	}
	return fd;
}

static void accept_client(struct ks_state *state, long wall_offset)
{
	int fd = accept4(listen_fd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
	if (fd < 0)
		return;
	struct ucred cred;
	socklen_t length = sizeof(cred);
	if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &length) < 0 ||
	    cred.uid != owner_uid) {
		fprintf(stderr,
			"[odsod-daemon-keys] rejected a socket peer\n");
		close(fd);
		return;
	}
	if (client.fd >= 0) {
		drop_client(state, wall_offset);
	} else {
		client.used = 0;
	}
	client.fd = fd;
	struct ks_input in = {.t_ms = mono_ms(),
			      .kind = KS_IN_SOCK_CONNECT,
			      .code = 0,
			      .value = 0};
	feed_input(state, &in, wall_offset);
}

static void read_client(struct ks_state *state, long wall_offset)
{
	char chunk[256];
	ssize_t count = recv(client.fd, chunk, sizeof(chunk), MSG_DONTWAIT);
	if (count == 0) {
		drop_client(state, wall_offset);
		return;
	}
	if (count < 0) {
		if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
			return;
		drop_client(state, wall_offset);
		return;
	}
	for (ssize_t i = 0; i < count; i++) {
		char value = chunk[i];
		if (value == '\n') {
			if (client.used > 0 &&
			    client.buffer[client.used - 1] == '\r')
				client.used--;
			client.buffer[client.used] = '\0';
			if (strcmp(client.buffer, "paste") == 0) {
				struct ks_input in = {
					.t_ms = mono_ms(),
					.kind = KS_IN_SOCK_PASTE,
					.code = 0,
					.value = 0};
				feed_input(state, &in, wall_offset);
			} else if (client.used > 0) {
				fprintf(stderr,
					"[odsod-daemon-keys] unknown message: %s\n",
					client.buffer);
			}
			client.used = 0;
			continue;
		}
		if (client.used + 1 < sizeof(client.buffer)) {
			client.buffer[client.used++] = value;
			continue;
		}
		client.used = 0;
	}
}

static int record_main(const char *path)
{
	FILE *out = fopen(path, "w");
	if (out == NULL) {
		perror(path);
		return 1;
	}
	scan_devices(0);
	if (device_count == 0) {
		fprintf(stderr, "[odsod-daemon-keys] no keyboards found\n");
		fclose(out);
		return 1;
	}
	long start = mono_ms();
	while (running) {
		struct pollfd pfds[MAX_DEVICES];
		int count = device_count;
		for (int i = 0; i < count; i++) {
			pfds[i].fd = devices[i].fd;
			pfds[i].events = POLLIN;
			pfds[i].revents = 0;
		}
		int ready = poll(pfds, (nfds_t)count, 100);
		if (ready < 0) {
			if (errno == EINTR)
				continue;
			break;
		}
		for (int i = 0; i < count; i++) {
			if (!(pfds[i].revents & (POLLIN | POLLERR | POLLHUP)))
				continue;
			int index = device_index_of(pfds[i].fd);
			if (index < 0)
				continue;
			struct input_event events[64];
			ssize_t length =
				read(pfds[i].fd, events, sizeof(events));
			if (length <= 0) {
				drop_device(index);
				continue;
			}
			int n = (int)(length /
				      (ssize_t)sizeof(struct input_event));
			for (int e = 0; e < n; e++) {
				const struct input_event *ev = &events[e];
				const char *name = key_name_of(ev->code);
				if (name == NULL)
					continue;
				long t = event_ms(ev) - start;
				if (ev->type == EV_KEY) {
					fprintf(out,
						"%ld in %s %s %s\n", t,
						devices[index].keyboard ? "key"
								    : "btn",
						name,
						ev->value == 1
							? "down"
							: (ev->value == 0
								   ? "up"
								   : "repeat"));
				} else if (ev->type == EV_REL) {
					fprintf(out, "%ld in rel %s %d\n", t,
						name, ev->value);
				}
			}
			fflush(out);
		}
	}
	release_devices();
	fclose(out);
	return 0;
}

static void log_latency(void)
{
	if (latency_count == 0) {
		fprintf(stderr,
			"[odsod-daemon-keys] latency: no key events yet\n");
		return;
	}
	fprintf(stderr,
		"[odsod-daemon-keys] latency: count=%ld avg=%.3fms max=%.3fms\n",
		latency_count,
		(double)latency_sum_ns / (double)latency_count / 1000000.0,
		(double)latency_max_ns / 1000000.0);
}

int main(int argc, char **argv)
{
	if (argc == 3 && strcmp(argv[1], "--record") == 0)
		return record_main(argv[2]);
	if (argc != 1) {
		fprintf(stderr,
			"usage: %s [--record <file.seq>]\n"
			"  --record needs the keys service stopped, because it "
			"holds the grabs\n",
			argv[0]);
		return 2;
	}

	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);
	signal(SIGUSR1, on_signal);
	signal(SIGPIPE, SIG_IGN);

	uinput_fd = setup_uinput();
	if (uinput_fd < 0)
		return 1;
	/* Let the uinput device appear before the first grab. */
	usleep(200000);

	scan_devices(1);
	if (device_count == 0) {
		fprintf(stderr, "[odsod-daemon-keys] no keyboards found\n");
		ioctl(uinput_fd, UI_DEV_DESTROY);
		close(uinput_fd);
		return 1;
	}

	int inotify_fd = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
	if (inotify_fd >= 0)
		(void)inotify_add_watch(inotify_fd, INPUT_DIR, IN_CREATE);

	listen_fd = setup_socket();

	struct ks_state state;
	ks_init(&state);

	while (running) {
		struct pollfd pfds[MAX_POLLFD];
		nfds_t count = 0;

		for (int i = 0; i < device_count; i++) {
			pfds[count].fd = devices[i].fd;
			pfds[count].events = POLLIN;
			pfds[count].revents = 0;
			count++;
		}
		if (inotify_fd >= 0) {
			pfds[count].fd = inotify_fd;
			pfds[count].events = POLLIN;
			pfds[count].revents = 0;
			count++;
		}
		if (listen_fd >= 0) {
			pfds[count].fd = listen_fd;
			pfds[count].events = POLLIN;
			pfds[count].revents = 0;
			count++;
		}
		if (client.fd >= 0) {
			pfds[count].fd = client.fd;
			pfds[count].events = POLLIN;
			pfds[count].revents = 0;
			count++;
		}

		int timeout = -1;
		long deadline = 0;
		if (ks_deadline(&state, &deadline)) {
			long wait = deadline - mono_ms();
			timeout = wait < 0 ? 0 : (int)wait;
		}

		int ready = poll(pfds, count, timeout);
		if (ready < 0) {
			if (errno == EINTR)
				continue;
			break;
		}
		if (report_latency) {
			log_latency();
			report_latency = 0;
		}

		long wall_offset = wall_offset_ms();
		if (ready == 0) {
			struct ks_input in = {.t_ms = mono_ms(),
					      .kind = KS_IN_TICK,
					      .code = 0,
					      .value = 0};
			feed_input(&state, &in, wall_offset);
			if (state.exit) {
				running = 0;
				break;
			}
			continue;
		}

		for (nfds_t i = 0; i < count; i++) {
			if (!(pfds[i].revents & (POLLIN | POLLERR | POLLHUP)))
				continue;
			short revents = pfds[i].revents;
			if (inotify_fd >= 0 && pfds[i].fd == inotify_fd) {
				char buffer[4096];
				while (read(inotify_fd, buffer,
					    sizeof(buffer)) > 0)
					;
				usleep(HOTPLUG_SETTLE_MS * 1000);
				scan_devices(1);
				continue;
			}
			if (listen_fd >= 0 && pfds[i].fd == listen_fd) {
				accept_client(&state, wall_offset);
				continue;
			}
			if (client.fd >= 0 && pfds[i].fd == client.fd) {
				read_client(&state, wall_offset);
				continue;
			}
			int index = device_index_of(pfds[i].fd);
			if (index < 0)
				continue;
			struct device *dev = &devices[index];
			if (revents & POLLERR) {
				drop_device(index);
				continue;
			}

			long long started = mono_ns();
			struct input_event events[64];
			ssize_t length = read(dev->fd, events, sizeof(events));
			if (length <= 0) {
				if (length < 0 &&
				    (errno == EAGAIN || errno == EINTR))
					continue;
				drop_device(index);
				continue;
			}
			int n = (int)(length /
				      (ssize_t)sizeof(struct input_event));
			for (int e = 0; e < n; e++) {
				feed_event(&state, &events[e], dev->keyboard,
					   wall_offset);
				if (state.exit) {
					running = 0;
					break;
				}
			}
			if (dev->keyboard && n > 0) {
				long long elapsed = mono_ns() - started;
				latency_count++;
				latency_sum_ns += elapsed;
				if (elapsed > latency_max_ns)
					latency_max_ns = elapsed;
			}
			if (!running)
				break;
		}
	}

	struct ks_outputs final = {0};
	ks_release_all(&state, mono_ms(), &final);
	apply_outputs(&state, &final, wall_offset_ms());
	release_devices();
	if (uinput_fd >= 0) {
		(void)ioctl(uinput_fd, UI_DEV_DESTROY);
		close(uinput_fd);
	}
	if (inotify_fd >= 0)
		close(inotify_fd);
	if (client.fd >= 0)
		close(client.fd);
	if (listen_fd >= 0) {
		close(listen_fd);
		unlink(SOCKET_PATH);
	}
	fprintf(stderr, "[odsod-daemon-keys] stopped\n");
	return 0;
}
