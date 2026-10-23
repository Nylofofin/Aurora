"""System-Python adapter for the XDG ScreenCast portal and PipeWire."""
from __future__ import annotations

import secrets
import struct
import sys


def portal_response(bus, request_path, GLib, timeout=30):
    loop = GLib.MainLoop()
    result = {}

    def received(code, data):
        result["code"] = int(code)
        result["data"] = dict(data)
        if loop.is_running():
            loop.quit()

    receiver = bus.add_signal_receiver(
        received, signal_name="Response", dbus_interface="org.freedesktop.portal.Request",
        path=request_path,
    )
    timer = GLib.timeout_add(int(timeout * 1000), lambda: (loop.quit(), False)[1])
    try:
        loop.run()
    finally:
        GLib.source_remove(timer)
        receiver.remove()
    if "code" not in result:
        raise TimeoutError("O portal não respondeu à solicitação de compartilhamento.")
    if result["code"] != 0:
        raise PermissionError("O compartilhamento da tela foi recusado ou cancelado no desktop.")
    return result["data"]


def main(width: int, fps: int) -> int:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    from gi.repository import GLib, Gst

    DBusGMainLoop(set_as_default=True)
    Gst.init(None)
    bus = dbus.SessionBus()
    portal = dbus.Interface(
        bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"),
        "org.freedesktop.portal.ScreenCast",
    )
    token = "aurora_" + secrets.token_hex(8)
    request = portal.CreateSession({"handle_token": token, "session_handle_token": token + "_session"})
    data = portal_response(bus, request, GLib)
    session_path = str(data["session_handle"])
    pipeline = None
    try:
        request = portal.SelectSources(session_path, {
            "handle_token": token + "_sources", "types": dbus.UInt32(1),
            "multiple": False, "cursor_mode": dbus.UInt32(2),
        })
        portal_response(bus, request, GLib)
        request = portal.Start(session_path, "", {"handle_token": token + "_start"})
        data = portal_response(bus, request, GLib)
        streams = data.get("streams", [])
        if not streams:
            raise RuntimeError("O portal não retornou uma tela para transmitir.")
        node_id = int(streams[0][0])
        remote_fd = portal.OpenPipeWireRemote(session_path, {})
        fd = remote_fd.take() if hasattr(remote_fd, "take") else int(remote_fd)
        pipeline = Gst.parse_launch(
            f"pipewiresrc fd={fd} path={node_id} do-timestamp=true ! videoconvert ! videoscale ! "
            f"video/x-raw,width={width},framerate={fps}/1 ! jpegenc quality=58 ! "
            "appsink name=aurora_sink max-buffers=1 drop=true sync=false"
        )
        sink = pipeline.get_by_name("aurora_sink")
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Não consegui iniciar o fluxo PipeWire.")
        while True:
            sample = sink.emit("try-pull-sample", 1_000_000_000)
            if sample is None:
                continue
            buffer = sample.get_buffer()
            success, mapping = buffer.map(Gst.MapFlags.READ)
            if not success:
                continue
            try:
                frame = bytes(mapping.data)
            finally:
                buffer.unmap(mapping)
            if not frame or len(frame) > 2_000_000:
                continue
            sys.stdout.buffer.write(struct.pack(">I", len(frame)))
            sys.stdout.buffer.write(frame)
            sys.stdout.buffer.flush()
    finally:
        if pipeline is not None:
            pipeline.set_state(Gst.State.NULL)
        try:
            session = dbus.Interface(bus.get_object("org.freedesktop.portal.Desktop", session_path),
                                      "org.freedesktop.portal.Session")
            session.Close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        main(max(320, min(int(sys.argv[1]), 1600)), max(1, min(int(sys.argv[2]), 8)))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
