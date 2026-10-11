package com.clipbridge

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class Pairing(val peerId: String, val peerName: String, val host: String, val port: Int, val fp: String, val secret: ByteArray)

/** Prefs + Android-Keystore-wrapped shared secret. */
object Store {
    private fun sp(c: Context) = c.getSharedPreferences("cb", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey("cb_key", null) as? SecretKey)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(KeyGenParameterSpec.Builder("cb_key", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return g.generateKey()
    }
    private fun enc(b: ByteArray): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, key())
        return Base64.encodeToString(c.iv + c.doFinal(b), Base64.NO_WRAP)
    }
    private fun dec(s: String): ByteArray {
        val r = Base64.decode(s, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, r, 0, 12))
        return c.doFinal(r, 12, r.size - 12)
    }

    fun deviceId(c: Context): String = sp(c).getString("device_id", null)
        ?: UUID.randomUUID().toString().also { sp(c).edit().putString("device_id", it).apply() }
    fun deviceName(): String = android.os.Build.MODEL ?: "Android"

    fun pairing(c: Context): Pairing? {
        val p = sp(c); val s = p.getString("secret", null) ?: return null
        return try {
            Pairing(p.getString("peer_id", "")!!, p.getString("peer_name", "laptop")!!, p.getString("host", "")!!,
                p.getInt("port", 48500), p.getString("fp", "")!!, dec(s))
        } catch (e: Exception) { null }
    }
    fun savePairing(c: Context, x: Pairing) = sp(c).edit().putString("peer_id", x.peerId).putString("peer_name", x.peerName)
        .putString("host", x.host).putInt("port", x.port).putString("fp", x.fp).putString("secret", enc(x.secret)).apply()
    fun saveHost(c: Context, host: String) = sp(c).edit().putString("host", host).apply()
    fun unpair(c: Context) = sp(c).edit().remove("secret").apply()

    fun long(c: Context, k: String) = sp(c).getLong(k, 0)
    fun putLong(c: Context, k: String, v: Long) = sp(c).edit().putLong(k, v).apply()
    fun str(c: Context, k: String) = sp(c).getString(k, "") ?: ""
    fun putStr(c: Context, k: String, v: String) = sp(c).edit().putString(k, v).apply()
    var paused: Boolean = false
    fun isPaused(c: Context) = sp(c).getBoolean("paused", false)
    fun setPaused(c: Context, v: Boolean) = sp(c).edit().putBoolean("paused", v).apply()
}
