package com.clipbridge

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

class SyncService : Service() {
    override fun onBind(i: Intent?): IBinder? = null
    override fun onStartCommand(i: Intent?, f: Int, id: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("svc", "Connection", NotificationManager.IMPORTANCE_LOW))
        val send = PendingIntent.getActivity(this, 1, Intent(this, SendClipActivity::class.java).setAction("SEND_CLIP")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
        startForeground(1, NotificationCompat.Builder(this, "svc").setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("ClipBridge running").setContentText("Tap “Send clipboard” after copying")
            .addAction(0, "Send clipboard", send).setOngoing(true).build())
        Engine.start(this)
        return START_STICKY
    }
    companion object { fun start(c: Context) = c.startForegroundService(Intent(c, SyncService::class.java)) }
}
