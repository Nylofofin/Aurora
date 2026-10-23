from aurora_core.system.screen_stream import DesktopScreenStream


def test_screen_stream_has_bounded_capture_parameters():
    assert (DesktopScreenStream(width=9999, fps=90).width,
            DesktopScreenStream(width=1, fps=0).fps) == (1600, 1)


def test_stopping_screen_stream_discards_the_last_desktop_frame():
    stream = DesktopScreenStream()
    stream._set_state("streaming")
    with stream._condition:
        stream._frame = b"private-frame"
        stream._frame_number = 4

    stream.stop()

    assert stream.frame_after(3, timeout=0.1) == (4, b"")


def test_worker_frame_reader_handles_partial_reads_and_eof():
    class Fragmented:
        def __init__(self, data):
            self.data = bytearray(data)

        def read(self, size):
            size = min(size, 2)
            result = bytes(self.data[:size])
            del self.data[:size]
            return result

    assert DesktopScreenStream._read_exact(Fragmented(b"abcdefgh"), 6) == b"abcdef"
    assert DesktopScreenStream._read_exact(Fragmented(b"ab"), 3) == b""
