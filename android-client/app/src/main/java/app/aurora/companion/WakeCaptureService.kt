package app.aurora.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import java.util.concurrent.atomic.AtomicBoolean

/** Opt-in foreground mic loop. Wake inference runs on the paired PC's local Vosk model. */
class WakeCaptureService : Service() {
    private val running = AtomicBoolean(false)
    private var captureThread: Thread? = null
    @Volatile private var activeRecorder: AudioRecord? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopCapture()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        val endpoint = intent?.getStringExtra(EXTRA_ENDPOINT).orEmpty()
        val fingerprint = intent?.getStringExtra(EXTRA_FINGERPRINT).orEmpty()
        val token = intent?.getStringExtra(EXTRA_TOKEN).orEmpty()
        if (endpoint.isBlank() || fingerprint.isBlank() || token.isBlank()) {
            stopSelf(startId)
            return START_NOT_STICKY
        }
        ensureChannel()
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else startForeground(NOTIFICATION_ID, notification)
        if (running.compareAndSet(false, true)) {
            captureThread = Thread({ listen(endpoint, fingerprint, token) }, "aurora-mobile-wake").also { it.start() }
        }
        return START_NOT_STICKY
    }

    private fun listen(endpoint: String, fingerprint: String, token: String) {
        var recorder: AudioRecord? = null
        var wakeDetected = false
        try {
            val minBuffer = AudioRecord.getMinBufferSize(
                SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            )
            check(minBuffer > 0) { "O Android não disponibilizou o microfone." }
            recorder = AudioRecord(
                MediaRecorder.AudioSource.MIC, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuffer, FRAME_BYTES * 2),
            )
            activeRecorder = recorder
            check(recorder.state == AudioRecord.STATE_INITIALIZED) { "Não consegui iniciar o microfone." }
            recorder.startRecording()
            val client = CompanionClient(endpoint, fingerprint, token)
            val frame = ByteArray(FRAME_BYTES)
            var consecutiveErrors = 0
            while (running.get()) {
                var offset = 0
                while (running.get() && offset < frame.size) {
                    val count = recorder.read(frame, offset, frame.size - offset, AudioRecord.READ_BLOCKING)
                    if (count <= 0) throw IllegalStateException("A leitura do microfone falhou.")
                    offset += count
                }
                if (!running.get()) break
                try {
                    if (client.detectWake(frame.copyOf())) {
                        wakeDetected = true
                        running.set(false)
                    }
                    consecutiveErrors = 0
                } catch (netError: java.io.IOException) {
                    consecutiveErrors++
                    if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                        throw IllegalStateException("Conexão com o PC perdida após $MAX_CONSECUTIVE_ERRORS tentativas: ${netError.message}")
                    }
                    Thread.sleep(RECONNECT_DELAY_MS)
                }
            }
        } catch (error: Exception) {
            if (running.get()) {
                sendBroadcast(Intent(ACTION_ERROR).setPackage(packageName).putExtra(EXTRA_MESSAGE,
                    error.message ?: "A escuta por voz foi interrompida."))
            }
            running.set(false)
        } finally {
            runCatching { recorder?.stop() }
            recorder?.release()
            activeRecorder = null
            if (wakeDetected) notifyWakeDetected()
            stopForeground(STOP_FOREGROUND_REMOVE)
            if (wakeDetected) sendBroadcast(Intent(ACTION_DETECTED).setPackage(packageName))
            stopSelf()
        }
    }

    private fun stopCapture() {
        running.set(false)
        captureThread?.interrupt()
        runCatching { activeRecorder?.stop() }
        captureThread = null
    }

    private fun notifyWakeDetected() {
        val launch = packageManager.getLaunchIntentForPackage(packageName) ?: return
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val pending = PendingIntent.getActivity(this, 2, launch, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL_ID)
        else Notification.Builder(this)
        getSystemService(NotificationManager::class.java).notify(
            WAKE_NOTIFICATION_ID,
            builder.setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentTitle("Aurora ouviu a palavra de ativação")
                .setContentText("Abra o app para falar; o Android limita a abertura automática de telas em segundo plano.")
                .setContentIntent(pending).setAutoCancel(true).setCategory(Notification.CATEGORY_EVENT).build(),
        )
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Wake word Aurora", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Microfone ativo enquanto a ativação por voz está ligada. O PC reconhece Aurora localmente."
            },
        )
    }

    private fun buildNotification(): Notification {
        val pending = packageManager.getLaunchIntentForPackage(packageName)?.let {
            PendingIntent.getActivity(this, 1, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL_ID)
        else Notification.Builder(this)
        return builder.setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("Aurora está aguardando a palavra de ativação")
            .setContentText("Áudio enviado ao PC pareado por HTTPS; detecção local no PC. Toque para desativar.")
            .setCategory(Notification.CATEGORY_SERVICE).setOngoing(true).setOnlyAlertOnce(true)
            .setContentIntent(pending).build()
    }

    override fun onDestroy() {
        stopCapture()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "app.aurora.companion.WAKE_START"
        const val ACTION_STOP = "app.aurora.companion.WAKE_STOP"
        const val ACTION_DETECTED = "app.aurora.companion.WAKE_DETECTED"
        const val ACTION_ERROR = "app.aurora.companion.WAKE_ERROR"
        const val EXTRA_ENDPOINT = "endpoint"
        const val EXTRA_FINGERPRINT = "fingerprint"
        const val EXTRA_TOKEN = "token"
        const val EXTRA_MESSAGE = "message"
        private const val CHANNEL_ID = "aurora-wake"
        private const val NOTIFICATION_ID = 0xA071
        private const val WAKE_NOTIFICATION_ID = 0xA072
        private const val SAMPLE_RATE = 16_000
        private const val FRAME_BYTES = SAMPLE_RATE * 2 / 5  // 6400 bytes = 200ms
        private const val MAX_CONSECUTIVE_ERRORS = 10
        private const val RECONNECT_DELAY_MS = 3_000L
    }
}
