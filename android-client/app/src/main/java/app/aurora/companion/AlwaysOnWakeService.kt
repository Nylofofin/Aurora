// SPDX-License-Identifier: GPL-3.0-only
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
 * Ao identificar "aurora", dispara broadcast e PAUSA o ciclo de escuta
 * para não conflitar com o microfone do PcmVoiceCapture durante o comando.
 *
 * CORREÇÕES v0.8.2:
 *  - Pausa a escuta ao detectar wake word (evita loop de mic)
 *  - Só reinicia quando recebe ACTION_RESUME_LISTENING (após fim do comando)
 *  - stopService correto via onStartCommand(ACTION_STOP)
 *  - START_NOT_STICKY para evitar restart automático do Android em crash
 *  - Contador de erros consecutivos: para após 10 falhas e notifica
 */
class AlwaysOnWakeService : Service() {

    private val running = AtomicBoolean(false)
    private val paused = AtomicBoolean(false)   // pausa enquanto user fala o comando
    private var recognizer: SpeechRecognizer? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var consecutiveErrors = 0
    private val MAX_CONSECUTIVE_ERRORS = 10

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                Log.i(TAG, "ACTION_STOP recebido")
                running.set(false)
                paused.set(false)
                stopListening()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
                return START_NOT_STICKY
            }
            ACTION_PAUSE_LISTENING -> {
                Log.i(TAG, "ACTION_PAUSE_LISTENING recebido: pausando microfone")
                paused.set(true)
                stopListening()
                return START_NOT_STICKY
            }
            ACTION_RESUME_LISTENING -> {
                // Chamado pelo ViewModel quando o comando do usuário terminou
                Log.i(TAG, "ACTION_RESUME_LISTENING: retomando escuta")
                if (running.get()) {
                    paused.set(false)
                    mainHandler.removeCallbacksAndMessages(null)
                    mainHandler.postDelayed({ startRecognizer() }, RESUME_DELAY_MS)
                }
                return START_NOT_STICKY
            }
        }

        // Já está rodando — ignora start duplicado
        if (running.get()) {
            Log.d(TAG, "Já em execução, ignorando start duplicado")
            return START_NOT_STICKY
        }

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
        paused.set(false)
        consecutiveErrors = 0
        mainHandler.post { startRecognizer() }

        // START_NOT_STICKY: o Android NÃO reinicia o serviço automaticamente se ele morrer.
        // Isso evita loops de restart com intent=null que causam comportamento indefinido.
        return START_NOT_STICKY
    }

    private fun startRecognizer() {
        if (!running.get() || paused.get()) return

        // Destrói instância anterior com segurança
        val oldRec = recognizer
        recognizer = null
        runCatching { oldRec?.destroy() }

        try {
            val rec = SpeechRecognizer.createSpeechRecognizer(this)
            rec.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    consecutiveErrors = 0 // reset ao começar a ouvir com sucesso
                }
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit

                override fun onPartialResults(partialResults: Bundle?) {
                    if (paused.get()) return
                    val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: return
                    for (text in matches) {
                        if (containsWakeWord(text)) {
                            onWakeDetected()
                            return
                        }
                    }
                }

                override fun onResults(results: Bundle?) {
                    if (!running.get()) return
                    if (paused.get()) return
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: emptyList<String>()
                    var found = false
                    for (text in matches) {
                        if (containsWakeWord(text)) {
                            onWakeDetected()
                            found = true
                            break
                        }
                    }
                    if (!found && running.get() && !paused.get()) {
                        restartRecognizer(RESTART_DELAY_MS)
                    }
                }

                override fun onError(error: Int) {
                    if (!running.get()) return
                    consecutiveErrors++
                    Log.w(TAG, "SpeechRecognizer erro=$error consecutivos=$consecutiveErrors")

                    if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                        Log.e(TAG, "Muitos erros consecutivos, parando escuta.")
                        broadcastError("Escuta encerrada após $consecutiveErrors falhas consecutivas. Verifique a conexão com a internet.")
                        running.set(false)
                        stopForeground(STOP_FOREGROUND_REMOVE)
                        stopSelf()
                        return
                    }

                    // Tempos de espera por código de erro (evita spam de restart)
                    val delay = when (error) {
                        SpeechRecognizer.ERROR_NO_MATCH,
                        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> 300L
                        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> 1000L
                        SpeechRecognizer.ERROR_AUDIO,
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> 2000L
                        else -> 1500L
                    }
                    restartRecognizer(delay)
                }

                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })
            recognizer = rec

            val listenIntent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                // Sem EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH: deixa o recognizer decidir
                // quando parar — minimiza falsos timeouts
            }
            rec.startListening(listenIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Erro ao criar/iniciar SpeechRecognizer", e)
            consecutiveErrors++
            restartRecognizer(2000)
        }
    }

    private fun onWakeDetected() {
        Log.i(TAG, "Wake word 'Aurora' detectada! Pausando escuta.")

        // CRÍTICO: pausa ANTES de qualquer outra ação para evitar conflito de mic
        paused.set(true)
        mainHandler.removeCallbacksAndMessages(null)

        // Para o recognizer atual com segurança
        val rec = recognizer
        recognizer = null
        runCatching { rec?.stopListening() }
        // Não destrói ainda — deixa terminar o ciclo atual limpo
        mainHandler.postDelayed({ runCatching { rec?.destroy() } }, 500)

        // Envia broadcast para a MainActivity / ViewModel
        sendBroadcast(Intent(ACTION_DETECTED).setPackage(packageName))

        // Traz Activity para frente (sem forçar nova instância se já está no topo)
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_SINGLE_TOP or
                Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
            )
        }
        launchIntent?.let { startActivity(it) }

        // A escuta SÓ volta quando o ViewModel mandar ACTION_RESUME_LISTENING
        // (após o comando do usuário terminar)
    }

    private fun restartRecognizer(delayMs: Long) {
        if (!running.get() || paused.get()) return
        mainHandler.removeCallbacksAndMessages(null)
        mainHandler.postDelayed({
            if (running.get() && !paused.get()) {
                startRecognizer()
            }
        }, delayMs)
    }

    private fun stopListening() {
        mainHandler.removeCallbacksAndMessages(null)
        val rec = recognizer
        recognizer = null
        runCatching { rec?.stopListening() }
        runCatching { rec?.destroy() }
    }

    override fun onDestroy() {
        Log.i(TAG, "onDestroy")
        running.set(false)
        paused.set(false)
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
                setSound(null, null) // sem som ao criar/atualizar notificação
            }
        )
    }

    private fun buildNotification(): Notification {
        val stopIntent = Intent(this, AlwaysOnWakeService::class.java).apply {
            action = ACTION_STOP
        }
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
        else
            @Suppress("DEPRECATION")
            Notification.Builder(this)

        @Suppress("DEPRECATION")
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
        /** Enviado pelo ViewModel para pausar a escuta enquanto o usuário fala */
        const val ACTION_PAUSE_LISTENING = "app.aurora.companion.ALWAYS_ON_WAKE_PAUSE"
        /** Enviado pelo ViewModel quando o usuário terminou de falar o comando */
        const val ACTION_RESUME_LISTENING = "app.aurora.companion.ALWAYS_ON_WAKE_RESUME"
        const val EXTRA_MESSAGE = "message"

        private const val WAKE_WORD = "aurora"
        private const val TAG = "AlwaysOnWakeService"
        private const val CHANNEL_ID = "aurora-always-on-wake"
        private const val NOTIFICATION_ID = 0xA074
        private const val RESTART_DELAY_MS = 300L
        private const val RESUME_DELAY_MS = 1500L // aguarda mic do PcmVoiceCapture ser liberado
    }
}
