"""System-Python adapter for the XDG ScreenCast portal and PipeWire."""
from __future__ import annotations

import secrets
import json
import struct
import sys
import threading
import time


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
    from dbus.mainloop.glib import DBusGMainLoop, threads_init
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    from gi.repository import GLib, Gst

    threads_init()
    DBusGMainLoop(set_as_default=True)
    Gst.init(None)
    bus = dbus.SessionBus()
    portal_object = bus.get_object(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
    )
    remote = dbus.Interface(
        portal_object,
        "org.freedesktop.portal.RemoteDesktop",
    )
    screencast = dbus.Interface(
        portal_object,
        "org.freedesktop.portal.ScreenCast",
    )
    token = "aurora_" + secrets.token_hex(8)
    request = remote.CreateSession({"handle_token": token, "session_handle_token": token + "_session"})
    data = portal_response(bus, request, GLib)
    session_path = str(data["session_handle"])
    pipeline = None
    try:
        # The GNOME portal prompts the user for explicit pointer-control and
        # screen-sharing consent. Never enable global remote-control settings.
        request = remote.SelectDevices(session_path, {
            "handle_token": token + "_devices", "types": dbus.UInt32(2),
        })
        portal_response(bus, request, GLib)
        request = screencast.SelectSources(session_path, {
            "handle_token": token + "_sources", "types": dbus.UInt32(1),
            "multiple": False, "cursor_mode": dbus.UInt32(2),
        })
        portal_response(bus, request, GLib)
        request = remote.Start(session_path, "", {"handle_token": token + "_start"})
        data = portal_response(bus, request, GLib)
        streams = data.get("streams", [])
        devices = int(data.get("devices", 0))
        if not streams:
            raise RuntimeError("O portal não retornou uma tela para transmitir.")
        if not (devices & 2):
            raise PermissionError("O GNOME não autorizou controle do ponteiro.")
        node_id = int(streams[0][0])
        properties = streams[0][1]
        size = properties.get("size", (1920, 1080))
        screen_width, screen_height = int(size[0]), int(size[1])
        if screen_width <= 0 or screen_height <= 0:
            raise RuntimeError("O portal informou dimensões inválidas para a tela.")
        def read_input_events():
            buttons = {1: 0x110, 2: 0x112, 3: 0x111}
            for line in sys.stdin.buffer:
                try:
                    event = json.loads(line.decode("utf-8"))
                    action = event["action"]
                    x = float(event["x"]) * screen_width
                    y = float(event["y"]) * screen_height
                    button = buttons[int(event.get("button", 1))]
                    if action in {"move", "click", "double_click", "down", "up"}:
                        remote.NotifyPointerMotionAbsolute(
                            session_path, {}, dbus.UInt32(node_id), x, y
                        )
                    if action == "move":
                        pass
                    elif action in {"click", "double_click", "down", "up"}:
                        state = 0 if action == "up" else 1
                        remote.NotifyPointerButton(session_path, {}, dbus.Int32(button), dbus.UInt32(state))
                        if action in {"click", "double_click"}:
                            remote.NotifyPointerButton(session_path, {}, dbus.Int32(button), dbus.UInt32(0))
                        if action == "double_click":
                            time.sleep(0.07)
                            remote.NotifyPointerButton(session_path, {}, dbus.Int32(button), dbus.UInt32(1))
                            remote.NotifyPointerButton(session_path, {}, dbus.Int32(button), dbus.UInt32(0))
                    elif action == "scroll":
                        steps = max(-10, min(10, int(float(event.get("delta", 0)))))
                        if steps:
                            remote.NotifyPointerAxisDiscrete(session_path, {}, dbus.UInt32(0), dbus.Int32(steps))
                except Exception as exc:
                    print(f"[remote-input] {type(exc).__name__}", file=sys.stderr, flush=True)

        threading.Thread(target=read_input_events, name="aurora-portal-input", daemon=True).start()
        remote_fd = screencast.OpenPipeWireRemote(session_path, {})
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
