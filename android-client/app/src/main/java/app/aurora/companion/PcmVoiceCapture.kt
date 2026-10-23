package app.aurora.companion

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/**
 * Captura inteligente de voz em PCM mono (16 kHz, 16 bits).
 * Inclui detecção de fala e auto-finalização por silêncio após o início da fala (VAD simples).
 */
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
        val buffer = ShortArray(1_600) // 100ms chunks a 16kHz
        val byteBuffer = ByteArray(3_200)
        val startedAt = System.nanoTime()

        var hasSpoken = false
        var consecutiveSilenceChunks = 0
        val silenceThresholdRms = 450.0 // Nível de corte para silêncio ambiente
        val requiredSilenceChunksForStop = 15 // 1.5s de silêncio contínuo após falar = fim do comando

        try {
            audio.startRecording()
            while (!stopped.get() && (System.nanoTime() - startedAt) < 45_000_000_000L) {
                val readShorts = audio.read(buffer, 0, buffer.size)
                if (readShorts > 0) {
                    var sumSquares = 0.0
                    for (i in 0 until readShorts) {
                        val s = buffer[i]
                        sumSquares += (s * s).toDouble()
                        byteBuffer[i * 2] = (s.toInt() and 0xff).toByte()
                        byteBuffer[i * 2 + 1] = ((s.toInt() shr 8) and 0xff).toByte()
                    }
                    pcm.write(byteBuffer, 0, readShorts * 2)

                    val rms = sqrt(sumSquares / readShorts)
                    if (rms > silenceThresholdRms) {
                        hasSpoken = true
                        consecutiveSilenceChunks = 0
                    } else if (hasSpoken) {
                        consecutiveSilenceChunks++
                        if (consecutiveSilenceChunks >= requiredSilenceChunksForStop) {
                            // Usuário terminou de falar a frase/comando
                            break
                        }
                    }
                }
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
