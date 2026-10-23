// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View
import android.view.animation.OvershootInterpolator

/**
 * Alvo visual de descarte da bolha flutuante ("X" no centro inferior da tela).
 * Estilo Messenger / Android Bubbles: surge suavemente quando o usuário começa
 * a arrastar a bolha e se expande com feedback visual quando a bolha se aproxima.
 */
@SuppressLint("ViewConstructor")
class BubbleDismissTargetView(context: Context) : View(context) {

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.parseColor("#4429263A")
    }

    private val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        color = Color.parseColor("#80FFFFFF")
    }

    private val xPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 6f
        strokeCap = Paint.Cap.ROUND
        color = Color.WHITE
    }

    private var targetScale = 1.0f
    private var isTargetHovered = false
    private var scaleAnimator: ValueAnimator? = null

    fun setTargetHovered(hovered: Boolean) {
        if (isTargetHovered == hovered) return
        isTargetHovered = hovered

        scaleAnimator?.cancel()
        val startScale = targetScale
        val endScale = if (hovered) 1.25f else 1.0f

        scaleAnimator = ValueAnimator.ofFloat(startScale, endScale).apply {
            duration = 180
            interpolator = OvershootInterpolator(1.5f)
            addUpdateListener { anim ->
                targetScale = anim.animatedValue as Float
                if (isTargetHovered) {
                    bgPaint.color = Color.parseColor("#D32F2F") // Vermelho de exclusão
                    ringPaint.color = Color.WHITE
                } else {
                    bgPaint.color = Color.parseColor("#6629263A")
                    ringPaint.color = Color.parseColor("#80FFFFFF")
                }
                invalidate()
            }
            start()
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val cx = width / 2f
        val cy = height / 2f
        val radius = (width.coerceAtMost(height) / 2f - 8f) * targetScale

        // Círculo de fundo
        canvas.drawCircle(cx, cy, radius, bgPaint)
        canvas.drawCircle(cx, cy, radius, ringPaint)

        // Desenho do "X"
        val xSize = radius * 0.40f
        canvas.drawLine(cx - xSize, cy - xSize, cx + xSize, cy + xSize, xPaint)
        canvas.drawLine(cx + xSize, cy - xSize, cx - xSize, cy + xSize, xPaint)
    }
}
