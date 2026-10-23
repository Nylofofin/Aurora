package app.aurora.companion

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateDecelerateInterpolator
import kotlin.math.abs
import kotlin.math.min

/**
 * View nativa ultra-estável e acelerada por hardware para a bolha flutuante da Aurora.
 * Não depende do ciclo de vida de Compose dentro do WindowManager, garantindo
 * zero crashes e fluidez a 60/120 fps.
 */
@SuppressLint("ViewConstructor")
class AuroraBubbleView(
    context: Context,
    private val windowManager: WindowManager,
    private val layoutParams: WindowManager.LayoutParams,
    private val onBubbleClick: () -> Unit,
    private val onDismissClick: () -> Unit
) : View(context) {

    private val orbPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val haloPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f
    }
    private val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val closeBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#EAE3F5")
    }
    private val closeTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#29263A")
        textSize = 34f
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    private var pulseScale = 1.0f
    private var haloAlpha = 0.25f
    private var animator: ValueAnimator? = null

    // Variáveis de drag
    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false

    init {
        startAnimation()
    }

    private fun startAnimation() {
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 2000
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            interpolator = AccelerateDecelerateInterpolator()
            addUpdateListener { anim ->
                val fraction = anim.animatedValue as Float
                pulseScale = 0.95f + (fraction * 0.08f)
                haloAlpha = 0.12f + (fraction * 0.25f)
                invalidate()
            }
            start()
        }
    }

    override fun onDetachedFromWindow() {
        animator?.cancel()
        animator = null
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0 || h <= 0) return

        val centerX = w / 2f
        val centerY = h / 2f
        val baseRadius = min(w, h) * 0.40f

        // 1. Halo externo pulsante
        haloPaint.color = Color.parseColor("#8A70C4")
        haloPaint.alpha = (haloAlpha * 255).toInt().coerceIn(0, 255)
        canvas.drawCircle(centerX, centerY, baseRadius * 1.15f * pulseScale, haloPaint)

        // 2. Esfera principal com gradiente de luz perolada
        val currentRadius = baseRadius * pulseScale
        val sphereShader = LinearGradient(
            centerX - currentRadius, centerY - currentRadius,
            centerX + currentRadius, centerY + currentRadius,
            intArrayOf(
                Color.parseColor("#FFFFFF"),
                Color.parseColor("#F0EAF8"),
                Color.parseColor("#D7C8EF"),
                Color.parseColor("#A9CFE4"),
                Color.parseColor("#8A70C4")
            ),
            floatArrayOf(0.0f, 0.25f, 0.55f, 0.80f, 1.0f),
            Shader.TileMode.CLAMP
        )
        orbPaint.shader = sphereShader
        canvas.drawCircle(centerX, centerY, currentRadius, orbPaint)

        // 3. Brilho radial interno (reflexo de pérola/vidro)
        val glowShader = RadialGradient(
            centerX - (currentRadius * 0.35f),
            centerY - (currentRadius * 0.35f),
            currentRadius * 0.85f,
            intArrayOf(Color.argb(190, 255, 255, 255), Color.argb(40, 255, 255, 255), Color.TRANSPARENT),
            floatArrayOf(0.0f, 0.5f, 1.0f),
            Shader.TileMode.CLAMP
        )
        highlightPaint.shader = glowShader
        canvas.drawCircle(centerX, centerY, currentRadius, highlightPaint)

        // 4. Reflexo elíptico superior suave
        highlightPaint.shader = null
        highlightPaint.color = Color.argb(160, 255, 255, 255)
        canvas.drawOval(
            centerX - (currentRadius * 0.55f),
            centerY - (currentRadius * 0.70f),
            centerX + (currentRadius * 0.25f),
            centerY - (currentRadius * 0.30f),
            highlightPaint
        )

        // 5. Botão "×" para fechar no canto superior direito
        val closeRadius = 24f
        val closeX = w - closeRadius - 8f
        val closeY = closeRadius + 8f
        canvas.drawCircle(closeX, closeY, closeRadius, closeBgPaint)
        canvas.drawText("×", closeX, closeY + 11f, closeTextPaint)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        val w = width.toFloat()
        val closeRadius = 32f
        val closeX = w - closeRadius - 4f
        val closeY = closeRadius + 4f

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                // Checa se o toque foi no botão de fechar "×"
                val distToClose = abs(event.x - closeX) + abs(event.y - closeY)
                if (distToClose <= closeRadius * 1.5f) {
                    onDismissClick()
                    return true
                }

                initialX = layoutParams.x
                initialY = layoutParams.y
                initialTouchX = event.rawX
                initialTouchY = event.rawY
                isDragging = false
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = (event.rawX - initialTouchX).toInt()
                val dy = (event.rawY - initialTouchY).toInt()
                if (abs(dx) > 12 || abs(dy) > 12) {
                    isDragging = true
                }
                if (isDragging) {
                    layoutParams.x = initialX + dx
                    layoutParams.y = initialY + dy
                    try {
                        windowManager.updateViewLayout(this, layoutParams)
                    } catch (_: Exception) {}
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (!isDragging) {
                    // Foi um clique simples na bolha -> abre a Aurora
                    onBubbleClick()
                }
                isDragging = false
                return true
            }
        }
        return super.onTouchEvent(event)
    }
}
