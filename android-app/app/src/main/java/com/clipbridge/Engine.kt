package com.clipbridge

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.X509TrustManager
import kotlin.coroutines.resume

/** Connection, pairing, ordering, dedupe, queue. Android is always the TLS client. */
object Engine {
    val state = MutableStateFlow("Not paired")
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null
    @Volatile private var out: DataOutputStream? = null
    @Volatile var suppressText: String? = null
    private const val TAG = "ClipBridge"

    fun start(c: Context) { if (job?.isActive == true) return; job = scope.launch { loop(c.applicationContext) } }
    fun stop() { job?.cancel(); state.value = "Stopped" }

    fun disconnect(c: Context) {
        Store.unpair(c)
        out = null
        job?.cancel()
        job = null
        state.value = "Not paired"
    }

    // ---- TLS with certificate pinning (fingerprint comes from the QR code)
    private fun socket(host: String, port: Int, fp: String): SSLSocket {
        val tm = object : X509TrustManager {
            override fun checkServerTrusted(chain: Array<X509Certificate>, a: String) {
                if (sha256Hex(chain[0].encoded) != fp) throw CertificateException("certificate pin mismatch")
            }
            override fun checkClientTrusted(chain: Array<X509Certificate>, a: String) {}
            override fun getAcceptedIssuers() = emptyArray<X509Certificate>()
        }
        val ctx = SSLContext.getInstance("TLS"); ctx.init(null, arrayOf(tm), null)
        val s = ctx.socketFactory.createSocket() as SSLSocket
        s.connect(InetSocketAddress(host, port), 5000); s.soTimeout = 90_000; s.startHandshake()
        return s
    }

    /** qr = JSON from the Windows pairing window. Throws on failure. */
    suspend fun pair(c: Context, qr: String) = withContext(Dispatchers.IO) {
        val j = JSONObject(qr)
        val s = socket(j.getString("host"), j.getInt("port"), j.getString("fp"))
        s.use {
            val i = DataInputStream(s.inputStream.buffered()); val o = DataOutputStream(s.outputStream.buffered())
            readFrame(i)  // challenge (unused for pairing; the one-time token authenticates us)
            writeFrame(o, JSONObject().put("t", "pair").put("v", VERSION).put("token", j.getString("tok"))
                .put("device_id", Store.deviceId(c)).put("name", Store.deviceName()))
            val r = readFrame(i)
            check(r.getString("t") == "pair_ok") { "pairing refused: " + r.optString("code") }
            Store.savePairing(c, Pairing(r.getString("device_id"), r.optString("name", "laptop"), j.getString("host"),
                j.getInt("port"), j.getString("fp"), android.util.Base64.decode(r.getString("secret"), android.util.Base64.DEFAULT)))
        }
        start(c)
    }

    private suspend fun loop(c: Context) {
        var backoff = 1000L; var fails = 0
        while (currentCoroutineContext().isActive) {
            val p = Store.pairing(c)
            if (p == null) { state.value = "Not paired"; delay(2000); continue }
            if (Store.isPaused(c)) { state.value = "Paused"; delay(2000); continue }
            try { session(c, p); backoff = 1000; fails = 0 }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { Log.w(TAG, "connection ended: ${e.javaClass.simpleName}"); fails++ }
            out = null; state.value = "Reconnecting…"
            if (fails >= 2) discover(c, p.peerId)?.let { Store.saveHost(c, it) }  // IP may have changed
            delay(backoff); backoff = minOf(backoff * 2, 30_000)
        }
    }

    private suspend fun session(c: Context, p: Pairing) = coroutineScope {
        val s = socket(p.host, p.port, p.fp)
        coroutineContext[Job]!!.invokeOnCompletion { runCatching { s.close() } }
        val i = DataInputStream(s.inputStream.buffered()); val o = DataOutputStream(s.outputStream.buffered())
        val ch = readFrame(i); val nonce = hexToBytes(ch.getString("nonce")); val me = Store.deviceId(c)
        writeFrame(o, JSONObject().put("t", "hello").put("v", VERSION).put("device_id", me).put("name", Store.deviceName())
            .put("mac", hmacHex(p.secret, nonce, me.toByteArray())))
        val r = readFrame(i)
        if (r.getString("t") != "ready") { if (r.optString("code") == "unauthorized") Store.unpair(c); error("auth failed") }
        out = o; state.value = "Connected to ${p.peerName}"
        val pinger = launch { while (isActive) { delay(20_000); writeFrame(o, JSONObject().put("t", "ping")) } }
        try {
            flush(c)
            while (true) {
                val m = readFrame(i)
                when (m.getString("t")) {
                    "clip" -> onRemote(c, p, Item.parse(m.optJSONObject("item")), m.optJSONObject("item"), o)
                    "ack" -> { val id = m.optString("id"); val st = m.optString("status", "delivered")
                        App.instance.db.dao().settle(id, if (st == "applied") "delivered" else st) }
                }
            }
        } finally { pinger.cancel(); out = null; runCatching { s.close() } }
    }

    private suspend fun flush(c: Context) {
        val o = out ?: return; val dao = App.instance.db.dao()
        val q = dao.pending(); if (q.isEmpty()) return
        q.drop(1).forEach { dao.settle(it.id, "superseded") }  // never send older state after newer
        val k = q[0]
        writeFrame(o, JSONObject().put("t", "clip").put("item", Item(k.id, k.origin, k.seq, k.lamport, k.created / 1000.0,
            k.kind, k.mime, k.size, k.sha256, k.text).toJson()))
    }

    private suspend fun onRemote(c: Context, p: Pairing, item: Item?, raw: JSONObject?, o: DataOutputStream) {
        fun ack(id: String, st: String) = writeFrame(o, JSONObject().put("t", "ack").put("id", id).put("status", st))
        val dao = App.instance.db.dao()
        if (item == null || item.origin != p.peerId) { ack(raw?.optString("id") ?: "", "rejected"); return }
        if (dao.exists(item.id) > 0) { ack(item.id, "duplicate"); return }
        if (item.seq <= Store.long(c, "lastseq")) { ack(item.id, "replay"); return }
        Store.putLong(c, "lastseq", item.seq)
        fun rec(st: String) = Clip(item.id, item.origin, item.seq, item.lamport, (item.created * 1000).toLong(),
            item.kind, item.mime, item.size, item.sha256, item.text, false, st, false)
        if (item.kind != "text" && item.kind != "url") { dao.insert(rec("unsupported")); ack(item.id, "unsupported"); return }
        if (Store.isPaused(c)) { dao.insert(rec("paused")); ack(item.id, "paused"); return }
        Store.putLong(c, "lamport", maxOf(Store.long(c, "lamport"), item.lamport))
        val al = Store.long(c, "act_l"); val ao = Store.str(c, "act_o")
        val newer = item.lamport > al || (item.lamport == al && item.origin > ao)
        var st = "stale"
        if (newer) {
            st = if (setClipboard(c, item.text)) "applied" else "write_failed"
            if (st == "applied") { Store.putLong(c, "act_l", item.lamport); Store.putStr(c, "act_o", item.origin) }
        }
        dao.insert(rec(st)); dao.prune(100); ack(item.id, st)
        if (newer) notifyIncoming(c, p.peerName, item)
    }

    fun setClipboard(c: Context, text: String): Boolean = try {
        suppressText = text  // so our own write is never treated as a new user copy
        (c.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("ClipBridge", text)); true
    } catch (e: Exception) { false }

    /** Called for a genuine local copy (foreground capture, share target, or "Send clipboard" action). */
    fun onLocalCopy(c: Context, text: String) {
        if (text.isEmpty() || text == suppressText || Store.isPaused(c) || Store.pairing(c) == null) return
        if (text.toByteArray().size > MAX_BYTES) return
        scope.launch {
            val lam = Store.long(c, "lamport") + 1; val seq = Store.long(c, "seq") + 1
            Store.putLong(c, "lamport", lam); Store.putLong(c, "seq", seq)
            val it = Item.create(Store.deviceId(c), seq, lam, text)
            val dao = App.instance.db.dao()
            dao.insert(Clip(it.id, it.origin, it.seq, it.lamport, (it.created * 1000).toLong(), it.kind, it.mime, it.size,
                it.sha256, it.text, false, "queued", true, true))
            Store.putLong(c, "act_l", lam); Store.putStr(c, "act_o", it.origin)
            dao.prune(100)
            start(c)
            runCatching { flush(c) }
        }
    }

    private fun notifyIncoming(c: Context, from: String, item: Item) {
        val nm = c.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("incoming", "Incoming clips", NotificationManager.IMPORTANCE_DEFAULT))
        val copy = PendingIntent.getBroadcast(c, item.id.hashCode(), Intent(c, CopyReceiver::class.java).putExtra("id", item.id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val b = NotificationCompat.Builder(c, "incoming").setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Copied from $from").setContentText(if (item.kind == "url") "Link" else "Text")
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setAutoCancel(true)
            .addAction(0, "Copy", copy)
        if (item.kind == "url") b.addAction(0, "Open", PendingIntent.getActivity(c, item.id.hashCode(),
            Intent(Intent.ACTION_VIEW, Uri.parse(item.text.trim())), PendingIntent.FLAG_IMMUTABLE))
        nm.notify(item.id.hashCode(), b.build())
    }

    /** mDNS lookup of the laptop (matches the TXT "id" of the paired peer). */
    private suspend fun discover(c: Context, peerId: String): String? = withTimeoutOrNull(6000) {
        suspendCancellableCoroutine { cont ->
            val nsd = c.getSystemService(Context.NSD_SERVICE) as NsdManager
            val l = object : NsdManager.DiscoveryListener {
                override fun onServiceFound(s: NsdServiceInfo) {
                    @Suppress("DEPRECATION") nsd.resolveService(s, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(s: NsdServiceInfo, e: Int) {}
                        override fun onServiceResolved(r: NsdServiceInfo) {
                            val id = r.attributes["id"]?.toString(Charsets.UTF_8)
                            if (id == peerId && cont.isActive) cont.resume(r.host.hostAddress)
                        }
                    })
                }
                override fun onStartDiscoveryFailed(t: String, e: Int) { if (cont.isActive) cont.resume(null) }
                override fun onStopDiscoveryFailed(t: String, e: Int) {}
                override fun onDiscoveryStarted(t: String) {}
                override fun onDiscoveryStopped(t: String) {}
                override fun onServiceLost(s: NsdServiceInfo) {}
            }
            nsd.discoverServices("_clipbridge._tcp", NsdManager.PROTOCOL_DNS_SD, l)
            cont.invokeOnCancellation { runCatching { nsd.stopServiceDiscovery(l) } }
        }
    }
}
