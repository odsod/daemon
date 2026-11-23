"""Text output contains the same fields as the JSON report."""

from odsod_daemon.components.health.contract import StatusReport


def render(report: StatusReport) -> str:
    lines = [report.state + (" (dev)" if report.dev else "")]
    if report.commit:
        lines.append(f"commit: {report.commit}; workspace: {report.workspace}")
    for reason in report.reasons:
        lines.extend(
            [
                f"{reason.severity}: {reason.code} ({reason.service}): "
                f"{reason.message}",
                f"  since: {reason.since}; fix: {reason.fix or 'none'}",
            ]
        )
    for service in report.services:
        lines.append(
            f"{service.unit} ({service.scope}): "
            f"{service.active_state}/{service.sub_state}; "
            f"expected: {service.expected}; since: {service.since}"
        )
    for channel, newest in report.newest_audio.items():
        lines.append(f"newest audio {channel}: {newest or 'none'}")
    lines.extend(
        [
            f"backlog: {report.backlog.count} utterances, "
            f"{report.backlog.seconds:g} seconds; oldest: {report.backlog.oldest}",
            f"mode: {report.mode}; dictation available: {report.dictation.available}; "
            f"reason: {report.dictation.reason}",
            f"paused since: {report.paused_since}; exit code: {report.exit_code}; "
            f"ts: {report.ts}",
        ]
    )
    return "\n".join(lines)
