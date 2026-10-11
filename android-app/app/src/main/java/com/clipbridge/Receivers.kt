package com.clipbridge

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Bundle
import kotlinx.coroutines.*

class CopyReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) {
        val id = i.getStringExtra("id") ?: return
        val pr = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            App.instance.db.dao().get(id)?.let { Engine.setClipboard(c, it.text) }
            pr.finish()
        }
    }
}

/** Transparent activity: gains window focus so Android permits reading the clipboard; also the share target. */
class SendClipActivity : Activity() {
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        SyncService.start(this)
        if (intent?.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { Engine.onLocalCopy(this, it) }
            finish()
        }
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus && intent?.action != Intent.ACTION_SEND) {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
            cm.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString()?.let { Engine.onLocalCopy(this, it) }
            finish()
        }
    }
}
