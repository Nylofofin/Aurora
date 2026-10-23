# Aurora Companion — ProGuard / R8 rules

# ─── Kotlin data classes (protocol models) ────────────────────────────────────
# Keep all data classes in the app package so JSON serialisation and reflection
# can reach their fields and constructors.
-keepclassmembers class app.aurora.companion.** {
    public <init>(...);
    public ** component*();
    public ** copy(...);
    public static ** Companion;
}
-keep class app.aurora.companion.CompanionReply { *; }
-keep class app.aurora.companion.CompanionVoiceReply { *; }

# ─── Android services (must not be obfuscated — referenced by Manifest) ───────
-keep public class app.aurora.companion.MicCaptureService { *; }
-keep public class app.aurora.companion.WakeCaptureService { *; }

# ─── Kotlin companion objects & coroutines ────────────────────────────────────
-keepclassmembers class ** {
    public static ** Companion;
}
-dontwarn kotlinx.coroutines.**
-keep class kotlinx.coroutines.** { *; }

# ─── Android KeyStore / security ──────────────────────────────────────────────
-keep class java.security.** { *; }
-keep class javax.crypto.** { *; }
-keep class android.security.keystore.** { *; }

# ─── JSON parsing ─────────────────────────────────────────────────────────────
# If the project switches to Gson / Moshi / kotlinx.serialization later:
-keepattributes Signature
-keepattributes *Annotation*
-keepattributes EnclosingMethod
-keepattributes InnerClasses

# ─── Compose ──────────────────────────────────────────────────────────────────
-keep class androidx.compose.** { *; }
-dontwarn androidx.compose.**

# ─── Miscellaneous ────────────────────────────────────────────────────────────
-dontobfuscate
# Remove above line if obfuscation is desired in production; keeping it for
# easier crash-log reading during the beta phase.
