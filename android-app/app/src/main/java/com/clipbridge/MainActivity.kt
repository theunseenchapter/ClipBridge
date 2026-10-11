package com.clipbridge

import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.compose.material3.AlertDialog
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val cm by lazy { getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager }
    private val listener = ClipboardManager.OnPrimaryClipChangedListener { readClip() }

    private fun readClip() {
        cm.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString()?.let { Engine.onLocalCopy(this, it) }
    }

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        SyncService.start(this)
        setContent { MaterialTheme { Screen() } }
    }
    override fun onStart() { super.onStart(); cm.addPrimaryClipChangedListener(listener) }
    override fun onStop() { super.onStop(); cm.removePrimaryClipChangedListener(listener) }
    override fun onWindowFocusChanged(hasFocus: Boolean) { super.onWindowFocusChanged(hasFocus); if (hasFocus) readClip() }

    private fun scan() {
        val o = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
        GmsBarcodeScanning.getClient(this, o).startScan().addOnSuccessListener { bc ->
            CoroutineScope(Dispatchers.IO).launch {
                try { Engine.pair(this@MainActivity, bc.rawValue ?: "") }
                catch (e: Exception) { runOnUiThread { Toast.makeText(this@MainActivity, "Pairing failed: ${e.message}", Toast.LENGTH_LONG).show() } }
            }
        }
    }

    @Composable
    @OptIn(ExperimentalMaterial3Api::class)
    fun Screen() {
        val dao = App.instance.db.dao()
        var q by remember { mutableStateOf("") }
        var paused by remember { mutableStateOf(Store.isPaused(this)) }
        var showDisconnect by remember { mutableStateOf(false) }
        val status by Engine.state.collectAsState()
        val clips by remember(q) { dao.search(q) }.collectAsState(emptyList())
        val scope = rememberCoroutineScope()
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text("ClipBridge", fontWeight = FontWeight.Bold)
                            Text("Private clipboard sync", style = MaterialTheme.typography.labelSmall)
                        }
                    },
                    actions = {
                        IconButton(onClick = { paused = !paused; Store.setPaused(this@MainActivity, paused) }) {
                            Text(if (paused) "▶" else "Ⅱ", fontSize = 18.sp)
                        }
                    }
                )
            }
        ) { padding ->
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
                contentPadding = PaddingValues(vertical = 16.dp)
            ) {
                item {
                    StatusCard(status = status, paused = paused)
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            onClick = { scan() },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(14.dp)
                        ) { Text(if (status.startsWith("Connected")) "Pair another" else "Pair phone") }
                        OutlinedButton(
                            onClick = { scope.launch { dao.clear() } },
                            shape = RoundedCornerShape(14.dp)
                        ) { Text("Clear") }
                    }
                }
                item {
                    OutlinedButton(
                        onClick = { showDisconnect = true },
                        enabled = status.startsWith("Connected") || Store.pairing(this@MainActivity) != null,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp)
                    ) { Text("Disconnect phone") }
                }
                item {
                    OutlinedTextField(
                        value = q,
                        onValueChange = { q = it },
                        label = { Text("Search clipboard history") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(14.dp)
                    )
                }
                if (clips.isEmpty()) {
                    item { EmptyState() }
                } else {
                    item {
                        Text(
                            "Recent clips",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                    items(clips, key = { it.id }) { c ->
                        ClipCard(c, scope)
                    }
                }
            }
            if (showDisconnect) {
                AlertDialog(
                    onDismissRequest = { showDisconnect = false },
                    title = { Text("Disconnect phone?") },
                    text = { Text("This removes the pairing from this phone. You will need to scan a new QR code to reconnect.") },
                    confirmButton = {
                        TextButton(onClick = {
                            Engine.disconnect(this@MainActivity)
                            showDisconnect = false
                        }) { Text("Disconnect") }
                    },
                    dismissButton = { TextButton(onClick = { showDisconnect = false }) { Text("Cancel") } }
                )
            }
        }
    }

    @Composable
    private fun StatusCard(status: String, paused: Boolean) {
        val connected = status.startsWith("Connected")
        val accent = if (connected) Color(0xFF49D17D) else Color(0xFFFFB454)
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerHigh),
            shape = RoundedCornerShape(22.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(20.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(shape = RoundedCornerShape(16.dp), color = accent.copy(alpha = .16f)) {
                    Text(if (paused) "Ⅱ" else "↕", color = accent, fontSize = 28.sp,
                        modifier = Modifier.padding(14.dp))
                }
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (paused) "Sync paused" else if (connected) "Connected" else "Waiting for phone",
                        style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(if (paused) "Resume when you are ready"
                    else if (connected) "Your clipboard is synced securely"
                    else "Pair with your Windows PC to get started",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }

    @Composable
    private fun EmptyState() {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Nothing here yet", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("Copied text will appear in your history.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }

    @Composable
    private fun ClipCard(c: Clip, scope: CoroutineScope) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)
        ) {
            Column(Modifier.padding(16.dp)) {
                Text(c.text, maxLines = 4, style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.height(10.dp))
                Text("${if (c.outgoing) "Sent to laptop" else "Received from laptop"} · ${c.status}${if (c.pinned) " · pinned" else ""}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton({ Engine.setClipboard(this@MainActivity, c.text) }) { Text("Copy") }
                    TextButton({ scope.launch { App.instance.db.dao().pin(c.id, !c.pinned) } }) {
                        Text(if (c.pinned) "Unpin" else "Pin")
                    }
                    TextButton({ scope.launch { App.instance.db.dao().delete(c.id) } }) { Text("Delete") }
                }
            }
        }
    }
}
