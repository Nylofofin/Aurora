package app.aurora.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Escuta constante — equivalente ao "Hey Google" para a Aurora.
 *
 * Estratégia: usa o SpeechRecognizer nativo do Android (Google) em modo de loop
 * contínuo. Quando detecta a palavra "aurora" nos resultados parciais ou finais,
 * emite ACTION_DETECTED e para a escuta até ser reiniciado.
 *
 * Não requer modelo local extra — usa o mesmo reconhecedor que já estava disponível
 * no dispositivo. Limitação: precisa de internet (mesma limitação do recognize_google
 * no PC). Para uso totalmente offline, substituir por Vosk Android SDK no futuro.
 *
 * Permissões necessárias: RECORD_AUDIO, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE
 */
class AlwaysOnWakeService : Service() {

    private val running = AtomicBoolean(false)
    private var recognizer: SpeechRecognizer? = null
    private var restartScheduled = false
    private var consecutiveErrors = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopListening()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
                return START_NOT_STICKY
            }
        }

        if (running.get()) return START_NOT_STICKY  // já estava rodando

        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            broadcastError("O reconhecimento de voz não está disponível neste dispositivo.")
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
        consecutiveErrors = 0
        startListeningCycle()

        return START_NOT_STICKY
    }

    private fun startListeningCycle() {
        if (!running.get()) return

        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: android.os.Bundle?) {
                    consecutiveErrors = 0  // serviço respondendo normalmente
                }

                override fun onPartialResults(partialResults: android.os.Bundle?) {
                    // Detectar "aurora" nos resultados parciais para resposta imediata
                    val partials = partialResults
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?: return
                    if (partials.any { containsWakeWord(it) }) {
                        onWakeDetected()
                    }
                }

                override fun onResults(results: android.os.Bundle?) {
                    val matches = results
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?: return
                    if (matches.any { containsWakeWord(it) }) {
                        onWakeDetected()
                    } else {
                        // Não era a wake word — reiniciar o ciclo de escuta
                        scheduleRestart(delayMs = 300)
                    }
                }

                override fun onError(error: Int) {
                    if (!running.get()) return
                    val isTransient = error == SpeechRecognizer.ERROR_NO_MATCH ||
                            error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT ||
                            error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY

                    if (isTransient) {
                        consecutiveErrors++
                        val delay = if (consecutiveErrors > 5) 2000L else 600L
                        scheduleRestart(delay)
                    } else {
                        consecutiveErrors++
                        Log.w(TAG, "AlwaysOnWake erro $error (consecutivos: $consecutiveErrors)")
                        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                            running.set(false)
                            broadcastError("A escuta contínua falhou após várias tentativas (código $error). Toque em Mic para reativar.")
                            stopForeground(STOP_FOREGROUND_REMOVE)
                            stopSelf()
                        } else {
                            scheduleRestart(delayMs = 3000)
                        }
                    }
                }

                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit
                override fun onEvent(eventType: Int, params: android.os.Bundle?) = Unit
            })
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1000L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 200L)
            // Não passar EXTRA_CALLING_PACKAGE para não exibir UI
        }
        try {
            recognizer?.startListening(intent)
        } catch (e: Exception) {
            Log.w(TAG, "Falha ao iniciar listening: ${e.message}")
            scheduleRestart(delayMs = 1000)
        }
    }

    private fun onWakeDetected() {
        if (!running.get()) return
        running.set(false)
        Log.i(TAG, "Wake word 'Aurora' detectada pelo SpeechRecognizer local")
        stopListening()
        sendBroadcast(Intent(ACTION_DETECTED).setPackage(packageName))
        // Notificar visualmente
        val launch = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        val pending = launch?.let {
            PendingIntent.getActivity(this, 2, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            val builder = Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentTitle("Aurora ouviu você")
                .setContentText("Toque para abrir e continuar a conversa.")
                .setAutoCancel(true)
                .setContentIntent(pending)
            nm.notify(WAKE_NOTIFICATION_ID, builder.build())
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun scheduleRestart(delayMs: Long) {
        if (restartScheduled || !running.get()) return
        restartScheduled = true
        android.os.Handler(mainLooper).postDelayed({
            restartScheduled = false
            if (running.get()) startListeningCycle()
        }, delayMs)
    }

    private fun stopListening() {
        running.set(false)
        runCatching { recognizer?.stopListening() }
        runCatching { recognizer?.destroy() }
        recognizer = null
    }

    override fun onDestroy() {
        stopListening()
        super.onDestroy()
    }

    private fun containsWakeWord(text: String): Boolean {
        val normalized = text.lowercase().trim()
        // Aceita "aurora", "aurora," e variações comuns de reconhecimento
        return normalized == WAKE_WORD ||
                normalized.startsWith("$WAKE_WORD ") ||
                normalized.startsWith("$WAKE_WORD,") ||
                normalized.endsWith(" $WAKE_WORD") ||
                normalized.contains(" $WAKE_WORD ")
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
                description = "Aurora está aguardando você dizer 'Aurora'. O microfone é processado localmente."
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
            .setContentTitle("Aurora está aguardando você")
            .setContentText("Diga \"Aurora\" para começar. Toque para abrir o app.")
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
        private const val WAKE_NOTIFICATION_ID = 0xA075
        private const val MAX_CONSECUTIVE_ERRORS = 8
    }
}
