package app.aurora.companion

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/** Explicit foreground-only, mono PCM capture for one spoken turn. */
class PcmVoiceCapture {
    private val stopped = AtomicBoolean(false)
    @Volatile private var recorder: AudioRecord? = null

    fun stop() {
        stopped.set(true)
    }

    fun captureWav(): ByteArray {
        val sampleRate = 16_000
        val minBuffer = AudioRecord.getMinBufferSize(
            sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        require(minBuffer > 0) { "O microfone não está disponível neste aparelho." }
        val audio = AudioRecord(
            MediaRecorder.AudioSource.MIC, sampleRate, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuffer * 2, 6_400),
        )
        require(audio.state == AudioRecord.STATE_INITIALIZED) { "Não consegui iniciar o microfone." }
        recorder = audio
        val pcm = ByteArrayOutputStream()
        val buffer = ByteArray(3_200)
        val startedAt = System.nanoTime()
        try {
            audio.startRecording()
            while (!stopped.get() && (System.nanoTime() - startedAt) < 45_000_000_000L) {
                val count = audio.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING)
                if (count > 0) pcm.write(buffer, 0, count)
            }
        } finally {
            try { if (audio.recordingState == AudioRecord.RECORDSTATE_RECORDING) audio.stop() } catch (_: Exception) { }
            audio.release()
            recorder = null
        }
        val bytes = pcm.toByteArray()
        require(bytes.size >= sampleRate * 2 / 2) { "Fale por pelo menos meio segundo antes de enviar." }
        return wavHeader(bytes.size, sampleRate) + bytes
    }

    private fun wavHeader(dataSize: Int, sampleRate: Int): ByteArray {
        val header = ByteArrayOutputStream(44)
        fun ascii(value: String) = header.write(value.toByteArray(Charsets.US_ASCII))
        fun u16(value: Int) { header.write(value and 0xff); header.write((value shr 8) and 0xff) }
        fun u32(value: Int) { repeat(4) { header.write((value shr (8 * it)) and 0xff) } }
        ascii("RIFF"); u32(dataSize + 36); ascii("WAVE")
        ascii("fmt "); u32(16); u16(1); u16(1); u32(sampleRate); u32(sampleRate * 2); u16(2); u16(16)
        ascii("data"); u32(dataSize)
        return header.toByteArray()
    }
}
