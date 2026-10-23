// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import androidx.compose.ui.graphics.Color

data class AuroraColors(
    val background: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val primary: Color,
    val secondary: Color,
    val accent: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val isDark: Boolean,
)

object AuroraThemes {
    val CosmicAurora = AuroraColors(
        background = Color(0xFFF7F5FA),
        surface = Color(0xFFFFFFFF),
        surfaceVariant = Color(0xFFEFEAF7),
        primary = Color(0xFF8066C6),
        secondary = Color(0xFF559DC5),
        accent = Color(0xFFB8A2E4),
        textPrimary = Color(0xFF29263A),
        textSecondary = Color(0xFF777387),
        isDark = false,
    )

    val DeepDark = AuroraColors(
        background = Color(0xFF08080A),
        surface = Color(0xFF141418),
        surfaceVariant = Color(0xFF202028),
        primary = Color(0xFF8A70C4),
        secondary = Color(0xFF579BC2),
        accent = Color(0xFFB39DDB),
        textPrimary = Color(0xFFEEEEF2),
        textSecondary = Color(0xFF8C8A99),
        isDark = true,
    )

    val PureLight = AuroraColors(
        background = Color(0xFFF8F7FC),
        surface = Color(0xFFFFFFFF),
        surfaceVariant = Color(0xFFEFEBF7),
        primary = Color(0xFF7E57C2),
        secondary = Color(0xFF29B6F6),
        accent = Color(0xFF5C6BC0),
        textPrimary = Color(0xFF1C1929),
        textSecondary = Color(0xFF6B667C),
        isDark = false,
    )

    val CyberNeon = AuroraColors(
        background = Color(0xFF050510),
        surface = Color(0xFF0E0E22),
        surfaceVariant = Color(0xFF19183B),
        primary = Color(0xFF00E5FF),
        secondary = Color(0xFFFF007F),
        accent = Color(0xFF76FF03),
        textPrimary = Color(0xFFF0FDF4),
        textSecondary = Color(0xFF819FA6),
        isDark = true,
    )

    fun getTheme(name: String): AuroraColors {
        return when (name.lowercase()) {
            "dark", "escuro" -> DeepDark
            "light", "claro" -> PureLight
            "neon", "cyberpunk" -> CyberNeon
            else -> CosmicAurora
        }
    }
}
