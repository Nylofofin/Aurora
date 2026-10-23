package app.aurora.companion

import android.media.MediaPlayer
import android.media.AudioAttributes
import java.io.File
import java.io.FileOutputStream

/** Plays audio synthesized or supplied by the paired PC without invoking Android TTS. */
class RemoteAudioPlayer(private val cacheDirectory: File) {
    private var player: MediaPlayer? = null
    private var playingFile: File? = null

    @Synchronized
    fun play(bytes: ByteArray, onStarted: () -> Unit = {}, onFinished: (Boolean) -> Unit = {}) {
        stop()
        if (bytes.isEmpty()) {
            onFinished(false)
            return
        }
        var file: File? = null
        try {
            val audioFile = File.createTempFile("aurora-reply-", ".audio", cacheDirectory)
            file = audioFile
            FileOutputStream(audioFile).use { it.write(bytes) }
            val next = MediaPlayer()
            player = next
            playingFile = audioFile
            next.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            next.setVolume(1f, 1f)
            next.setDataSource(audioFile.absolutePath)
            next.setOnPreparedListener { media ->
                runCatching { media.start(); onStarted() }.onFailure {
                    finish(media, audioFile, onFinished, false)
                }
            }
            next.setOnCompletionListener { media -> finish(media, audioFile, onFinished, true) }
            next.setOnErrorListener { media, _, _ ->
                finish(media, audioFile, onFinished, false)
                true
            }
            next.prepareAsync()
        } catch (_: Exception) {
            runCatching { player?.release() }
            player = null
            playingFile = null
            file?.delete()
            onFinished(false)
        }
    }

    @Synchronized
    fun stop() {
        player?.let { current ->
            runCatching { if (current.isPlaying) current.stop() }
            runCatching { current.reset() }
            runCatching { current.release() }
        }
        player = null
        playingFile?.delete()
        playingFile = null
    }

    @Synchronized
    fun release() = stop()

    @Synchronized
    private fun finish(media: MediaPlayer, file: File, onFinished: (Boolean) -> Unit, success: Boolean) {
        if (player !== media) return
        runCatching { media.release() }
        player = null
        if (playingFile == file) playingFile = null
        file.delete()
        onFinished(success)
    }
}
