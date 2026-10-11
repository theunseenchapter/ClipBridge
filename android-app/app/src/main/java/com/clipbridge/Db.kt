package com.clipbridge

import android.content.Context
import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "clips")
data class Clip(
    @PrimaryKey val id: String, val origin: String, val seq: Long, val lamport: Long, val created: Long,
    val kind: String, val mime: String, val size: Long, val sha256: String, val text: String,
    val pinned: Boolean = false, val status: String, val outgoing: Boolean, val pending: Boolean = false)

@Dao
interface ClipDao {
    @Query("SELECT * FROM clips WHERE :q = '' OR text LIKE '%' || :q || '%' ORDER BY pinned DESC, created DESC")
    fun search(q: String): Flow<List<Clip>>
    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insert(c: Clip): Long
    @Query("SELECT COUNT(*) FROM clips WHERE id = :id") suspend fun exists(id: String): Int
    @Query("SELECT * FROM clips WHERE id = :id") suspend fun get(id: String): Clip?
    @Query("SELECT * FROM clips WHERE pending = 1 ORDER BY lamport DESC, origin DESC") suspend fun pending(): List<Clip>
    @Query("UPDATE clips SET pending = 0, status = :st WHERE id = :id") suspend fun settle(id: String, st: String)
    @Query("UPDATE clips SET pinned = :p WHERE id = :id") suspend fun pin(id: String, p: Boolean)
    @Query("DELETE FROM clips WHERE id = :id") suspend fun delete(id: String)
    @Query("DELETE FROM clips WHERE pinned = 0") suspend fun clear()
    @Query("DELETE FROM clips WHERE pinned = 0 AND id NOT IN (SELECT id FROM clips ORDER BY created DESC LIMIT :keep)")
    suspend fun prune(keep: Int)
}

@Database(entities = [Clip::class], version = 1, exportSchema = false)
abstract class AppDb : RoomDatabase() {
    abstract fun dao(): ClipDao
    companion object {
        fun create(c: Context) = Room.databaseBuilder(c, AppDb::class.java, "clipbridge.db").build()
    }
}
