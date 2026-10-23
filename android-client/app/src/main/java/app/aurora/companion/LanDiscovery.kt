// SPDX-License-Identifier: GPL-3.0-only
package app.aurora.companion

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import java.net.Inet4Address
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Finds the optional PC DNS-SD advertisement; TLS pinning remains a separate trust step. */
class LanDiscovery(context: Context) {
    private val manager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private var listener: NsdManager.DiscoveryListener? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private val resolving = AtomicBoolean(false)
    private var serviceInfoCallbackRegistered = false

    @Suppress("DEPRECATION")
    fun start(onFound: (String) -> Unit, onError: (String) -> Unit) {
        stop()
        resolving.set(false)
        multicastLock = wifi.createMulticastLock("aurora-companion-discovery").apply { setReferenceCounted(false); acquire() }
        val active = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) = Unit
            override fun onDiscoveryStopped(serviceType: String) = Unit
            override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                onError("A descoberta local falhou (código $errorCode).")
                stop()
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = stop()
            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                if (!serviceInfo.serviceName.startsWith("Aurora Companion") || !resolving.compareAndSet(false, true)) return
                if (Build.VERSION.SDK_INT >= 31) {
                    val callback = object : NsdManager.ServiceInfoCallback {
                        override fun onServiceInfoCallbackRegistrationFailed(errorCode: Int) {
                            resolving.set(false)
                        }
                        override fun onServiceUpdated(info: NsdServiceInfo) {
                            val address = (if (Build.VERSION.SDK_INT >= 33) info.hostAddresses.firstOrNull { it is Inet4Address } else null)?.hostAddress
                                ?: info.host?.takeIf { it is Inet4Address }?.hostAddress
                            if (address != null && info.port in 1..65535) {
                                onFound("https://$address:${info.port}")
                                stop()
                            } else resolving.set(false)
                        }
                        override fun onServiceLost() {
                            resolving.set(false)
                        }
                        override fun onServiceInfoCallbackUnregistered() = Unit
                    }
                    serviceInfoCallbackRegistered = true
                    manager.registerServiceInfoCallback(serviceInfo, Executors.newSingleThreadExecutor(), callback)
                } else {
                    @Suppress("DEPRECATION")
                    manager.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                            resolving.set(false)
                        }
                        override fun onServiceResolved(info: NsdServiceInfo) {
                            val address = (if (Build.VERSION.SDK_INT >= 33) info.hostAddresses.firstOrNull { it is Inet4Address } else null)?.hostAddress
                                ?: info.host?.takeIf { it is Inet4Address }?.hostAddress
                            if (address != null && info.port in 1..65535) {
                                onFound("https://$address:${info.port}")
                                stop()
                            } else resolving.set(false)
                        }
                    })
                }
            }
        }
        listener = active
        try {
            manager.discoverServices("_aurora-companion._tcp.", NsdManager.PROTOCOL_DNS_SD, active)
        } catch (error: Exception) {
            onError(error.message ?: "Não consegui iniciar a busca na rede local.")
            stop()
        }
    }

    @Suppress("DEPRECATION")
    fun stop() {
        listener?.let { active ->
            try { manager.stopServiceDiscovery(active) } catch (_: Exception) { }
        }
        listener = null
        multicastLock?.let { if (it.isHeld) it.release() }
        multicastLock = null
    }
}
