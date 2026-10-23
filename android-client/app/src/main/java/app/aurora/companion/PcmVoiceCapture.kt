package app.aurora.companion

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/**
 * Captura inteligente e estável de voz em PCM mono (16 kHz, 16 bits).
 *
 * Melhorias v0.8.2:
 *  - Descarta ruído de inicialização (eco do som de toque/beep de entrada)
 *  - VAD robusto: exige fala contínua (>200ms) para ativar deteção de voz
 *  - Timeout de espera sem fala (6s) sem estourar exceção agressiva (retorna vazio)
 *  - Silêncio de 1.8s após início de fala encerra o comando naturalmente
 *  - Liberação limpa e síncrona do AudioRecord
 */
class PcmVoiceCapture {
    private val stopped = AtomicBoolean(false)
    @Volatile private var recorder: AudioRecord? = null
    @Volatile private var recordingStarted = false
    @Volatile var lastCaptureError: String? = null
        private set

    fun stop() {
        stopped.set(true)
        val active = recorder
        try {
            if (active?.recordingState == AudioRecord.RECORDSTATE_RECORDING) active.stop()
        } catch (_: Exception) { }
        recordingStarted = false
    }

    @Synchronized
    fun captureWav(): ByteArray {
        val sampleRate = 16_000
        val minBuffer = AudioRecord.getMinBufferSize(
            sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) {
            Log.e(TAG, "AudioRecord minBufferSize inválido: $minBuffer")
            lastCaptureError = "O Android não disponibilizou o microfone."
            return ByteArray(0)
        }

        val bufferSize = maxOf(minBuffer * 2, 6_400)
        val audio = recorder ?: try {
                AudioRecord(
                    MediaRecorder.AudioSource.MIC, sampleRate, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT, bufferSize,
                ).also { recorder = it }
            } catch (e: Exception) {
                Log.e(TAG, "Erro ao instanciar AudioRecord", e)
                lastCaptureError = e.message ?: "Não foi possível abrir o microfone."
                return ByteArray(0)
            }

        if (audio.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord não inicializado (recurso ocupado)")
            lastCaptureError = "O microfone está ocupado ou indisponível."
            runCatching { audio.release() }
            if (recorder === audio) recorder = null
            recordingStarted = false
            return ByteArray(0)
        }

        val pcm = ByteArrayOutputStream()
        val buffer = ShortArray(1_600) // 100ms chunks a 16kHz
        val byteBuffer = ByteArray(3_200)
        val startedAt = System.nanoTime()

        var hasSpoken = false
        var speechChunks = 0
        var consecutiveSilenceChunks = 0
        var totalChunks = 0

        val silenceThresholdRms = 480.0 // Nível de corte para ruído ambiente
        val minSpeechChunksToConfirm = 2 // 200ms de voz contínua para confirmar que não é apenas estalo
        val requiredSilenceChunksForStop = 18 // 1.8s de silêncio contínuo após falar = fim do comando
        val maxWaitingChunksWithoutSpeech = 60 // 6.0s sem fala alguma = desiste pacificamente

        try {
            if (!recordingStarted) {
                audio.startRecording()
                recordingStarted = true
                lastCaptureError = null
            }
            while (!stopped.get() && (System.nanoTime() - startedAt) < 45_000_000_000L) {
                val readShorts = audio.read(buffer, 0, buffer.size)
                if (readShorts > 0) {
                    totalChunks++

                    // Descarta o início do primeiro ciclo para ignorar o beep de entrada.
                    if (!hasReadAudio && totalChunks <= 2) {
                        continue
                    }
                    hasReadAudio = true

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
                        speechChunks++
                        consecutiveSilenceChunks = 0
                        if (speechChunks >= minSpeechChunksToConfirm) {
                            hasSpoken = true
                        }
                    } else {
                        speechChunks = 0
                        if (hasSpoken) {
                            consecutiveSilenceChunks++
                            if (consecutiveSilenceChunks >= requiredSilenceChunksForStop) {
                                // Usuário concluiu o comando falado
                                break
                            }
                        } else {
                            // Usuário ainda não falou
                            if (totalChunks >= maxWaitingChunksWithoutSpeech) {
                                // Tempo esgotado sem fala
                                Log.d(TAG, "Timeout de espera sem fala do usuário")
                                break
                            }
                        }
                    }
                } else if (readShorts < 0) {
                    throw IllegalStateException("AudioRecord.read falhou ($readShorts)")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Exceção durante leitura do microfone", e)
            lastCaptureError = e.message ?: "Falha na captura do microfone"
            releaseRecorderForRetry()
        }

        if (!hasSpoken) {
            // Nenhuma fala válida detectada
            return ByteArray(0)
        }

        val bytes = pcm.toByteArray()
        if (bytes.size < sampleRate * 2 / 2) {
            // Menos de meio segundo de áudio gravado
            return ByteArray(0)
        }

        return wavHeader(bytes.size, sampleRate) + bytes
    }

    private var hasReadAudio = false

    @Synchronized
    fun close() {
        stopped.set(true)
        releaseRecorderForRetry()
    }

    @Synchronized
    private fun releaseRecorderForRetry() {
        val active = recorder
        recorder = null
        recordingStarted = false
        try {
            if (active?.recordingState == AudioRecord.RECORDSTATE_RECORDING) active.stop()
        } catch (_: Exception) { }
        try { active?.release() } catch (_: Exception) { }
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

    companion object {
        private const val TAG = "PcmVoiceCapture"
    }
}
