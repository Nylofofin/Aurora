plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "app.aurora.companion"
    compileSdk = 37

    defaultConfig {
        applicationId = "app.aurora.companion"
        minSdk = 26
        targetSdk = 36
        versionCode = 18
        versionName = "0.8.3-beta"
    }

    // ── Signing ────────────────────────────────────────────────────────────────
    // Reads env-vars injected by CI. Falls back to debug signing for local dev.
    val envKeystoreFile = System.getenv("AURORA_KEYSTORE_FILE")
    val envKeystorePassword = System.getenv("AURORA_KEYSTORE_PASSWORD")
    val envKeyAlias = System.getenv("AURORA_KEY_ALIAS")
    val envKeyPassword = System.getenv("AURORA_KEY_PASSWORD")

    val hasSigningConfig = !envKeystoreFile.isNullOrBlank() &&
        !envKeystorePassword.isNullOrBlank() &&
        !envKeyAlias.isNullOrBlank() &&
        !envKeyPassword.isNullOrBlank()

    if (hasSigningConfig) {
        signingConfigs {
            create("release") {
                storeFile = file(envKeystoreFile!!)
                storePassword = envKeystorePassword
                keyAlias = envKeyAlias
                keyPassword = envKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = if (hasSigningConfig) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
        debug {
            // No changes — keep default debug signing and no minification
        }
    }

    buildFeatures { compose = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.activity.compose)
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    debugImplementation(libs.compose.ui.tooling)
}
