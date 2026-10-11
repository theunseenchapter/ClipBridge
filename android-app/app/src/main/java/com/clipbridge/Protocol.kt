package com.clipbridge

import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

const val VERSION = 1
const val MAX_BYTES = 25 * 1024 * 1024
const val MAX_FRAME = 32 * 1024 * 1024
private val UUID_RE = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
private val URL_RE = Regex("^https?://\\S+$", RegexOption.IGNORE_CASE)

fun sha256Hex(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }
fun hmacHex(key: ByteArray, vararg parts: ByteArray): String {
    val m = Mac.getInstance("HmacSHA256"); m.init(SecretKeySpec(key, "HmacSHA256"))
    parts.forEach { m.update(it) }
    return m.doFinal().joinToString("") { "%02x".format(it) }
}
fun hexToBytes(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

fun writeFrame(out: DataOutputStream, o: JSONObject) {
    val b = o.toString().toByteArray(Charsets.UTF_8)
    synchronized(out) { out.writeInt(b.size); out.write(b); out.flush() }
}
fun readFrame(inp: DataInputStream): JSONObject {
    val n = inp.readInt()
    require(n in 2..MAX_FRAME) { "bad frame" }
    val b = ByteArray(n); inp.readFully(b)
    return JSONObject(String(b, Charsets.UTF_8))
}

data class Item(val id: String, val origin: String, val seq: Long, val lamport: Long, val created: Double,
                val kind: String, val mime: String, val size: Long, val sha256: String, val text: String) {
    fun toJson() = JSONObject().put("v", VERSION).put("id", id).put("origin", origin).put("seq", seq)
        .put("lamport", lamport).put("created", created).put("kind", kind).put("mime", mime)
        .put("size", size).put("sha256", sha256).put("text", text)

    companion object {
        fun create(origin: String, seq: Long, lamport: Long, text: String): Item {
            val raw = text.toByteArray(Charsets.UTF_8)
            val url = URL_RE.matches(text.trim())
            return Item(UUID.randomUUID().toString(), origin, seq, lamport, System.currentTimeMillis() / 1000.0,
                if (url) "url" else "text", if (url) "text/uri-list" else "text/plain", raw.size.toLong(), sha256Hex(raw), text)
        }

        /** Returns null when invalid (bad version/ids/size/integrity). */
        fun parse(j: JSONObject?): Item? = try {
            if (j == null || j.getInt("v") != VERSION) null else {
                val it = Item(j.getString("id"), j.getString("origin"), j.getLong("seq"), j.getLong("lamport"),
                    j.getDouble("created"), j.getString("kind"), j.getString("mime"), j.getLong("size"),
                    j.getString("sha256"), j.optString("text", ""))
                val raw = it.text.toByteArray(Charsets.UTF_8)
                if (!UUID_RE.matches(it.id) || !UUID_RE.matches(it.origin) || it.seq < 0 || it.lamport < 0 ||
                    it.size > MAX_BYTES || it.mime.length > 100 ||
                    it.kind !in setOf("text", "url", "html", "image", "file")) null
                else if (it.kind in setOf("text", "url", "html") && (raw.size.toLong() != it.size || sha256Hex(raw) != it.sha256)) null
                else it
            }
        } catch (e: Exception) { null }
    }
}
