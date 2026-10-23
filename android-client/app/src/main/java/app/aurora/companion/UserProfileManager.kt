// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import android.content.Context
import android.content.SharedPreferences

data class UserProfile(
    val isLoggedIn: Boolean = false,
    val loginType: String = "local", // "local", "google", "github"
    val username: String = "Usuário",
    val age: String = "",
    val avatarIcon: String = "🌌",
    val selectedTheme: String = "aurora", // "aurora", "dark", "light", "neon"
)

class UserProfileManager(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("aurora_user_profile", Context.MODE_PRIVATE)

    fun loadProfile(): UserProfile {
        return UserProfile(
            isLoggedIn = prefs.getBoolean("is_logged_in", false),
            loginType = prefs.getString("login_type", "local") ?: "local",
            username = prefs.getString("username", "Usuário") ?: "Usuário",
            age = prefs.getString("age", "") ?: "",
            avatarIcon = prefs.getString("avatar_icon", "🌌") ?: "🌌",
            selectedTheme = prefs.getString("selected_theme", "aurora") ?: "aurora",
        )
    }

    fun saveProfile(profile: UserProfile) {
        prefs.edit()
            .putBoolean("is_logged_in", profile.isLoggedIn)
            .putString("login_type", profile.loginType)
            .putString("username", profile.username)
            .putString("age", profile.age)
            .putString("avatar_icon", profile.avatarIcon)
            .putString("selected_theme", profile.selectedTheme)
            .apply()
    }

    fun logout() {
        prefs.edit().putBoolean("is_logged_in", false).apply()
    }
}
