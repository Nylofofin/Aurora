package app.aurora.companion

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.WindowManager

/**
 * Serviço responsável por gerenciar a bolha flutuante da Aurora sobre outros apps.
 * Usa AuroraBubbleView em Canvas nativo para estabilidade total e performance máxima.
 */
class FloatingBubbleService : Service() {

    private var windowManager: WindowManager? = null
    private var bubbleView: AuroraBubbleView? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as? WindowManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SHOW -> {
                showBubble()
            }
            ACTION_HIDE -> {
                hideBubble()
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    private fun showBubble() {
        if (bubbleView != null) return

        // 1. Verificação rigorosa de segurança para evitar BadTokenException / SecurityException
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            return
        }

        val wm = windowManager ?: return
        val density = resources.displayMetrics.density
        val sizePx = (84 * density).toInt()

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            sizePx, sizePx,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = (resources.displayMetrics.widthPixels - sizePx - (24 * density).toInt()).coerceAtLeast(0)
            y = (resources.displayMetrics.heightPixels / 3)
        }

        val view = AuroraBubbleView(
            context = this,
            windowManager = wm,
            layoutParams = params,
            onBubbleClick = {
                // Traz o app Aurora para frente
                val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
                    action = Intent.ACTION_MAIN
                    addCategory(Intent.CATEGORY_LAUNCHER)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                }
                launchIntent?.let { startActivity(it) }
            },
            onDismissClick = {
                sendBroadcast(Intent(ACTION_BUBBLE_DISMISSED).setPackage(packageName))
                hideBubble()
                stopSelf()
            }
        )

        try {
            wm.addView(view, params)
            bubbleView = view
        } catch (_: Exception) {
            bubbleView = null
        }
    }

    private fun hideBubble() {
        bubbleView?.let { view ->
            runCatching { windowManager?.removeView(view) }
        }
        bubbleView = null
    }

    override fun onDestroy() {
        hideBubble()
        super.onDestroy()
    }

    companion object {
        const val ACTION_SHOW = "app.aurora.companion.BUBBLE_SHOW"
        const val ACTION_HIDE = "app.aurora.companion.BUBBLE_HIDE"
        const val ACTION_BUBBLE_DISMISSED = "app.aurora.companion.BUBBLE_DISMISSED"
    }
}
