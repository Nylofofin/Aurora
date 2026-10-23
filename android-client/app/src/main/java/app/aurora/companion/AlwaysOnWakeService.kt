package app.aurora.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Escuta contínua ultra-estável — "Hey Aurora".
 *
 * Fica permanentemente ouvindo o ambiente sem interrupções.
 * Ao identificar "aurora", dispara a notificação e acorda a Aurora imediatamente,
 * mantendo o ciclo vivo para a próxima ativação.
 */
class AlwaysOnWakeService : Service() {

    private val running = AtomicBoolean(false)
    private var recognizer: SpeechRecognizer? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var isListening = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                running.set(false)
                stopListening()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
                return START_NOT_STICKY
            }
        }

        if (running.get()) return START_STICKY

        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            broadcastError("Reconhecimento de fala indisponível neste aparelho.")
            stopSelf(startId)
            return START_NOT_STICKY
        }

        ensureChannel()
        val notif = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notif)
        }

        running.set(true)
        mainHandler.post { startRecognizer() }

        return START_STICKY
    }

    private fun startRecognizer() {
        if (!running.get()) return

        try {
            recognizer?.destroy()
            recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {
                        isListening = true
                    }

                    override fun onBeginningOfSpeech() = Unit
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() {
                        isListening = false
                    }

                    override fun onPartialResults(partialResults: Bundle?) {
                        val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: return
                        for (text in matches) {
                            if (containsWakeWord(text)) {
                                onWakeDetected()
                                return
                            }
                        }
                    }

                    override fun onResults(results: Bundle?) {
                        isListening = false
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: return
                        var found = false
                        for (text in matches) {
                            if (containsWakeWord(text)) {
                                onWakeDetected()
                                found = true
                                break
                            }
                        }
                        if (!found && running.get()) {
                            restartRecognizer(150)
                        }
                    }

                    override fun onError(error: Int) {
                        isListening = false
                        if (!running.get()) return
                        // Códigos transitivos normais em escuta contínua (timeout de silêncio, sem áudio etc)
                        val delay = when (error) {
                            SpeechRecognizer.ERROR_NO_MATCH,
                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> 150L
                            SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> 400L
                            else -> 1000L
                        }
                        restartRecognizer(delay)
                    }

                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                })
            }

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            }
            recognizer?.startListening(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Erro ao iniciar SpeechRecognizer", e)
            restartRecognizer(1500)
        }
    }

    private fun onWakeDetected() {
        Log.i(TAG, "Wake word 'Aurora' detectada!")
        // Envia broadcast para a MainActivity / ViewModel
        sendBroadcast(Intent(ACTION_DETECTED).setPackage(packageName))

        // Dispara intent para trazer Activity para a frente
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        launchIntent?.let { startActivity(it) }

        // Reinicia ciclo após 3 segundos para permitir que o usuário fale o comando atual sem colisão
        restartRecognizer(3500)
    }

    private fun restartRecognizer(delayMs: Long) {
        if (!running.get()) return
        mainHandler.removeCallbacksAndMessages(null)
        mainHandler.postDelayed({
            if (running.get()) {
                startRecognizer()
            }
        }, delayMs)
    }

    private fun stopListening() {
        mainHandler.removeCallbacksAndMessages(null)
        runCatching { recognizer?.stopListening() }
        runCatching { recognizer?.destroy() }
        recognizer = null
        isListening = false
    }

    override fun onDestroy() {
        running.set(false)
        stopListening()
        super.onDestroy()
    }

    private fun containsWakeWord(text: String): Boolean {
        val clean = text.lowercase().trim()
        return clean == WAKE_WORD ||
                clean.startsWith("$WAKE_WORD ") ||
                clean.startsWith("$WAKE_WORD,") ||
                clean.endsWith(" $WAKE_WORD") ||
                clean.contains(" $WAKE_WORD ")
    }

    private fun broadcastError(message: String) {
        sendBroadcast(Intent(ACTION_ERROR).setPackage(packageName).putExtra(EXTRA_MESSAGE, message))
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Escuta Aurora sempre ativa", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Aurora aguardando a palavra de ativação."
            }
        )
    }

    private fun buildNotification(): Notification {
        val stopIntent = Intent(ACTION_STOP).setClass(this, AlwaysOnWakeService::class.java)
        val stopPending = PendingIntent.getService(
            this, 0, stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val launchPending = launch?.let {
            PendingIntent.getActivity(this, 1, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            Notification.Builder(this, CHANNEL_ID)
        else Notification.Builder(this)

        return builder
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("Aurora está ouvindo")
            .setContentText("Diga \"Aurora\" para ativar.")
            .setCategory(Notification.CATEGORY_SERVICE)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(launchPending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Desativar", stopPending)
            .build()
    }

    companion object {
        const val ACTION_START = "app.aurora.companion.ALWAYS_ON_WAKE_START"
        const val ACTION_STOP = "app.aurora.companion.ALWAYS_ON_WAKE_STOP"
        const val ACTION_DETECTED = "app.aurora.companion.ALWAYS_ON_WAKE_DETECTED"
        const val ACTION_ERROR = "app.aurora.companion.ALWAYS_ON_WAKE_ERROR"
        const val EXTRA_MESSAGE = "message"

        private const val WAKE_WORD = "aurora"
        private const val TAG = "AlwaysOnWakeService"
        private const val CHANNEL_ID = "aurora-always-on-wake"
        private const val NOTIFICATION_ID = 0xA074
    }
}
