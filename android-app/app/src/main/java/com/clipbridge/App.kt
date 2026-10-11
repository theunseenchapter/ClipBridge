package com.clipbridge

import android.app.Application

class App : Application() {
    lateinit var db: AppDb
    override fun onCreate() { super.onCreate(); db = AppDb.create(this); instance = this }
    companion object { lateinit var instance: App }
}
